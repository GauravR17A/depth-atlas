"""Immutable historical sampling, with future data loaded after plan selection."""
from functools import lru_cache
import numpy as np
from science.contracts import UnsupportedData
from science.expedition_contracts import METHOD, PlanQuery, SurveyQuery
from science.expedition import METHODS, LIMITATIONS, prepare, select, distances, reconstruct, metrics

SUPPORTED_CASES = ('bay-bengal-2024-01', 'arabian-sea-2024-01')

class ExpeditionStore:
    def __init__(self, cases): self.cases = cases

    def validate(self, case_id, query):
        manifest, digest = self.cases.require(case_id)
        if case_id not in SUPPORTED_CASES:
            raise UnsupportedData('unsupported_expedition_case','The checked sampling experiment uses the seven-snapshot Indian Ocean cases. Monthly Pacific climate fields are not an interchangeable forcing dataset.')
        c = manifest.coordinates
        if query.depth_index >= len(c.depth_m) or c.depth_m[query.depth_index] > 1000:
            raise UnsupportedData('unsupported_depth', 'Virtual Expedition supports native depths from 0 to 1000 m.')
        return manifest, digest

    def field(self, case_id, variable, time_index, depth_index):
        m, _ = self.cases.require(case_id)
        return np.asarray(self.cases._read_array(case_id, 'analytical', variable, time_index)).reshape(len(m.coordinates.depth_m), len(m.coordinates.latitude), len(m.coordinates.longitude))[depth_index]

    @lru_cache(maxsize=8)
    def prior(self, case_id, variable, depth_index):
        m, _ = self.cases.require(case_id)
        return prepare(self.field(case_id, variable, 0, depth_index), m.coordinates.longitude, m.coordinates.latitude)

    def base(self, case_id, query, kind):
        m, digest = self.validate(case_id, query)
        return dict(schema_version='1', kind=kind, method_version=METHOD, case_id=case_id,
                    manifest_sha256=digest, units=next(v.units for v in m.variables if v.id == query.variable),
                    variable=query.variable, depth_m=m.coordinates.depth_m[query.depth_index],
                    prior_time=m.coordinates.times[0], methods=METHODS.copy(), limitations=LIMITATIONS.copy())

    def plan(self, case_id, query): return self._plan(case_id, query.model_dump_json())

    @lru_cache(maxsize=12)
    def _plan(self, case_id, query_json):
        q = PlanQuery.model_validate_json(query_json)
        m, _ = self.validate(case_id, q); c = m.coordinates
        p = self.prior(case_id, q.variable, q.depth_index)
        chosen = select(p, q.budget, q.min_spacing_km, q.objective, q.seed)
        rows = []
        for i, index in enumerate(p['candidates']):
            y, x = divmod(int(index), len(c.longitude)); g = p['gradients'][i]
            rows.append(dict(id=f'n{index}', longitude=c.longitude[x], latitude=c.latitude[y], x_index=x, y_index=y,
                             prior_value=float(p['prior'][index]), gradient_per_km=float(g) if np.isfinite(g) else None))
        lookup = {r['id']: r for r in rows}
        stations = []
        for i, index in enumerate(chosen):
            nearest = float(distances(p['points'][[index]], p['points'][chosen[:i]]).min()) if i else None
            reason = 'High prior gradient balanced with distance from selected stations.' if q.objective == 'gradient' else 'Farthest available location from selected stations.' if i else 'Nearest candidate to the coordinate centre of the candidate pool.'
            stations.append(dict(**lookup[f'n{index}'], order=i+1, nearest_station_km=nearest, rationale=reason))
        # Preview subsampling never enters the numerical method.
        xi = sorted(set(range(0, len(c.longitude), 3)) | {len(c.longitude)-1})
        yi = sorted(set(range(0, len(c.latitude), 3)) | {len(c.latitude)-1})
        bg = p['prior'].reshape(p['shape'])[np.ix_(yi, xi)]
        out = self.base(case_id, q, 'station_plan')
        out.update(query=q.model_dump(), bounds=[c.longitude[0], c.latitude[0], c.longitude[-1], c.latitude[-1]],
                   candidate_count=len(rows), evaluation_count=len(p['evaluation']), candidates=rows, stations=stations,
                   fulfilled=len(chosen) == q.budget,
                   reason=None if len(chosen) == q.budget else 'The greedy design could not fill this budget at the chosen spacing and depth. Reduce budget or spacing. This does not prove no feasible design exists.',
                   background=dict(longitude=[c.longitude[i] for i in xi], latitude=[c.latitude[i] for i in yi], shape=list(bg.shape), values=[float(v) if np.isfinite(v) else None for v in bg.ravel()]))
        return out

    def survey(self, case_id, q: SurveyQuery):
        m, _ = self.validate(case_id, q); c = m.coordinates
        for x, y in (q.start, q.end):
            if not c.longitude[0] <= x <= c.longitude[-1] or not c.latitude[0] <= y <= c.latitude[-1]:
                raise UnsupportedData('outside_coverage', 'Both route endpoints must be inside this historical case.')
        if q.start == q.end: raise UnsupportedData('invalid_route', 'Choose two distinct route endpoints.')
        xx, yy = np.meshgrid(c.longitude, c.latitude)
        points = np.column_stack([xx.ravel(), yy.ravel()])
        requested = np.linspace(q.start, q.end, q.stations)
        matrix = distances(requested, points)
        # Stable source-order selection for numerically equidistant columns.
        indices = np.argmax(matrix <= matrix.min(axis=1)[:, None] + 1e-10, axis=1)
        field = self.field(case_id, q.variable, q.time_index, q.depth_index).ravel()
        increments = [0.0]+[float(distances(requested[i-1:i], requested[i:i+1])[0, 0]) for i in range(1, q.stations)]
        cumulative = np.cumsum(increments)
        samples = []
        for i, index in enumerate(indices):
            y, x = divmod(int(index), len(c.longitude)); value = field[index]
            samples.append(dict(order=i+1, requested_longitude=float(requested[i, 0]), requested_latitude=float(requested[i, 1]),
                                longitude=c.longitude[x], latitude=c.latitude[y], x_index=x, y_index=y,
                                distance_km=float(cumulative[i]), offset_km=float(matrix[i, index]), value=float(value) if np.isfinite(value) else None))
        out = self.base(case_id, q, 'virtual_survey')
        out.update(query=q.model_dump(), model_time=c.times[q.time_index], samples=samples, simulated=True, unique_columns=len(set(indices)))
        out['methods'] = ['Simulated model samples along a straight longitude/latitude segment. Equal coordinate increments, not equal geodesic spacing.',
                          'Nearest native column by great-circle distance at the exact selected native depth and timestamp. Ties within 1e-10 km select the first latitude-major source index. No horizontal, vertical or temporal interpolation. Missing values remain missing.',
                          'Distances accumulate the great-circle lengths of consecutive requested segments. Offset is requested-to-sampled-column distance.']
        return out

    def experiment(self, case_id, query): return self._experiment(case_id, query.model_dump_json())

    @lru_cache(maxsize=4)
    def _experiment(self, case_id, query_json):
        q = PlanQuery.model_validate_json(query_json)
        plan = self.plan(case_id, q); m, _ = self.validate(case_id, q)
        p = self.prior(case_id, q.variable, q.depth_index)
        seeds = [(q.seed+i) % 2147483648 for i in range(5)]
        # This complete tuple is frozen before any target-time field is loaded.
        designs = [('selected', None, select(p, q.budget, q.min_spacing_km, q.objective, q.seed)),
                   ('uniform', None, select(p, q.budget, q.min_spacing_km, 'coverage'))]
        designs += [('random', seed, select(p, q.budget, q.min_spacing_km, 'random', seed)) for seed in seeds]
        runs = []
        for time_index in (2, 4, 6):
            truth = self.field(case_id, q.variable, time_index, q.depth_index).ravel()
            evaluation = p['evaluation'][np.isfinite(truth[p['evaluation']])]
            for strategy, seed, indices in [*designs, ('persistence', None, [])]:
                reason = 'No common finite evaluation targets at this snapshot.' if not len(evaluation) else None
                if strategy != 'persistence':
                    if len(indices) != q.budget: reason = 'Greedy selection did not achieve the exact requested budget and spacing.'
                    elif not np.isfinite(truth[indices]).all(): reason = 'At least one frozen station has no target-time value. No station was replaced using future information.'
                values = [float(truth[i]) if np.isfinite(truth[i]) else None for i in indices]
                row = dict(strategy=strategy, seed=seed, time_index=time_index, model_time=m.coordinates.times[time_index],
                           status='failed' if reason else 'ok', reason=reason, budget=len(indices), station_ids=[f'n{i}' for i in indices],
                           station_values=values, evaluation_count=len(evaluation), rmse=None, mae=None, bias=None)
                if not reason:
                    prediction = p['prior'][evaluation] if strategy == 'persistence' else reconstruct(p['prior'], p['points'], indices, values, evaluation)
                    row.update(metrics(prediction, truth[evaluation]))
                runs.append(row)
        summary = []
        for strategy in ('selected', 'uniform', 'random', 'persistence'):
            group = [r for r in runs if r['strategy'] == strategy]; errors = [r['rmse'] for r in group if r['status'] == 'ok']
            summary.append(dict(strategy=strategy, successful_runs=len(errors), failed_runs=len(group)-len(errors),
                                mean_rmse=float(np.mean(errors)) if errors else None, min_rmse=min(errors) if errors else None, max_rmse=max(errors) if errors else None))
        out = self.base(case_id, q, 'sampling_experiment')
        out.update(query=q.model_dump(), plan=plan, evaluation_count=len(p['evaluation']), runs=runs, summary=summary,
                   random_seeds=seeds, held_out_times=[m.coordinates.times[t] for t in (2, 4, 6)],
                   evaluation_coordinates=[dict(longitude=float(x), latitude=float(y)) for x, y in p['points'][p['evaluation']]])
        out['limitations'].append('Mean errors summarize successful runs only. Inspect failure counts and per-time rows; means with different success sets are not directly comparable. Persistence uses zero new measurements.')
        return out

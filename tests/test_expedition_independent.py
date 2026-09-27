"""P10 checks using scalar references and original packed provider files.

Expected reconstruction numbers are not calculated by production helpers.
Original-file checks skip explicitly on a checkout without the acquired archives.
"""
from __future__ import annotations

from array import array
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.case_store import CaseStore
from science.expedition import distances, gradient, metrics, prepare, reconstruct, select


ROOT = Path(__file__).resolve().parents[1]
CASE_IDS = ('bay-bengal-2024-01', 'arabian-sea-2024-01')
QUERY = dict(variable='temperature', depth_index=0, budget=8,
             min_spacing_km=30, objective='gradient', seed=26067)


@pytest.fixture
def client():
    return TestClient(create_app())


def post(client, cid, operation, payload):
    response = client.post(f'/api/cases/{cid}/expedition/{operation}', json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def sphere_distance(latitude_a, longitude_a, latitude_b, longitude_b, radius=6371.0088):
    """Independent scalar atan2 great-circle calculation."""
    a, b = math.radians(latitude_a), math.radians(latitude_b)
    delta = math.radians(longitude_b - longitude_a)
    cross = math.hypot(math.cos(b) * math.sin(delta),
                       math.cos(a) * math.sin(b) - math.sin(a) * math.cos(b) * math.cos(delta))
    dot = math.sin(a) * math.sin(b) + math.cos(a) * math.cos(b) * math.cos(delta)
    return radius * math.atan2(cross, dot)


def cartesian_idw(points, stations, station_residuals):
    """Independent unit-vector distance and direct reciprocal-weight oracle."""
    def vectors(coordinates):
        longitude, latitude = np.radians(np.array(coordinates)).T
        return np.column_stack((np.cos(latitude) * np.cos(longitude),
                                np.cos(latitude) * np.sin(longitude), np.sin(latitude)))
    a, b = vectors(points), vectors(stations)
    dot = np.einsum('ij,kj->ik', a, b)
    cross = np.linalg.norm(np.cross(a[:, None, :], b[None, :, :]), axis=2)
    d = 6371.0088 * np.arctan2(cross, dot)
    w = 1 / d**2
    return (w @ np.array(station_residuals)) / w.sum(axis=1)


@lru_cache(maxsize=16)
def original(cid, variable, time_index):
    """Decode original packed integers without production adapters/stores."""
    folder = ROOT / ('data/raw' if cid == CASE_IDS[0] else 'data/raw/arabian-sea')
    journal = folder / 'acquisition.json'
    if not journal.exists():
        pytest.skip('Original provider archive is absent; acquire it to run the independent source check.')
    records = sorted((r for r in json.loads(journal.read_text())['files']
                      if r['archive_kind'] == 'packed_source_subset_reconstructed_as_netcdf'),
                     key=lambda r: r['time'])
    record = records[time_index]
    path = ROOT / record['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
    import netCDF4
    with netCDF4.Dataset(path) as source:
        v = source['water_temp' if variable == 'temperature' else 'salinity']
        v.set_auto_maskandscale(False)
        packed = np.asarray(v[:])[0]
        decoded = packed.astype('float64') * float(v.scale_factor) + float(v.add_offset)
        decoded[packed == v._FillValue] = np.nan
        return decoded, tuple(float(x) for x in source['lat'][:]), tuple(float(x) for x in source['lon'][:]), tuple(float(x) for x in source['depth'][:])


def test_scalar_geometry_reference_and_high_latitude_convergence():
    locations = np.array([[0., 0.], [1., 0.], [0., 60.], [1., 60.]])
    result = distances(locations, locations)
    assert result[0, 1] == pytest.approx(6371.0088 * math.pi / 180, abs=1e-10)
    assert 0.49 < result[2, 3] / result[0, 1] < 0.51
    for i, a in enumerate(locations):
        for j, b in enumerate(locations):
            assert result[i, j] == pytest.approx(sphere_distance(a[1], a[0], b[1], b[0]), abs=1e-10)


def test_exact_idw_fixtures_zero_distance_constant_residual_and_sign():
    # Targets at lon=0 and lon=1. Stations at -1 and3 bracket lon1 symmetrically.
    points = np.array([[-1., 0.], [3., 0.], [1., 0.], [0., 0.]])
    prior = np.array([10., 20., 30., 30.])
    answer = reconstruct(prior, points, [0, 1], [12., 26.], [2, 3, 0, 1])
    assert answer[0] == pytest.approx(34., abs=1e-12)
    # Target0 is distances1 and3: residual (2+6/9)/(1+1/9)=2.4.
    assert answer[1] == pytest.approx(32.4, abs=1e-12)
    assert answer[2:].tolist() == [12., 26.]
    points[1] = [2., 0.]
    unequal = reconstruct(prior, points, [0, 1], [12., 26.], [3])
    assert unequal[0] == pytest.approx(32.8, abs=1e-12)
    constant = reconstruct(prior, points, [0, 1], [13., 23.], [2, 3])
    np.testing.assert_allclose(constant, [33., 33.], rtol=0, atol=1e-12)
    unchanged = reconstruct(prior, points, [0, 1], [10., 20.], [2, 3])
    np.testing.assert_array_equal(unchanged, prior[[2, 3]])
    result = metrics([12., 11.], [10., 12.])
    assert result == pytest.approx(dict(rmse=math.sqrt(2.5), mae=1.5, bias=.5))


def test_gradient_uses_coordinate_distances_and_missing_neighbor_is_not_filled():
    lon = np.array([0., 1., 3.]); lat = np.array([0., 1., 2.])
    field = np.array([[0., 2., 6.], [0., 2., 6.], [0., 2., 6.]])
    result = gradient(field, lon, lat)
    expected = 6 / sphere_distance(1., 0., 1., 3.)
    assert result[1, 1] == pytest.approx(expected, abs=1e-12)
    field[1, 2] = np.nan
    assert math.isnan(gradient(field, lon, lat)[1, 1])


@pytest.mark.parametrize('scale', [1., 1e-6, 1e-12])
def test_two_component_gradient_against_three_four_five_reference(scale):
    # At the equator the central east and north spans have equal arc length.
    # Values change by6 and8 over those spans, giving norm10/span.
    lon = np.array([-1., 0., 1.]); lat = np.array([-1., 0., 1.])
    field = scale * (3 * lon[None, :] + 4 * lat[:, None])
    span = 6371.0088 * math.pi / 90
    expected = 10 * scale / span
    actual = gradient(field, lon, lat)[1, 1]
    assert actual == pytest.approx(expected, rel=5e-15, abs=0)


def test_prior_lattice_and_spacing_failure_have_no_false_success():
    prior = np.ones((7, 7)); coordinates = np.arange(7, dtype=float)
    prepared = prepare(prior, coordinates, coordinates)
    assert set(prepared['candidates']) == {0, 6, 42, 48}
    assert set(prepared['candidates']).isdisjoint(prepared['evaluation'])
    assert len(prepared['evaluation']) == 45
    chosen = select(prepared, budget=3, spacing=10000, strategy='coverage')
    assert len(chosen) == 1
    prior[0, 0] = np.nan
    changed = prepare(prior, coordinates, coordinates)
    assert 0 not in changed['candidates'] and 0 not in changed['evaluation']


@pytest.mark.parametrize('cid', CASE_IDS)
def test_all_reported_run_metrics_against_original_source_and_cartesian_oracle(client, cid):
    result = post(client, cid, 'experiment', QUERY)
    prior3, latitudes, longitudes, _ = original(cid, 'temperature', 0)
    prior = prior3[0]
    lat_index = {value: i for i, value in enumerate(latitudes)}
    lon_index = {value: i for i, value in enumerate(longitudes)}
    all_eval = result['evaluation_coordinates']
    for run in result['runs']:
        assert run['status'] == 'ok', run
        truth3, _, _, _ = original(cid, 'temperature', run['time_index'])
        truth = truth3[0]
        evaluated = [(p['longitude'], p['latitude'], lat_index[p['latitude']], lon_index[p['longitude']])
                     for p in all_eval if math.isfinite(truth[lat_index[p['latitude']], lon_index[p['longitude']]])]
        target = np.array([truth[y, x] for _, _, y, x in evaluated])
        prediction = np.array([prior[y, x] for _, _, y, x in evaluated])
        if run['strategy'] != 'persistence':
            indices = [divmod(int(name[1:]), len(longitudes)) for name in run['station_ids']]
            station_coordinates = [(longitudes[x], latitudes[y]) for y, x in indices]
            simulated = [float(truth[y, x]) for y, x in indices]
            assert run['station_values'] == simulated
            residuals = [truth[y, x] - prior[y, x] for y, x in indices]
            prediction += cartesian_idw([(lo, la) for lo, la, _, _ in evaluated], station_coordinates, residuals)
        residual = prediction - target
        count = len(residual)
        assert run['evaluation_count'] == count
        expected = dict(rmse=math.sqrt(math.fsum(float(x)**2 for x in residual) / count),
                        mae=math.fsum(abs(float(x)) for x in residual) / count,
                        bias=math.fsum(float(x) for x in residual) / count)
        for name, value in expected.items():
            assert run[name] == pytest.approx(value, abs=2e-12, rel=2e-12)


@pytest.mark.parametrize('cid', CASE_IDS)
@pytest.mark.parametrize('variable,depth_index,budget', [('temperature', 0, 8), ('salinity', 19, 5)])
def test_native_prior_candidates_budget_spacing_and_reserved_targets(client, cid, variable, depth_index, budget):
    query = {**QUERY, 'variable': variable, 'depth_index': depth_index, 'budget': budget}
    plan = post(client, cid, 'plan', query)
    source, latitudes, longitudes, depths = original(cid, variable, 0)
    assert plan['depth_m'] == depths[depth_index]
    assert plan['prior_time'] == '2024-01-07T00:00:00Z'
    assert plan['fulfilled'] is True
    assert len(plan['stations']) == budget
    assert len({s['id'] for s in plan['stations']}) == budget
    candidate_ids = {c['id'] for c in plan['candidates']}
    for candidate in plan['candidates']:
        y, x = candidate['y_index'], candidate['x_index']
        assert candidate['latitude'] == latitudes[y]
        assert candidate['longitude'] == longitudes[x]
        assert candidate['prior_value'] == source[depth_index, y, x]
    for i, station in enumerate(plan['stations']):
        assert station['id'] in candidate_ids
        assert station['rationale']
        for other in plan['stations'][:i]:
            distance = sphere_distance(station['latitude'], station['longitude'], other['latitude'], other['longitude'])
            # Radius differences of a few metres are not a spacing loophole.
            assert distance + 1e-7 >= query['min_spacing_km']
    experiment = post(client, cid, 'experiment', query)
    candidates = {(c['longitude'], c['latitude']) for c in plan['candidates']}
    evaluations = {(c['longitude'], c['latitude']) for c in experiment['evaluation_coordinates']}
    assert candidates.isdisjoint(evaluations)
    assert len(evaluations) == experiment['evaluation_count'] > 0
    assert set(experiment['held_out_times']) == {'2024-01-08T00:00:00Z', '2024-01-09T00:00:00Z', '2024-01-10T00:00:00Z'}
    assert len(experiment['random_seeds']) == 5
    assert len(experiment['runs']) == 24
    for run in experiment['runs']:
        assert run['status'] == 'ok', run
        assert run['evaluation_count'] == len(evaluations)
        assert run['budget'] == (0 if run['strategy'] == 'persistence' else budget)
        assert len(run['station_ids']) == run['budget']
        assert set(run['station_ids']).issubset(candidate_ids)


@pytest.mark.parametrize('cid', CASE_IDS)
def test_station_planner_cannot_read_future_fields(client, monkeypatch, cid):
    original_read = CaseStore._read_array
    calls = []
    def prior_only(self, case_id, representation, variable, time_index):
        calls.append(time_index)
        assert time_index == 0, 'The planner attempted to read future data.'
        return original_read(self, case_id, representation, variable, time_index)
    monkeypatch.setattr(CaseStore, '_read_array', prior_only)
    for objective in ('gradient', 'coverage'):
        for seed in (0, 26067):
            plan = post(client, cid, 'plan', {**QUERY, 'objective': objective, 'seed': seed})
            assert plan['fulfilled']
    assert calls and set(calls) == {0}


@pytest.mark.parametrize('cid', CASE_IDS)
def test_constant_temporal_residual_reconstructs_and_persistence_does_not(client, monkeypatch, cid):
    original_read = CaseStore._read_array
    def changed_future(self, case_id, representation, variable, time_index):
        prior = np.asarray(original_read(self, case_id, representation, variable, 0), dtype='float64')
        return array('d', prior + float(time_index))
    monkeypatch.setattr(CaseStore, '_read_array', changed_future)
    result = post(client, cid, 'experiment', QUERY)
    for run in result['runs']:
        assert run['status'] == 'ok', run
        if run['strategy'] == 'persistence':
            assert run['rmse'] == pytest.approx(float(run['time_index']), abs=1e-12)
            assert run['mae'] == pytest.approx(float(run['time_index']), abs=1e-12)
            assert run['bias'] == pytest.approx(-float(run['time_index']), abs=1e-12)
        else:
            assert run['rmse'] == pytest.approx(0, abs=1e-12)
            assert run['mae'] == pytest.approx(0, abs=1e-12)
            assert run['bias'] == pytest.approx(0, abs=1e-12)


def test_future_mask_does_not_refill_selected_station_or_hide_failure(client, monkeypatch):
    cid = CASE_IDS[0]
    plan = post(client, cid, 'plan', QUERY)
    lost = plan['stations'][0]
    original_read = CaseStore._read_array
    def missing_future(self, case_id, representation, variable, time_index):
        values = np.array(original_read(self, case_id, representation, variable, time_index), copy=True)
        if time_index:
            values[lost['y_index'] * 63 + lost['x_index']] = np.nan
        return array('d', values)
    monkeypatch.setattr(CaseStore, '_read_array', missing_future)
    result = post(client, cid, 'experiment', QUERY)
    assert result['plan']['stations'] == plan['stations']
    failed = [run for run in result['runs'] if run['strategy'] == 'selected']
    assert len(failed) == 3
    for run in failed:
        assert run['status'] == 'failed'
        assert run['reason']
        assert run['rmse'] is None and run['mae'] is None
        assert run['station_ids'] == [station['id'] for station in plan['stations']]
    summary = next(row for row in result['summary'] if row['strategy'] == 'selected')
    assert summary['failed_runs'] == 3 and summary['successful_runs'] == 0


def test_all_designs_are_frozen_before_future_data_load(monkeypatch):
    import api.expedition_store as store_module
    original_select = store_module.select
    original_read = CaseStore._read_array
    selection_events = []
    def select_spy(*args, **kwargs):
        result = original_select(*args, **kwargs)
        selection_events.append(tuple(result))
        return result
    def read_spy(self, cid, representation, variable, time_index):
        if time_index > 0:
            # One visible plan plus selected, uniform and five random designs.
            assert len(selection_events) == 8
        return original_read(self, cid, representation, variable, time_index)
    monkeypatch.setattr(store_module, 'select', select_spy)
    monkeypatch.setattr(CaseStore, '_read_array', read_spy)
    result = post(TestClient(create_app()), CASE_IDS[0], 'experiment', QUERY)
    assert len(result['runs']) == 24


def test_hidden_target_mutation_changes_scores_but_not_reconstruction(monkeypatch):
    import api.expedition_store as store_module
    original_reconstruct = store_module.reconstruct
    original_read = CaseStore._read_array
    predictions = []
    def reconstruction_spy(*args, **kwargs):
        result = original_reconstruct(*args, **kwargs)
        predictions.append(result.copy())
        return result
    monkeypatch.setattr(store_module, 'reconstruct', reconstruction_spy)
    baseline = post(TestClient(create_app()), CASE_IDS[0], 'experiment', QUERY)
    first_predictions = predictions.copy()
    predictions.clear()
    candidate_indices = {c['y_index'] * 63 + c['x_index'] for c in baseline['plan']['candidates']}
    def changed_evaluation(self, cid, representation, variable, time_index):
        values = np.array(original_read(self, cid, representation, variable, time_index), copy=True)
        if time_index:
            # All measured candidates stay unchanged; only unmeasured points change.
            for index in range(76 * 63):
                if index not in candidate_indices:
                    values[index] += 10
        return array('d', values)
    monkeypatch.setattr(CaseStore, '_read_array', changed_evaluation)
    altered = post(TestClient(create_app()), CASE_IDS[0], 'experiment', QUERY)
    assert altered['plan'] == baseline['plan']
    assert len(predictions) == len(first_predictions) == 21
    for before, after in zip(first_predictions, predictions):
        np.testing.assert_array_equal(before, after)
    for before, after in zip(baseline['runs'], altered['runs']):
        assert before['station_ids'] == after['station_ids']
        assert before['station_values'] == after['station_values']
        assert after['rmse'] > before['rmse']
        assert after['bias'] == pytest.approx(before['bias'] - 10, abs=1e-12)


@pytest.mark.parametrize('cid', CASE_IDS)
@pytest.mark.parametrize('variable,depth_index,time_index', [('temperature', 0, 2), ('salinity', 19, 4), ('temperature', 32, 6)])
def test_virtual_survey_samples_original_source_and_scalar_geometry(client, cid, variable, depth_index, time_index):
    source, latitudes, longitudes, depths = original(cid, variable, time_index)
    start = [longitudes[0], latitudes[0]]
    end = [longitudes[-1], latitudes[-1]]
    query = dict(variable=variable, depth_index=depth_index, time_index=time_index, start=start, end=end, stations=5)
    result = post(client, cid, 'survey', query)
    assert result['simulated'] is True
    assert result['depth_m'] == depths[depth_index]
    cumulative = 0.0
    previous = None
    selected = []
    for index, sample in enumerate(result['samples']):
        fraction = index / 4
        longitude = start[0] + fraction * (end[0] - start[0])
        latitude = start[1] + fraction * (end[1] - start[1])
        distances_to_grid = [(sphere_distance(latitude, longitude, la, lo), y, x)
                             for y, la in enumerate(latitudes) for x, lo in enumerate(longitudes)]
        minimum = min(row[0] for row in distances_to_grid)
        # A 0.1-micrometre tolerance resolves floating roundoff in exact
        # geometric ties. Source row order wins, independent of atan2 noise.
        offset, y, x = next(row for row in distances_to_grid if row[0] <= minimum + 1e-10)
        assert sample['requested_longitude'] == pytest.approx(longitude, abs=1e-12)
        assert sample['requested_latitude'] == pytest.approx(latitude, abs=1e-12)
        assert (sample['y_index'], sample['x_index']) == (y, x)
        assert sample['longitude'] == longitudes[x] and sample['latitude'] == latitudes[y]
        expected = source[depth_index, y, x]
        assert sample['value'] == (float(expected) if math.isfinite(expected) else None)
        if previous is not None:
            cumulative += sphere_distance(previous[1], previous[0], latitude, longitude)
        assert sample['offset_km'] == pytest.approx(offset, rel=1e-12, abs=1e-10)
        assert sample['distance_km'] == pytest.approx(cumulative, rel=1e-12, abs=1e-10)
        previous = (longitude, latitude)
        selected.append((y, x))
    assert result['unique_columns'] == len(set(selected))

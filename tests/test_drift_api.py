"""P11 request bounds, transport, cancellation and portable result contracts.

These checks establish API consistency. Independent numerical/source and full
Parcels reference checks live in test_drift_independent.py.
"""
from copy import deepcopy
import asyncio
import csv
from datetime import datetime, timedelta
import io
import json
import math
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.case_store import CaseStore
from api.drift_store import DriftStore
from science.contracts import UnsupportedData
from science.drift_contracts import DriftQuery, METHOD
from science.investigations import fingerprint

ROOT = Path(__file__).resolve().parents[1]
CASES = ('bay-bengal-2024-01', 'arabian-sea-2024-01')


@pytest.fixture(scope='module')
def application():
    return create_app()


@pytest.fixture
def client(application, request):
    # Independent scientific cases must not spend each other's abuse budget.
    # Keep the real defaults and shared source caches; every request within one
    # test still has the same peer and passes through the production guard.
    with TestClient(application, client=(request.node.nodeid, 50000)) as session:
        yield session


@pytest.fixture(scope='module')
def cases():
    return CaseStore(ROOT / 'casepacks')


def query(cases, case, **overrides):
    c = cases.require(case)[0].coordinates
    x, y = (c.longitude[0] + c.longitude[-1]) / 2, (c.latitude[0] + c.latitude[-1]) / 2
    return dict(release=dict(kind='box', bounds=[x-.15, y-.15, x+.15, y+.15]),
                depth_index=0, start_time_index=0, duration_hours=2, particle_count=6,
                seed=26067, dt_seconds=600, target_bounds=[x-.25, y-.25, x+.25, y+.25], **overrides)


def post_run(client, case, q):
    response = client.post(f'/api/cases/{case}/drift/run', json=q)
    assert response.status_code == 200, response.text
    return response.json()


def records_from(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    return value['records'] if isinstance(value, dict) and 'records' in value else list(value.values()) if isinstance(value, dict) else value


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('depth', [0, 32])
@pytest.mark.parametrize('dt', [300, 600, 1200])
def test_results_keep_depth_forcing_cadence_bounds_and_summary(client, cases, case, depth, dt):
    q = query(cases, case)
    q.update(depth_index=depth, dt_seconds=dt, start_time_index=2)
    out = post_run(client, case, q)
    m, digest = cases.require(case)
    assert out['method_version'] == METHOD and out['simulated'] is True
    assert out['manifest_sha256'] == digest and out['depth_m'] == m.coordinates.depth_m[depth]
    assert out['start_time'] == m.coordinates.times[2]
    assert out['forcing_times'] == m.coordinates.times
    assert out['completed_steps'] == out['total_steps'] == 7200 // dt
    assert out['output_interval_seconds'] == math.lcm(1800, dt)
    assert out['query'] == q
    assert len(out['particles']) == out['summary']['released'] == 6
    assert out['summary']['valid_releases'] > 0
    assert sum(out['summary'][s] for s in ('completed', 'left_domain', 'missing_velocity', 'invalid_release')) == 6
    assert out['summary']['arrival_fraction'] == out['summary']['arrived'] / 6
    for p in out['particles']:
        points = p['points']
        assert points[0] == dict(elapsed_seconds=0, longitude=p['release_longitude'], latitude=p['release_latitude'])
        times = [r['elapsed_seconds'] for r in points]
        assert times == sorted(set(times)) and times[-1] == p['stop_elapsed_seconds']
        assert all(t % out['output_interval_seconds'] == 0 for t in times[1:-1])
        assert p['distance_km'] >= 0
        assert p['arrival_elapsed_seconds'] is None or 0 <= p['arrival_elapsed_seconds'] <= p['stop_elapsed_seconds']
        assert all(out['bounds'][0] <= r['longitude'] <= out['bounds'][2] and out['bounds'][1] <= r['latitude'] <= out['bounds'][3] for r in points)
        if p['status'] == 'completed':
            assert p['stop_elapsed_seconds'] == 7200 and p['stop_reason'] is None
    background = client.get(f'/api/cases/{case}/drift/context?depth_index={depth}&time_index=2')
    assert background.status_code == 200 and background.json() == out['background']


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('depth,time', [(0, 0), (32, 6)])
def test_context_uses_exact_native_coordinates_components_and_joint_missingness(client, cases, case, depth, time):
    m, digest = cases.require(case)
    c = m.coordinates
    response = client.get(f'/api/cases/{case}/drift/context?depth_index={depth}&time_index={time}')
    assert response.status_code == 200
    context = response.json()
    assert context['manifest_sha256'] == digest and context['model_time'] == c.times[time]
    x = [c.longitude.index(v) for v in context['longitude']]
    y = [c.latitude.index(v) for v in context['latitude']]
    assert context['shape'] == [len(y), len(x)]
    assert x[0] == y[0] == 0 and x[-1] == len(c.longitude)-1 and y[-1] == len(c.latitude)-1
    shape = (len(c.depth_m), len(c.latitude), len(c.longitude))
    for name, key in [('eastward_velocity', 'u'), ('northward_velocity', 'v')]:
        native = np.asarray(cases._read_array(case, 'analytical', name, time)).reshape(shape)[depth][np.ix_(y, x)].ravel()
        assert context[key] == [float(v) if np.isfinite(v) else None for v in native]


@pytest.mark.parametrize('patch', [
    {'particle_count': 0}, {'particle_count': 65}, {'particle_count': 1.5}, {'particle_count': True},
    {'duration_hours': 0}, {'duration_hours': 73}, {'duration_hours': 1.5},
    {'dt_seconds': 60}, {'depth_index': 33}, {'depth_index': -1}, {'start_time_index': 7},
    {'seed': -1}, {'seed': 2147483648}, {'diffusion': 1},
    {'release': {'kind': 'point', 'longitude': 'NaN', 'latitude': 13}},
    {'release': {'kind': 'point', 'longitude': 'bad coordinate', 'latitude': 13}},
    {'release': {'kind': 'point', 'longitude': 86, 'latitude': 13, 'depth': 10}},
    {'release': {'kind': 'box', 'bounds': [86, 13, 89]}},
    {'release': {'kind': 'line', 'bounds': [86, 13, 89, 14]}},
    {'target_bounds': [86, 13, 'Infinity', 14]},
])
def test_unsupported_requests_rejected_without_coercing_missing_values(client, cases, patch):
    response = client.post(f'/api/cases/{CASES[0]}/drift/run', json={**query(cases, CASES[0]), **patch})
    assert response.status_code == 422 and response.json()['error']['code'] == 'invalid_request'


@pytest.mark.parametrize('endpoint', ['run', 'stream'])
@pytest.mark.parametrize('patch,code', [
    ({'start_time_index': 6, 'duration_hours': 1}, 'forcing_exhausted'),
    ({'start_time_index': 5, 'duration_hours': 13}, 'forcing_exhausted'),
    ({'release': {'kind': 'point', 'longitude': 0, 'latitude': 0}}, 'outside_coverage'),
    ({'release': {'kind': 'box', 'bounds': [86, 13, 86, 14]}}, 'outside_coverage'),
    ({'release': {'kind': 'box', 'bounds': [89, 14, 86, 13]}}, 'outside_coverage'),
    ({'target_bounds': [86, 13, 86, 14]}, 'invalid_target'),
    ({'target_bounds': [0, 0, 1, 1]}, 'invalid_target'),
])
def test_semantic_errors_are_identical_before_stream_opens(client, cases, endpoint, patch, code):
    response = client.post(f'/api/cases/{CASES[0]}/drift/{endpoint}', json={**query(cases, CASES[0]), **patch})
    assert response.status_code == 422 and response.json()['error']['code'] == code


def test_unknown_case_and_context_limits(client, cases):
    assert client.post('/api/cases/unknown/drift/run', json=query(cases, CASES[0])).json()['error']['code'] == 'case_not_found'
    for suffix in ('depth_index=33', 'time_index=7', 'depth_index=-1'):
        response = client.get(f'/api/cases/{CASES[0]}/drift/context?{suffix}')
        assert response.status_code == 422


@pytest.mark.parametrize('case', CASES)
def test_stream_is_real_ordered_progress_and_exact_same_result_as_json(client, cases, case):
    q = query(cases, case)
    q.update(duration_hours=12, seed=817342)
    response = client.post(f'/api/cases/{case}/drift/stream', json=q)
    assert response.status_code == 200 and response.headers['content-type'].startswith('application/x-ndjson')
    assert response.headers['content-encoding'] == 'identity'
    assert response.headers['x-accel-buffering'] == 'no'
    assert response.headers['cache-control'] == 'no-store, no-transform'
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['type'] == 'result' and all(e['type'] == 'progress' for e in events[:-1])
    progress = [e['completed_steps'] for e in events[:-1]]
    assert progress[0] == 0 and progress[-1] == 72 and progress == sorted(set(progress))
    assert all(b-a <= 12 for a, b in zip(progress, progress[1:]))
    assert events[-1]['result'] == post_run(client, case, q)
    cached = client.post(f'/api/cases/{case}/drift/stream', json=q)
    cached_events = [json.loads(line) for line in cached.text.splitlines()]
    assert cached_events[-1]['result'] == events[-1]['result']


def test_closing_partial_generator_never_caches_partial_results(cases):
    store = DriftStore(cases)
    q = DriftQuery(**query(cases, CASES[0]))
    stream = store.stream(CASES[0], q)
    assert next(stream) == dict(type='progress', completed_steps=0, total_steps=12)
    assert next(stream) == dict(type='progress', completed_steps=12, total_steps=12)
    stream.close()
    assert not store.cache, 'Even last progress is not a completed result'
    rerun = list(store.stream(CASES[0], q))
    assert rerun[0]['completed_steps'] == 0 and rerun[-1]['type'] == 'result'
    assert len(store.cache) == 1
    assert list(store.stream(CASES[0], q))[-1]['result'] == rerun[-1]['result']


def test_stream_scientific_failure_is_an_explicit_error_without_result(client, cases, monkeypatch):
    def fail(_self, _case, _query):
        yield dict(type='progress', completed_steps=0, total_steps=12)
        raise UnsupportedData('source_unavailable', 'Injected checked-source failure')
    monkeypatch.setattr(DriftStore, 'stream', fail)
    response = client.post(f'/api/cases/{CASES[0]}/drift/stream', json=query(cases, CASES[0]))
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [e['type'] for e in events] == ['progress', 'error']
    assert events[-1]['code'] == 'source_unavailable'


def test_route_disconnect_closes_calculation_after_current_bounded_chunk(cases, monkeypatch):
    observed = dict(chunks=0, closed=False)
    def controlled(_self, _case, _query):
        try:
            for completed in (0, 12, 24, 36):
                observed['chunks'] += 1
                yield dict(type='progress', completed_steps=completed, total_steps=36)
            yield dict(type='result', result={'should_not_be_sent': True})
        finally:
            observed['closed'] = True
    monkeypatch.setattr(DriftStore, 'stream', controlled)
    app = create_app()
    endpoint = next(route.endpoint for route in app.routes if route.path == '/api/cases/{case_id}/drift/stream')
    class DisconnectedAfterTwoEvents:
        calls = 0
        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 2
    async def collect():
        response = await endpoint(CASES[0], DriftQuery(**query(cases, CASES[0])), DisconnectedAfterTwoEvents())
        return [json.loads(line) async for line in response.body_iterator]
    events = asyncio.run(collect())
    assert [e['completed_steps'] for e in events] == [0, 12]
    assert observed == dict(chunks=2, closed=True)
    assert all(e['type'] == 'progress' for e in events)


def assert_trajectory_csv(raw, module):
    out = module['output']
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8'))))
    expected = [(p, point) for p in out['particles'] for point in p['points']]
    assert len(rows) == len(expected)
    for row, (p, point) in zip(rows, expected):
        assert row['module'] == module['module'] and row['method_version'] == METHOD
        assert row['manifest_sha256'] == out['manifest_sha256'] and row['simulated'] == 'True'
        assert row['case_id'] == out['case_id'] and float(row['depth_m']) == out['depth_m']
        assert int(row['seed']) == out['query']['seed'] and row['start_time_utc'] == out['start_time']
        expected_time = datetime.fromisoformat(out['start_time'].replace('Z', '+00:00')) + timedelta(seconds=point['elapsed_seconds'])
        assert datetime.fromisoformat(row['sample_time_utc'].replace('Z', '+00:00')) == expected_time
        assert int(row['particle_id']) == p['id'] and row['final_status'] == p['status']
        for key in ('elapsed_seconds', 'longitude', 'latitude'):
            assert float(row[key]) == point[key]


@pytest.mark.parametrize('case', CASES)
def test_two_different_runs_save_exactly_replay_and_export_actual_times(client, cases, case):
    a = query(cases, case)
    b = {**a, 'seed': 14, 'depth_index': 32, 'start_time_index': 3, 'dt_seconds': 1200}
    recipe = dict(mode='drift', case_id=case, query=a, comparison=b)
    response = client.post('/api/investigations/capture', json=dict(title='Drift <script> & comparison', recipe=recipe))
    assert response.status_code == 200, response.text
    record = response.json()
    assert record['replay']['sources']['methods']['drift'] == METHOD
    assert record['result_sha256'] == fingerprint(record['results'])
    assert record['document_sha256'] == fingerprint({k: v for k, v in record.items() if k != 'document_sha256'})
    assert [m['module'] for m in record['results']] == ['drift_run', 'reference_drift_run']
    for module, q in zip(record['results'], (a, b)):
        assert module['random_seed'] == q['seed'] and module['parameters'] == q
        assert module['output'] == post_run(client, case, q)
    replay = client.post('/api/investigations/replay', json=record['replay'])
    assert replay.status_code == 200 and replay.json()['results'] == record['results']
    assert len(record['references'][0]['files']) == 7
    for format in ('csv', 'html', 'zip'):
        response = client.post('/api/investigations/export', json=dict(replay=record['replay'], format=format))
        assert response.status_code == 200, response.text[:200]
        if format == 'csv':
            assert_trajectory_csv(response.content, record['results'][0])
        elif format == 'html':
            assert '&lt;script&gt;' in response.text and '<script>' not in response.text
            assert 'real-world probabilities' in response.text and 'Twelve-hourly source snapshots' in response.text
        else:
            with ZipFile(io.BytesIO(response.content)) as archive:
                assert {'investigation.json', 'settings.json', 'report.html', 'SOURCES.json', 'source-credits.txt',
                        'drift-trajectories.csv', 'drift-particles.csv', 'reference-drift-trajectories.csv', 'reference-drift-particles.csv'} <= set(archive.namelist())
                assert json.loads(archive.read('investigation.json'))['results'] == record['results']
                assert json.loads(archive.read('settings.json')) == record['replay']
                assert 'HYCOM' in archive.read('source-credits.txt').decode('utf-8')
                for module, prefix in zip(record['results'], ('drift', 'reference-drift')):
                    assert_trajectory_csv(archive.read(prefix+'-trajectories.csv'), module)
                    rows = list(csv.DictReader(io.StringIO(archive.read(prefix+'-particles.csv').decode('utf-8'))))
                    for p, row in zip(module['output']['particles'], rows):
                        assert row['simulated'] == 'True' and row['status'] == p['status']
                        assert (float(row['arrival_elapsed_seconds']) if row['arrival_elapsed_seconds'] else None) == p['arrival_elapsed_seconds']
                        assert float(row['distance_km']) == p['distance_km']


@pytest.mark.parametrize('kind', ['source', 'method', 'recipe', 'result'])
def test_saved_identity_guards_cannot_restore_changed_calculation(client, cases, kind):
    recipe = dict(mode='drift', case_id=CASES[0], query=query(cases, CASES[0]), comparison=None)
    record = client.post('/api/investigations/capture', json=dict(title='Identity check', recipe=recipe)).json()
    replay = deepcopy(record['replay'])
    if kind == 'source': replay['sources']['model_manifest_sha256'] = '0'*64
    elif kind == 'method': replay['sources']['methods']['drift'] = 'p11-drift-incompatible'
    elif kind == 'recipe': replay['recipe']['query']['seed'] += 1
    else: replay['expected_result_sha256'] = '0'*64
    if kind in ('source', 'method'):
        replay['expected_recipe_sha256'] = fingerprint(dict(recipe=replay['recipe'], sources=replay['sources']))
    response = client.post('/api/investigations/replay', json=replay)
    assert response.status_code == 422 and response.json()['error']['code'] == kind+'_mismatch'


def test_identical_comparison_and_capture_source_mismatch_rejected(client, cases):
    q = query(cases, CASES[0])
    recipe = dict(mode='drift', case_id=CASES[0], query=q, comparison=q)
    assert client.post('/api/investigations/capture', json=dict(title='Same', recipe=recipe)).json()['error']['code'] == 'invalid_request'
    recipe['comparison'] = None
    response = client.post('/api/investigations/capture', json=dict(title='Changed source', recipe=recipe, expected_model_sha256='0'*64))
    assert response.status_code == 422 and response.json()['error']['code'] == 'source_mismatch'


@pytest.mark.parametrize('filename,count', [('p08-local-records.json', 4), ('p10-v2-local-records.json', 8)])
def test_original_p08_and_p10_results_still_replay_exactly(client, filename, count):
    records = records_from(ROOT / 'docs/evidence' / filename)
    assert len(records) == count
    for old in records:
        response = client.post('/api/investigations/replay', json=old['replay'])
        assert response.status_code == 200, response.text[:200]
        fresh = response.json()
        assert fresh['results'] == old['results'] and fresh['replay'] == old['replay']
        assert fresh['result_sha256'] == old['result_sha256']


def test_mean_uses_fixed_left_to_right_binary64_addition_across_python_versions():
    from science.drift import sequential_mean
    # Python 3.12 changed built-in sum(float) to compensated accumulation. The
    # method explicitly pins the earlier left-to-right binary64 arithmetic.
    values = [1e16, 1., 1.]
    assert sequential_mean(values) == 1e16 / 3
    assert sequential_mean(values) != math.fsum(values) / 3
    assert sequential_mean([]) is None
    assert sequential_mean([0., 0.]) == 0.
    # Actual cross-platform incident records also distinguish these reductions.
    local = records_from(ROOT/'docs/evidence/p11-api-local-records.json')
    public = records_from(ROOT/'docs/evidence/p11-api-public-records.json')
    discriminating = 0
    for a, b in zip(local, public):
        for am, bm in zip(a['results'], b['results']):
            particles = am['output']['particles']
            assert particles == bm['output']['particles']
            distances = [p['distance_km'] for p in particles if p['status'] != 'invalid_release']
            assert sequential_mean(distances) == am['output']['summary']['mean_distance_km']
            discriminating += am['output']['summary']['mean_distance_km'] != bm['output']['summary']['mean_distance_km']
    assert discriminating == 4


@pytest.mark.parametrize('filename', ['p11-api-local-records.json', 'p11-api-public-records.json'])
def test_initial_p11_archives_remain_explicitly_old_method_not_altered(client, filename):
    records = records_from(ROOT/'docs/evidence'/filename)
    assert len(records) == 8
    for saved in records:
        assert saved['replay']['sources']['methods']['drift'] == 'p11-drift-v1'
        response = client.post('/api/investigations/replay', json=saved['replay'])
        assert response.status_code == 422 and response.json()['error']['code'] == 'method_mismatch'

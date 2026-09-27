"""API, constraints, source identities and portable expedition replay."""
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile
import csv
import io
import json
import pytest
from fastapi.testclient import TestClient
from api.app import create_app
from science.investigations import fingerprint

ROOT = Path(__file__).resolve().parents[1]
CASES = ['bay-bengal-2024-01', 'arabian-sea-2024-01']
QUERY = dict(variable='temperature', depth_index=0, budget=8, min_spacing_km=30, objective='gradient', seed=26067)


@pytest.fixture(scope='module')
def client(): return TestClient(create_app())


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('variable', ['temperature','salinity'])
@pytest.mark.parametrize('depth', [0, 32])
def test_budget_spacing_native_source_and_common_targets(client, case, variable, depth):
    q = {**QUERY, 'variable':variable, 'depth_index':depth}
    r = client.post(f'/api/cases/{case}/expedition/experiment', json=q)
    assert r.status_code == 200, r.text
    out = r.json(); plan = out['plan']
    assert len(out['runs']) == 24
    assert out['depth_m'] == (0 if depth == 0 else 1000)
    assert len(plan['stations']) == q['budget'] and plan['fulfilled']
    candidates = {(r['longitude'],r['latitude']) for r in plan['candidates']}
    evaluation = {(r['longitude'],r['latitude']) for r in out['evaluation_coordinates']}
    assert not candidates & evaluation
    assert out['evaluation_count'] == len(evaluation)
    for station in plan['stations'][1:]: assert station['nearest_station_km'] >= q['min_spacing_km']
    assert all(r['status'] == 'ok' for r in out['runs'])
    for t in [2,4,6]: assert len({r['evaluation_count'] for r in out['runs'] if r['time_index']==t}) == 1
    assert all(r['budget'] == (0 if r['strategy']=='persistence' else 8) for r in out['runs'])
    assert '2024' in out['prior_time'] and 'not an operational' in out['limitations'][0]


@pytest.mark.parametrize('patch', [dict(budget=0),dict(budget=17),dict(budget=3.5),dict(depth_index=33),dict(min_spacing_km=-1),dict(min_spacing_km=151),dict(seed=-1),dict(variable='chlorophyll'),dict(objective='forecast_gain'),dict(time_index=6),dict(min_spacing_km='NaN')])
def test_unbounded_or_unsupported_plan_rejected(client,patch):
    r=client.post(f'/api/cases/{CASES[0]}/expedition/plan',json={**QUERY,**patch})
    assert r.status_code==422


def test_unfilled_constraints_retained_and_persistence_separate(client):
    out=client.post(f'/api/cases/{CASES[0]}/expedition/experiment',json={**QUERY,'budget':16,'min_spacing_km':150}).json()
    assert not out['plan']['fulfilled'] and out['plan']['reason']
    failed=[r for r in out['runs'] if r['strategy']!='persistence']
    assert failed and all(r['status']=='failed' and r['rmse'] is None for r in failed)
    assert all(r['status']=='ok' and r['budget']==0 for r in out['runs'] if r['strategy']=='persistence')


@pytest.mark.parametrize('case',CASES)
def test_survey_capture_replay_and_exports(client,case):
    manifest=client.get(f'/api/cases/{case}').json();c=manifest['coordinates']
    survey=dict(variable='temperature',depth_index=0,time_index=4,start=[c['longitude'][0],c['latitude'][0]],end=[c['longitude'][-1],c['latitude'][-1]],stations=25)
    recipe=dict(mode='expedition',case_id=case,query=QUERY,survey=survey,experiment=True)
    response=client.post('/api/investigations/capture',json=dict(title='Virtual expedition <script>',recipe=recipe))
    assert response.status_code==200,response.text
    record=response.json();assert len(record['results'])==3
    assert record['replay']['sources']['methods']['expedition']=='p10-sampling-v2'
    assert record['results'][-1]['random_seed']==QUERY['seed']
    assert record['result_sha256']==fingerprint(record['results'])
    replay=client.post('/api/investigations/replay',json=record['replay'])
    assert replay.status_code==200 and replay.json()['results']==record['results']
    result=record['results'][1]['output'];assert result['simulated'] and len(result['samples'])==25
    assert all(r['distance_km']>=0 and r['offset_km']>=0 for r in result['samples'])
    assert len(record['references'][0]['files'])>0
    for format in ['csv','html','zip']:
        response=client.post('/api/investigations/export',json={'replay':record['replay'],'format':format})
        assert response.status_code==200,response.text
        if format=='csv':
            rows=list(csv.DictReader(io.StringIO(response.text)))
            assert len(rows)==24 and all(r['simulated']=='True' and r['sample_time_utc']==r['model_time'] for r in rows)
        elif format=='html': assert '&lt;script&gt;' in response.text and 'Reconstruction errors do not establish' in response.text
        else:
            with ZipFile(io.BytesIO(response.content)) as archive:
                assert {'stations.csv','simulated-survey.csv','reconstruction-benchmark.csv','source-credits.txt'}<=set(archive.namelist())
                assert json.loads(archive.read('investigation.json'))['result_sha256']==record['result_sha256']
                samples=list(csv.DictReader(io.StringIO(archive.read('simulated-survey.csv').decode())))
                assert all(r['sample_time_utc']==c['times'][4] and r['module']=='virtual_survey' for r in samples)
                assert all(r['simulated']=='True' and r['method_version']=='p10-sampling-v2' and r['manifest_sha256']==record['replay']['sources']['model_manifest_sha256'] for r in samples)
    bad=deepcopy(record['replay']);bad['recipe']['query']['seed']+=1
    assert client.post('/api/investigations/replay',json=bad).json()['error']['code']=='recipe_mismatch'


def test_survey_outside_and_incompatible_saved_source_rejected(client):
    survey=dict(variable='temperature',depth_index=0,time_index=0,start=[1,2],end=[89,14],stations=25)
    assert client.post(f'/api/cases/{CASES[0]}/expedition/survey',json=survey).status_code==422
    survey.update(start=[89,14])
    assert client.post(f'/api/cases/{CASES[0]}/expedition/survey',json=survey).status_code==422
    survey.update(start=[86,13],variable='salinity')
    recipe=dict(mode='expedition',case_id=CASES[0],query=QUERY,survey=survey,experiment=False)
    assert client.post('/api/investigations/capture',json={'title':'Incompatible','recipe':recipe}).status_code==422


def test_original_p08_records_still_replay_with_unchanged_methods(client):
    records=json.loads((ROOT/'docs/evidence/p08-local-records.json').read_text())
    # The retained verification artifact is keyed by recipe mode.
    if isinstance(records,dict): records=list(records.values())
    assert len(records) == 4 and all(isinstance(r,dict) and 'replay' in r for r in records)
    for record in records:
        r=client.post('/api/investigations/replay',json=record['replay'])
        assert r.status_code==200,r.text
        assert r.json()['result_sha256']==record['result_sha256']


def test_initial_p10_method_is_explicitly_rejected_without_reinterpreting_record(client):
    records=json.loads((ROOT/'docs/evidence/p10-public-v1-records.json').read_text())
    assert len(records)==8
    for record in records:
        r=client.post('/api/investigations/replay',json=record['replay'])
        assert r.status_code==422 and r.json()['error']['code']=='method_mismatch'

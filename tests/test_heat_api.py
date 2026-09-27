"""Heat transport, applied-selection, source identity and export contracts.

Scientific reference tests live separately in test_heat_independent.py.
"""
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from api.app import create_app
from api.case_store import CaseStore
from api.heat_store import HeatStore
from api.instrument_store import InstrumentStore
from science.contracts import UnsupportedData
from science.heat_contracts import HeatQuery, METHOD
from science.investigations import fingerprint

ROOT = Path(__file__).resolve().parents[1]
CASES = ('bay-bengal-2024-01', 'arabian-sea-2024-01')
LOCATIONS = [('bay-bengal-2024-01', f'bay-{p}') for p in ('west', 'center', 'east')] + [('arabian-sea-2024-01', f'arabian-{p}') for p in ('west', 'center', 'east')]


@pytest.fixture
def client():
    assert (ROOT/'casepacks/heat/manifest.json').is_file(), 'Real prepared daily SST pack is required for this acceptance suite.'
    return TestClient(create_app())


@pytest.fixture(scope='module')
def cases():
    return CaseStore(ROOT/'casepacks')


def query(location, **changes):
    return dict(location_id=location, year=2024, event_id=None, model_time_index=0, depth_limit_m=300, **changes)


def analyse(client, case, q):
    response=client.post(f'/api/cases/{case}/heat/analyse', json=q)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('case', CASES)
def test_catalog_preserves_case_scope_source_selection_and_api_headers(client, cases, case):
    response=client.get(f'/api/cases/{case}/heat/catalog')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    out=response.json()
    assert out['method_version'] == METHOD and out['case_id'] == case
    assert len(out['locations']) == 3 and all(p['case_id'] == case for p in out['locations'])
    assert out['model_manifest_sha256'] == cases.require(case)[1]
    assert out['heat_manifest_sha256'] == hashlib.sha256((ROOT/'casepacks/heat/manifest.json').read_bytes()).hexdigest()
    assert out['baseline_period'] == [1982,2011] and out['years'] == [2023,2024]
    assert out['default_query']['location_id'].endswith('-center')
    assert out['model_times'] == cases.require(case)[0].coordinates.times
    assert all(p['selection_rule'] and p['latitude'] is not None and p['longitude'] is not None for p in out['locations'])


@pytest.mark.parametrize('case,location', LOCATIONS)
@pytest.mark.parametrize('year', [2023,2024])
def test_real_annual_series_events_and_depth_availability(client, cases, case, location, year):
    q=query(location);q['year']=year
    out=analyse(client,case,q)
    assert out['method_version'] == METHOD and out['case_id'] == case
    assert len(out['series']) == (366 if year==2024 else 365)
    assert out['series'][0]['date'] == f'{year}-01-01' and out['series'][-1]['date'] == f'{year}-12-31'
    assert len(out['baseline']['threshold_c']) == len(out['baseline']['seasonal_mean_c']) == 366
    for row in out['series']:
        assert row['sst_c'] is None or row['anomaly_c'] == row['sst_c']-row['seasonal_mean_c']
        assert row['exceeds_threshold'] == (row['sst_c']>row['threshold_c'] if row['sst_c'] is not None else None)
    selected=out['selected_event']
    assert out['query']['event_id'] == (selected['id'] if selected else None)
    if selected:
        assert selected in out['events'] and selected['duration_days'] >= 5
        assert selected['exceedance_days']+selected['bridged_days'] == selected['duration_days']
    if out['depth_link']['status']=='available':
        profile=out['depth_profile']
        assert profile['model_time']==cases.require(case)[0].coordinates.times[q['model_time_index']]
        assert selected['start'] <= profile['model_time'][:10] <= selected['end']
        assert profile['points'][0]['depth_m']==0 and profile['points'][-1]['depth_m']==300
        assert profile['heat_content']['reference_conservative_temperature_c']==0
        for p in out['observations']:
            original=client.get('/api/instruments/profiles/'+p['id'])
            assert original.status_code==200 and original.json()['source_sha256']==p['source_sha256']
            assert selected['start']<=p['time'][:10]<=selected['end']
    else:
        assert out['depth_profile'] is None and out['observations']==[]
    assert analyse(client,case,out['query'])==out


@pytest.mark.parametrize('change', [dict(location_id='../manifest'),dict(location_id='arabian-center'),dict(year=2026),dict(model_time_index=7),dict(model_time_index=True),dict(depth_limit_m=500),dict(event_id='invented'),dict(event_id='mhw-2024-01-01-2024-01-10'),dict(unexpected=3)])
def test_invalid_request_never_substitutes_scientific_inputs(client, change):
    q=query('bay-center');q.update(change)
    response=client.post('/api/cases/bay-bengal-2024-01/heat/analyse',json=q)
    assert response.status_code==422 and 'error' in response.json()


def test_unknown_case_and_unavailable_source_have_explicit_errors(client,tmp_path):
    assert client.get('/api/cases/not-a-case/heat/catalog').status_code==404
    store=HeatStore(CaseStore(tmp_path),InstrumentStore(tmp_path/'instruments'))
    with pytest.raises(UnsupportedData, match='unavailable'):
        store.manifest()


def test_heat_source_integrity_cannot_be_bypassed(tmp_path,cases):
    source=ROOT/'casepacks/heat'
    metadata=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    selected=next(p for p in metadata['locations'] if p['id']=='bay-center')
    target=tmp_path/'heat';target.mkdir()
    (target/'manifest.json').write_bytes((source/'manifest.json').read_bytes())
    file=target/selected['path'];file.parent.mkdir(parents=True,exist_ok=True)
    file.write_bytes((source/selected['path']).read_bytes()+b' ')
    store=HeatStore(cases,InstrumentStore(ROOT/'casepacks/instruments'));store.root=target
    with pytest.raises(UnsupportedData, match='fingerprint'):
        store.source_series('bay-bengal-2024-01','bay-center')


@pytest.mark.parametrize('case,location', [(CASES[0],'bay-center'),(CASES[1],'arabian-center')])
@pytest.mark.parametrize('depth', [100,1000])
def test_applied_heat_record_replay_export_and_full_source_metadata(client,case,location,depth):
    q=query(location);q['depth_limit_m']=depth
    out=analyse(client,case,q)
    recipe=dict(mode='heat',case_id=case,query=out['query'])
    request=dict(title='Heat <script> check',recipe=recipe,expected_model_sha256=out['model_manifest_sha256'],expected_heat_manifest_sha256=out['heat_manifest_sha256'])
    response=client.post('/api/investigations/capture',json=request)
    assert response.status_code==200,response.text
    record=response.json();module=record['results'][0]
    assert module['module']=='heat_analysis' and module['output']==out and module['parameters']==recipe['query']
    assert record['replay']['sources']['heat_manifest_sha256']==out['heat_manifest_sha256']
    assert module['output_sha256']==fingerprint(out)
    replay=client.post('/api/investigations/replay',json=record['replay'])
    assert replay.status_code==200 and replay.json()['results']==record['results']
    response=client.post('/api/investigations/export',json=dict(replay=record['replay'],format='zip'))
    assert response.status_code==200,response.text
    with ZipFile(io.BytesIO(response.content)) as archive:
        rows=list(csv.DictReader(io.StringIO(archive.read('heat-surface-series.csv').decode())))
        assert len(rows)==len(out['series'])
        assert float(rows[0]['sst_c'])==out['series'][0]['sst_c']
        assert rows[0]['heat_manifest_sha256']==out['heat_manifest_sha256']
        events=list(csv.DictReader(io.StringIO(archive.read('heat-events.csv').decode())))
        assert len(events)==len(out['events'])
        assert 'heat-climatology.csv' in archive.namelist()
        if out['depth_profile']:
            profile=list(csv.DictReader(io.StringIO(archive.read('heat-depth-profile.csv').decode())))
            assert float(profile[-1]['depth_m'])==depth
            assert 'heat-depth-integral.csv' in archive.namelist() and 'heat-mixed-layer.csv' in archive.namelist()
        report=archive.read('report.html').decode()
        assert '<script>' not in report and '&lt;script&gt;' in report
        assert 'subsurface heatwave' in report and '1982' in report
        sources=json.loads(archive.read('SOURCES.json'))
        assert any(p.get('heat_manifest_sha256')==out['heat_manifest_sha256'] for p in sources)
    direct=client.post('/api/investigations/export',json=dict(replay=record['replay'],format='csv'))
    assert 'heat-surface-series.csv' in direct.headers['content-disposition']
    assert list(csv.DictReader(io.StringIO(direct.text)))==rows


@pytest.mark.parametrize('kind',['heat_source','method','result','stale_capture'])
def test_changed_identity_fails_without_silent_recalculation_substitution(client,kind):
    out=analyse(client,CASES[0],query('bay-center'))
    request=dict(title='Source check',recipe=dict(mode='heat',case_id=CASES[0],query=out['query']),expected_heat_manifest_sha256=out['heat_manifest_sha256'])
    if kind=='stale_capture':
        request['expected_heat_manifest_sha256']='0'*64
        response=client.post('/api/investigations/capture',json=request)
        assert response.status_code==422 and response.json()['error']['code']=='source_mismatch'
        return
    record=client.post('/api/investigations/capture',json=request).json()
    replay=deepcopy(record['replay'])
    if kind=='heat_source': replay['sources']['heat_manifest_sha256']='0'*64
    elif kind=='method': replay['sources']['methods']['heat']='unsupported'
    else: replay['expected_result_sha256']='0'*64
    replay['expected_recipe_sha256']=fingerprint(dict(recipe=replay['recipe'],sources=replay['sources']))
    response=client.post('/api/investigations/replay',json=replay)
    assert response.status_code==422
    assert response.json()['error']['code']=={'heat_source':'source_mismatch','method':'method_mismatch','result':'result_mismatch'}[kind]

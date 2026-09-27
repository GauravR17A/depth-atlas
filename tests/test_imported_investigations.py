"""Independent native-file interpolation, imported lifecycle and adversarial replay."""
import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import netCDF4
import numpy as np
import pytest
from fastapi.testclient import TestClient

from adapters.import_preview import PARSER_VERSION, inspect_import
from api.app import create_app
from api.evidence_store import EvidenceStore
from science.investigations import fingerprint

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'casepacks/instruments/examples'
CASE = 'bay-bengal-2024-03'
SETTINGS = dict(variable='temperature', time_index=2, time_window_hours=6, distance_km=5, max_vertical_gap_m=500, qc='good_probably_good')


def envelope(name='SR1902594_034.nc', body=None, mapping=None):
    body = body if body is not None else (EXAMPLES/name).read_bytes()
    return dict(schema_version='1', filename=name, content_base64=base64.b64encode(body).decode(),
                source_sha256=hashlib.sha256(body).hexdigest(), parser_version=PARSER_VERSION, mapping=mapping)


def selection(source, mode='comparison'):
    parsed = inspect_import(base64.b64decode(source['content_base64']), source['filename'], source['mapping'])['result']['profiles'][0]
    common = dict(mode=mode, case_id=CASE, profile_id='import-'+parsed['id'], sample_index=0)
    return dict(**common, settings=SETTINGS, view='comparison', rank='nearest', baseline=None) if mode == 'comparison' else dict(**common, variable='chlorophyll', show_excluded=True)


@pytest.fixture(scope='module')
def client():
    return TestClient(create_app())


def capture(client, source, mode='comparison'):
    r = client.post('/api/investigations/capture', json=dict(title='Imported source check', recipe=selection(source, mode), import_source=source))
    assert r.status_code == 200, r.text[:1000]
    return r.json()


@pytest.fixture(scope='module')
def record(client):
    return capture(client, envelope())


def test_real_bgc_comparison_against_independent_native_file(record):
    out = record['results'][0]['output']
    p = record['imported_profiles'][0]
    assert 0 < out['matched_count'] <= 245
    assert out['profile']['source_sha256'] == envelope()['source_sha256']
    assert 'assimilates' in out['caveats'][0]
    assert any('this imported file only' in s for s in out['caveats'])
    assert not any('inspection only' in s for s in out['caveats'])
    with netCDF4.Dataset(EXAMPLES/'SR1902594_034.nc') as raw:
        values=np.ma.filled(raw['TEMP'][0,:], np.nan)
        flags=raw['TEMP_QC'][0,:]
        for row, value, flag in zip(out['rows'], values, flags):
            assert row['observed'] == (float(value) if np.isfinite(value) else None)
            assert row['qc'] == (flag.decode() if not np.ma.is_masked(flag) else '')
    # Independent spatial choice and interpolation from the native CF exchange,
    # whose complete arrays were independently checked against raw HYCOM in P16B.
    with netCDF4.Dataset(ROOT/'casepacks/standards'/f'{CASE}.nc') as nc:
        lat, lon, depth = (np.asarray(nc.variables[k][:]) for k in ('latitude','longitude','depth'))
        yy, xx = np.meshgrid(lat, lon, indexing='ij')
        a = np.sin(np.deg2rad(yy-p['latitude'])/2)**2 + np.cos(np.deg2rad(yy))*np.cos(np.deg2rad(p['latitude']))*np.sin(np.deg2rad(xx-p['longitude'])/2)**2
        distances = 2*6371.0088*np.arctan2(np.sqrt(a),np.sqrt(1-a))
        y, x = np.unravel_index(np.argmin(distances), distances.shape)
        column = np.ma.filled(nc.variables['temperature'][2,:,y,x], np.nan)
        residuals=[]
        for row, level in zip(out['rows'], p['levels']):
            if not row['accepted']:
                assert row['residual'] is None and row['reason'] != 'accepted'
                continue
            assert row['distance_km'] == pytest.approx(distances[y,x], abs=1e-10)
            expected = float(np.interp(level['depth_m'],depth,column))
            observed = level['readings']['temperature']['value']
            assert row['model'] == pytest.approx(expected, abs=1e-12)
            assert row['residual'] == pytest.approx(expected-observed, abs=1e-12)
            residuals.append(expected-observed)
    assert out['metrics']['bias'] == pytest.approx(np.mean(residuals), abs=1e-12)
    assert out['metrics']['rmse'] == pytest.approx(np.sqrt(np.mean(np.square(residuals))), abs=1e-12)
    assert out['metrics']['mae'] == pytest.approx(np.mean(np.abs(residuals)), abs=1e-12)


@pytest.mark.parametrize('mode', ['comparison','instrument'])
def test_source_included_fresh_app_replay_and_exact_export(client, mode):
    source=envelope(); record=capture(client,source,mode)
    fresh=TestClient(create_app()).post('/api/investigations/replay',json=record['replay'])
    assert fresh.status_code == 200, fresh.text[:500]
    assert fresh.json()['results'] == record['results']
    assert fresh.json()['replay'] == record['replay']
    assert fingerprint(record['imported_profiles']) == record['replay']['sources']['import_profiles_sha256']
    assert len(json.dumps(record,separators=(',',':')).encode()) < 4_200_000
    assert fingerprint({k:v for k,v in record.items() if k!='document_sha256'}) == record['document_sha256']
    exported=client.post('/api/investigations/export',json=dict(replay=record['replay'],format='zip'))
    assert exported.status_code == 200
    with ZipFile(io.BytesIO(exported.content)) as z:
        assert z.read('original-observation/'+source['filename']) == base64.b64decode(source['content_base64'])
        assert json.loads(z.read('investigation.json'))['result_sha256'] == record['result_sha256']
        assert 'original uploaded observation file' in z.read('README.txt').decode()
        csv_name='paired-values.csv' if mode=='comparison' else 'observation-profile.csv'
        import csv
        rows=list(csv.DictReader(io.StringIO(z.read(csv_name).decode())))
        if mode=='comparison':
            assert [float(r['residual']) if r['residual'] else None for r in rows] == [r['residual'] for r in record['results'][0]['output']['rows']]
        else:
            assert [float(r['value']) if r['value'] else None for r in rows] == [l['readings']['chlorophyll']['value'] for l in record['imported_profiles'][0]['levels']]


@pytest.mark.parametrize('change,code', [('bytes','source_mismatch'),('parser','method_mismatch'),('mapping','source_mismatch'),('model','source_mismatch'),('method','method_mismatch'),('result','result_mismatch'),('no_source','source_mismatch')])
def test_tampering_and_unavailable_dependencies_stop_replay(client,record,change,code):
    replay=deepcopy(record['replay'])
    if change=='bytes': replay['import_source']['content_base64']=base64.b64encode(b'changed').decode()
    if change=='parser': replay['import_source']['parser_version']='future-reader'
    if change=='mapping': replay['import_source']['filename']='renamed.nc'
    if change=='model': replay['sources']['model_manifest_sha256']='0'*64
    if change=='method': replay['sources']['methods']['comparison']='future-method'
    if change=='result': replay['expected_result_sha256']='0'*64
    if change=='no_source': del replay['import_source']
    replay['expected_recipe_sha256']=fingerprint(dict(recipe=replay['recipe'],sources=replay['sources']))
    r=client.post('/api/investigations/replay',json=replay)
    assert r.status_code == 422, r.text[:500]
    # Missing embedded bytes may be reported as an unsupported method before
    # source comparison. Neither path may substitute a bundled observation.
    assert r.json()['error']['code'] in ({code,'method_mismatch'} if change=='no_source' else {code})


def test_new_source_does_not_enter_frozen_library_or_global_evidence_caches(client):
    before=client.get('/api/instruments').json()
    counts=(EvidenceStore._comparison.cache_info().currsize, EvidenceStore._coverage.cache_info().currsize)
    source=envelope();recipe=selection(source)
    for settings in [SETTINGS,{**SETTINGS,'qc':'good'},{**SETTINGS,'time_index':0},{**SETTINGS,'variable':'salinity'}]:
        r=client.post(f'/api/cases/{CASE}/evidence/imported/comparison',json=dict(import_source=source,profile_id=recipe['profile_id'],settings=settings))
        assert r.status_code==200,r.text[:500]
        if settings['time_index']==0: assert r.json()['matched_count']==0 and 'time_window' in r.json()['exclusion_counts']
    assert client.get('/api/instruments').json()==before
    assert counts==(EvidenceStore._comparison.cache_info().currsize, EvidenceStore._coverage.cache_info().currsize)
    assert hashlib.sha256((ROOT/'casepacks/instruments/index.json').read_bytes()).hexdigest()=='b1fc70a489a594dc8b9e11aacd0b087166dee396b4e2a79ac77884e96d02a082'


def test_client_cannot_supply_forged_normalized_profiles_and_wrong_quantities(client):
    source=envelope();payload=dict(import_source=source,profile_id=selection(source)['profile_id'],settings=SETTINGS)
    r=client.post(f'/api/cases/{CASE}/evidence/imported/comparison',json={**payload,'profiles':[{'qc':'1'}]})
    assert r.status_code==422
    r=client.post(f'/api/cases/{CASE}/evidence/imported/comparison',json={**payload,'settings':{**SETTINGS,'variable':'chlorophyll'}})
    assert r.status_code==422
    r=client.post('/api/cases/pacific-godas-2015-son/evidence/imported/comparison',json=payload)
    assert r.status_code==200 and r.json()['matched_count']==0
    assert r.json()['exclusion_counts']['incompatible_variable']==1475


def test_mapped_kelvin_values_and_qc_replay_without_metadata_guessing(client):
    # Synthetic parser fixture, never shown as a real observation in the app.
    body=(b'profile_id,instrument,platform,time,latitude,longitude,pressure_dbar,pressure_qc,position_qc,time_qc,kelvin,flag\n'
          b'unit,argo,fixture,2024-03-29T00:00:00Z,12.5,85.5,10,1,1,1,300,1\n'
          b'unit,argo,fixture,2024-03-29T00:00:00Z,12.5,85.5,20,1,1,1,290,4\n'
          b'unit,argo,fixture,2024-03-29T00:00:00Z,12.5,85.5,30,1,1,1,,9\n')
    mapping=dict(temperature_c=dict(source='kelvin',units='K'),temperature_qc=dict(source='flag'))
    source=envelope('mapped.csv',body,mapping);record=capture(client,source)
    rows=record['results'][0]['output']['rows']
    assert rows[0]['observed']==pytest.approx(26.85,abs=1e-12) and rows[0]['accepted']
    assert rows[1]['reason']=='observation_qc' and rows[1]['residual'] is None
    assert rows[2]['reason']=='missing_value'
    assert record['imported_profiles'][0]['metadata']['mapping_sha256']
    replay=client.post('/api/investigations/replay',json=record['replay'])
    assert replay.status_code==200 and replay.json()['result_sha256']==record['result_sha256']


def test_request_budget_and_invalid_base64(client):
    r=client.post('/api/investigations/capture',content=b' ' * 3_000_001,headers={'Content-Type':'application/json'})
    assert r.status_code==413
    source=envelope();source['content_base64']='!!!!'
    r=client.post('/api/investigations/capture',json=dict(title='Invalid encoding',recipe=selection(envelope()),import_source=source))
    assert r.status_code==422 and r.json()['error']['code']=='source_mismatch'

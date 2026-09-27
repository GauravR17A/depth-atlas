"""Public case-pack invariants, source values, missing cells and bounded APIs."""

from pathlib import Path
import hashlib
import json
import math

from fastapi.testclient import TestClient
import pytest

from api.app import create_app
from api.case_store import CaseStore, CASE_ID

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'casepacks' / CASE_ID


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def test_pack_fingerprints_and_actual_coverage():
    manifest = json.loads((PACK/'manifest.json').read_text(encoding='utf-8'))
    for f in manifest['files']:
        p = PACK / f['path']
        assert p.stat().st_size == f['bytes']
        assert hashlib.sha256(p.read_bytes()).hexdigest() == f['sha256']
    assert manifest['coordinates']['times'][0] == '2024-01-07T00:00:00Z'
    assert manifest['coordinates']['times'][-1] == '2024-01-10T00:00:00Z'
    assert len(manifest['profiles']) == 7
    assert all(p['overlap']['eligible'] and p['data_mode']=='D' for p in manifest['profiles'])
    assert all(s['retrieved_at'].startswith('2026-') for s in manifest['sources'])
    assert set(manifest['case']['variables']) == {'temperature','salinity','eastward_velocity','northward_velocity'}


def test_source_packed_value_and_observation_are_preserved(client):
    path=f'/api/cases/{CASE_ID}/subset'
    response=client.get(path,params={'depth_index':0,'west':85.0400390625,'east':85.0400390625,'south':12,'north':12})
    assert response.status_code == 200
    body=response.json()
    # Independently inspected HYCOM packed value=8237; source Float32 scale .001.
    assert body['values'] == pytest.approx([28.237000391236506],abs=1e-12)
    assert body['shape'] == [1,1,1]
    p=client.get(f'/api/cases/{CASE_ID}/profiles/argo-1902669-012-0').json()
    assert p['time'] == '2024-01-07T14:10:13Z'
    assert p['levels'][0]['pressure_dbar'] == pytest.approx(0.4000000059604645)
    assert p['levels'][0]['temperature_c'] == pytest.approx(28.152999877929688)
    assert p['levels'][0]['salinity_psu'] == pytest.approx(32.832000732421875)
    assert p['levels'][0]['depth_m'] != p['levels'][0]['pressure_dbar']


def test_display_is_declared_decimation_and_preserves_mask():
    store=CaseStore(ROOT/'casepacks');m,_=store.require(CASE_ID)
    source=store._read_array(CASE_ID,'analytical','temperature',0)
    visual=store._read_array(CASE_ID,'display','temperature',0)
    ys=m.representations['display']['latitude_source_indices'];xs=m.representations['display']['longitude_source_indices']
    ny,nx=len(m.coordinates.latitude),len(m.coordinates.longitude)
    max_error=m.representations['display']['max_absolute_rounding_error']['temperature']
    for z in [0,19,32,39]:
        for iy,y in enumerate(ys):
            for ix,x in enumerate(xs):
                a=source[(z*ny+y)*nx+x];b=visual[(z*len(ys)+iy)*len(xs)+ix]
                assert math.isnan(a)==math.isnan(b)
                if math.isfinite(a):assert abs(a-b)<=max_error+1e-12


def test_bounded_endpoints_and_missing_are_explicit(client):
    path=f'/api/cases/{CASE_ID}/subset'
    response=client.get(path,params={'depth_index':39})
    assert response.status_code==200
    assert all(v is None for v in response.json()['values'])
    assert 'NaN' not in response.text
    visual=client.get(path,params={'operation':'volume','representation':'display'})
    assert visual.status_code==200
    assert len(visual.content)<4_000_000
    assert len(visual.json()['values'])==40*39*32
    too_big=client.get(path,params={'operation':'volume'})
    assert too_big.status_code==413
    assert too_big.json()['error']['code']=='subset_too_large'
    for params,code in [({'depth_index':99},'unsupported_depth'),({'depth_index':0,'time_index':7},'unsupported_time'),({'depth_index':0,'west':84,'east':90,'south':12,'north':15},'outside_coverage'),({'depth_index':0,'west':86},'invalid_bounds'),({'operation':'volume','depth_index':0},'invalid_request')]:
        r=client.get(path,params=params)
        assert r.status_code==422
        assert r.json()['error']['code']==code
    assert client.get(path,params={'depth_index':0,'variable':'chlorophyll'}).status_code==422
    assert client.get('/api/cases/unknown').status_code==404
    assert client.get(f'/api/cases/{CASE_ID}/profiles/unknown').status_code==404


def test_catalog_retains_indian_cases_and_adds_checked_pacific_seasons(client):
    health=client.get('/api/health').json();catalog=client.get('/api/catalog').json()
    assert health['data_status']=='historical_case_ready' and health['case_count']==6
    assert catalog['schema_version']=='2' and len(catalog['cases'])==6
    assert [r['id'] for r in catalog['regions'] if r['status']=='data_available']==['bay-of-bengal','arabian-sea','tropical-pacific']
    assert {c['id'] for c in catalog['cases']}=={'bay-bengal-2024-01','arabian-sea-2024-01','bay-bengal-2024-03','pacific-godas-2013-son','pacific-godas-2015-son','pacific-godas-2022-son'}

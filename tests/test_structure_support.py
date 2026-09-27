"""Independent bin-boundary fixtures and real P05/P07/API consistency."""
import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from science.support import associate
from science.feature_contracts import FeatureQuery
from science.evidence_contracts import MatchRow

ROOT = Path(__file__).resolve().parents[1]
BASE = '/api/cases/bay-bengal-2024-01/'


def pair(i, depth):
    return MatchRow(sample_index=i, observation_time='2024-01-07T12:00:00Z', latitude=10, longitude=80,
                    depth_m=depth, observed=25, model=26, residual=1, accepted=True, reason='accepted',
                    qc='1', mode='R', model_latitude=10, model_longitude=80, distance_km=0,
                    time_offset_hours=0, lower_depth_m=0, upper_depth_m=100,
                    upper_weight=depth/100, model_lower_value=26, model_upper_value=26)


def test_irregular_midpoint_bins_boundary_duplicates_and_gaps():
    # Region has only the native 10 m cell. Its depth bin is [5,55).
    coordinates = dict(depth_m=[0,10,100], latitude=[10,11], longitude=[80,81])
    labels = np.full((3,2,2), -1); labels[1,0,0] = 4
    rows = [pair(i,z) for i,z in enumerate([4.999,5,10,54.999,55,100])]
    comparison = NS(profile=NS(id='source',platform='test',source_sha256='a'*64), rows=rows, exclusion_counts={'observation_qc':2})
    result = associate(labels, coordinates, FeatureQuery(depth_max_m=100), 'r4', [comparison])
    assert [r['sample_index'] for r in result['rows']] == [1,2,3]
    assert result['eligible_samples'] == 3
    assert result['supported_cells'] == result['region_cells'] == 1
    assert result['unsupported_cells'] == 0
    assert result['supported_columns'] == [0]
    assert result['accepted_outside_region'] == 3
    assert result['excluded_samples'] == 2
    # Clipping at source centres cannot pull a sample into an excluded depth.
    clipped = associate(labels,coordinates,FeatureQuery(depth_min_m=11,depth_max_m=100),'r4',[comparison])
    assert clipped['eligible_samples'] == 0
    assert clipped['unsupported_cells'] == 1


@pytest.fixture(scope='module')
def client():
    return TestClient(create_app(web_dist=ROOT/'web/dist'))


def request(client,base=BASE,query=None,**extra):
    query = query or {}
    found = client.post(base+'features/search',json=query).json()
    return found, dict(query=found['query'],region_id=found['regions'][0]['id'],settings=dict(variable=found['query']['variable'],time_index=found['query']['time_index']),**extra)


def test_real_january_support_uses_exact_accepted_pairs_and_gaps(client):
    found, body = request(client)
    response = client.post(BASE+'features/support',json=body)
    assert response.status_code == 200, response.text
    data=response.json()
    assert data['eligible_samples'] == found['regions'][0]['eligible_samples'] == 34
    assert data['eligible_profiles'] == 2
    assert data['supported_cells'] + data['unsupported_cells'] == found['regions'][0]['cell_count']
    assert data['supported_cells'] == len({tuple(r['cell']) for r in data['rows']})
    assert data['unsupported_columns'] == len(data['footprint_indices'])-len(data['supported_columns'])
    for pid in {r['profile_id'] for r in data['rows']}:
        expected=client.get(BASE+'evidence/profiles/'+pid,params=body['settings']).json()
        for row in (r for r in data['rows'] if r['profile_id']==pid):
            original=next(r for r in expected['rows'] if r['sample_index']==row['sample_index'])
            assert all(row[k]==v for k,v in original.items())
            assert row['residual']==pytest.approx(row['model']-row['observed'])
            assert found['coordinates']['latitude'][row['cell'][1]]==row['model_latitude']
            assert found['coordinates']['longitude'][row['cell'][2]]==row['model_longitude']
    strict=client.post(BASE+'features/support',json={**body,'settings':{**body['settings'],'time_window_hours':0}}).json()
    assert strict['eligible_samples']==strict['supported_cells']==0
    assert strict['unsupported_cells']==data['region_cells']


def test_imported_march_source_and_stricter_time_do_not_rewrite_dates(client):
    original=(ROOT/'casepacks/instruments/examples/SR1902594_034.nc').read_bytes()
    envelope=dict(filename='SR1902594_034.nc',schema_version='1',content_base64=base64.b64encode(original).decode(),source_sha256=hashlib.sha256(original).hexdigest(),parser_version='observation-preview-v1',mapping=None)
    base='/api/cases/bay-bengal-2024-03/'
    found,body=request(client,base,dict(time_index=2,threshold=20,depth_max_m=300),import_source=envelope)
    response=client.post(base+'features/support',json=body)
    assert response.status_code==200,response.text
    support=response.json()
    assert support['eligible_samples']>0
    assert support['eligible_profiles']==1
    assert support['source_scope']=='SR1902594_034.nc'
    assert support['model_time']=='2024-03-29T00:00:00Z'
    assert {r['observation_time'] for r in support['rows']}=={'2024-03-29T02:30:44Z'}
    comparison=client.post(base+'evidence/imported/comparison',json=dict(import_source=envelope,profile_id=support['rows'][0]['profile_id'],settings=body['settings'])).json()
    assert comparison['matched_count']==245
    assert support['eligible_samples']+support['accepted_outside_region']==245
    assert support['excluded_samples']==comparison['excluded_count']
    strict=client.post(base+'features/support',json={**body,'settings':{**body['settings'],'time_window_hours':1}}).json()
    assert strict['eligible_samples']==0
    assert strict['unsupported_cells']==support['region_cells']
    bad={**envelope,'source_sha256':'0'*64}
    assert client.post(base+'features/support',json={**body,'import_source':bad}).status_code==422


@pytest.mark.parametrize('change',[
    {'settings':{'variable':'salinity','time_index':1}},
    {'settings':{'time_index':0}}, {'settings':{'time_window_hours':73}},
    {'region_id':'r9999999'}, {'query':{'threshold':100}}, {'extra':'invalid'},
])
def test_mismatches_reject_instead_of_fabricating_support(client,change):
    _,body=request(client)
    assert client.post(BASE+'features/support',json={**body,**change}).status_code==422


def test_request_byte_bound_and_monthly_quantity_hold(client):
    assert client.post(BASE+'features/support',content=b' '*3_000_001,headers={'Content-Type':'application/json'}).status_code==413
    base='/api/cases/pacific-godas-2015-son/'
    found,body=request(client,base,{'time_index':0,'threshold':20,'depth_min_m':5})
    response=client.post(base+'features/support',json=body)
    assert response.status_code==422
    assert response.json()['error']['code']=='incompatible_quantity'

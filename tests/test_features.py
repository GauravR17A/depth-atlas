"""API rejection, native surface geometry and bounded search behavior."""
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from api.app import create_app
from science.feature_contracts import FeatureQuery, SectionQuery
from science.features import analyze,boundary_faces,sample_section,midpoint_edges

ROOT=Path(__file__).resolve().parents[1]
PATH='/api/cases/bay-bengal-2024-01/features/'


@pytest.fixture(scope='module')
def client():
    return TestClient(create_app(web_dist=ROOT/'web/dist'))


@pytest.mark.parametrize('change',[
    {'variable':'oxygen'}, {'units':'K'}, {'variable':'salinity'}, {'time_index':7},
    {'operator':'above'}, {'depth_min_m':300}, {'depth_min_m':-1}, {'depth_max_m':6000},
    {'operator':'between'}, {'operator':'between','upper_threshold':20},
    {'upper_threshold':30}, {'extra':'ignored'}, {'threshold':float('inf')},
])
def test_invalid_search_is_rejected(client,change):
    import json
    response=client.post(PATH+'search',content=json.dumps(change),headers={'Content-Type':'application/json'})
    assert response.status_code==422
    assert response.json()['error']['code'] in {'invalid_request','incompatible_units'}


def test_default_query_and_exact_source_identity(client):
    data=client.post(PATH+'search',json={}).json()
    assert data['qualified_cells']==sum(r['cell_count'] for r in data['regions'])==80203
    assert data['manifest_sha256']=='9598b33dc9eef89cb909f2811e1590ca580a143c1dbcc25d97e51a84faf7d28d'
    assert data['model_time']=='2024-01-07T12:00:00Z'
    assert data['shape']==[40,76,63]
    assert data['regions'][0]['eligible_samples']==34
    assert data['regions'][0]['eligible_profiles']==2
    reordered=client.post(PATH+'search',json={'order':'observations'}).json()
    assert data['regions']==reordered['regions']
    assert len(data['footprint']['region_ids'])==76*63
    assert len(data['edges']['depth_m'])==41


def test_empty_and_unsupported_region_do_not_fabricate_geometry(client):
    data=client.post(PATH+'search',json={'threshold':100}).json()
    assert data['qualified_cells']==data['total_regions']==0
    assert data['regions']==[]
    assert set(data['footprint']['region_ids'])=={None}
    response=client.post(PATH+'region',json={'query':{'threshold':100},'region_id':'r0'})
    assert response.status_code==422
    assert response.json()['error']['code']=='region_not_found'
    assert client.post(PATH+'region',json={'query':{},'region_id':'../../other'}).status_code==422


@pytest.mark.parametrize('start,end,stations',[
    ([84,13],[89,14],81),([86,13],[86,13],81),([86,13],[89,14],202),
])
def test_section_rejects_outside_empty_and_unbounded(client,start,end,stations):
    assert client.post(PATH+'section',json=dict(query={},start=start,end=end,stations=stations)).status_code==422


def test_mesh_surface_has_exact_native_boundary_without_internal_faces():
    labels=np.full((3,4,5),-1)
    labels[:2,1:3,1:4]=0
    faces=boundary_faces(labels,0)
    assert len(faces)==6  # merged rectangular solid
    def area(f): return (f[3]-f[2])*(f[5]-f[4])
    assert sum(area(f) for f in faces)==2*(2*2+2*3+2*3)
    labels[0,1,2]=-1  # remove a surface cell; validate each exposed unit face independently
    expected=set()
    for z,y,x in zip(*np.where(labels==0)):
        pos=[z,y,x]
        for axis in range(3):
            others=[i for i in range(3) if i!=axis]
            for sign in (-1,1):
                neighbour=pos.copy();neighbour[axis]+=sign
                if neighbour[axis]<0 or neighbour[axis]>=labels.shape[axis] or labels[tuple(neighbour)]!=0:
                    expected.add((axis,pos[axis]+(sign==1),pos[others[0]],pos[others[1]],sign))
    actual=set()
    for axis,plane,u0,u1,v0,v1,sign in boundary_faces(labels,0):
        for u in range(u0,u1):
            for v in range(v0,v1):
                item=(axis,plane,u,v,sign)
                assert item not in actual
                actual.add(item)
    assert actual==expected
    assert boundary_faces(labels,0,limit=1) is None


def test_section_keeps_mask_and_selects_native_values_without_interpolation():
    coords=dict(depth_m=[0,10,100],latitude=[10,11],longitude=[80,82,84])
    values=np.arange(18,dtype=float).reshape(3,2,3)
    values[1,0,1]=np.nan
    q=FeatureQuery(threshold=0,depth_max_m=100)
    data=analyze(values,coords,q)
    s=sample_section(values,coords,data['labels'],SectionQuery(query=q,start=(80,10),end=(84,10),stations=3))
    assert s['values']==[0,1,2,6,None,8,12,13,14]
    assert s['depth_m']==[0,10,100]
    assert s['region_ids'][4] is None
    assert all(station['offset_km']==0 for station in s['stations'])


def test_cell_bins_and_native_analysis_never_mutate_inputs():
    coords=dict(depth_m=[0,10,100],latitude=[10,11],longitude=[80,82,84])
    values=np.ones((3,2,3));before=values.copy()
    assert midpoint_edges(coords['depth_m']).tolist()==[0,5,55,100]
    result=analyze(values,coords,FeatureQuery(threshold=1,depth_min_m=9,depth_max_m=11))
    assert result['qualified_cells']==6
    assert result['regions'][0]['cell_bounds']['depth_min_m']==9
    assert result['regions'][0]['cell_bounds']['depth_max_m']==11
    assert np.array_equal(values,before)


def test_derived_search_has_no_invented_observation_matches(client):
    data=client.post(PATH+'search',json={'variable':'horizontal_kinetic_energy','units':'m\u00b2/s\u00b2','threshold':0.08}).json()
    assert data['qualified_cells']>0
    assert all(r['eligible_samples']==r['eligible_profiles']==0 for r in data['regions'])
    assert data['units']=='m\u00b2/s\u00b2'

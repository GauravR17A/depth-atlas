"""Two-case isolation, genuine guide samples and backwards-compatible replay."""
import json
import hashlib
from copy import deepcopy
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from api.app import create_app
from api.case_store import CaseStore
from api.guide_store import GuideStore
from science.contracts import UnsupportedData

ROOT=Path(__file__).resolve().parents[1]
BAY='bay-bengal-2024-01';SEA='arabian-sea-2024-01'
@pytest.fixture(scope='module')
def client():return TestClient(create_app())

def test_old_bay_identity_remains_unchanged():
    assert hashlib.sha256((ROOT/'casepacks'/BAY/'manifest.json').read_bytes()).hexdigest()=='9598b33dc9eef89cb909f2811e1590ca580a143c1dbcc25d97e51a84faf7d28d'

def test_guide_values_dates_tolerance_and_matching(client):
    guide=client.get('/api/guided-cases');assert guide.status_code==200
    g=guide.json();assert g['comparison_depth_m']==100 and g['surface_tolerance_c']==.05
    assert len(g['columns'])==2
    for c in g['columns']:
        m=client.get('/api/cases/'+c['case_id']).json()
        assert c['time']==m['coordinates']['times'][1]=='2024-01-07T12:00:00Z'
        assert c['depth_m'][c['point'][2]]==100
        r=client.get('/api/cases/'+c['case_id']+'/evidence/profiles/'+c['comparison']['profile_id'],params={'time_index':1});assert r.status_code==200,r.text
        assert r.json()['matched_count']==c['comparison']['matched_count']>0
    assert abs(g['columns'][0]['temperature_c'][0]-g['columns'][1]['temperature_c'][0])==pytest.approx(.007,abs=1e-8)
    assert abs(g['columns'][0]['temperature_c'][19]-g['columns'][1]['temperature_c'][19])==pytest.approx(4.239,abs=1e-6)

def test_cases_do_not_share_values_or_observation_identity(client):
    libraries=[client.get('/api/instruments',params={'case_id':cid}).json() for cid in (BAY,SEA)]
    assert [len(v['profiles']) for v in libraries]==[13,19]
    a=client.get(f'/api/cases/{BAY}/subset',params={'depth_index':19}).json()
    b=client.get(f'/api/cases/{SEA}/subset',params={'depth_index':19}).json()
    assert a['longitude']!=b['longitude'] and a['values']!=b['values'] and a['manifest_sha256']!=b['manifest_sha256']
    sea_profile=next(p for p in libraries[1]['profiles'] if p['platform']=='1902671')
    assert client.get(f'/api/cases/{BAY}/evidence/profiles/'+sea_profile['id']).status_code==404
    wrong=client.post('/api/investigations/capture',json={'title':'Wrong case context','recipe':{'mode':'instrument','case_id':BAY,'profile_id':sea_profile['id'],'variable':'temperature'}})
    assert wrong.status_code==404 and wrong.json()['error']['code']=='profile_not_found'
    assert client.get('/api/instruments?case_id=unknown').status_code==404

@pytest.mark.parametrize('mode',['ocean','comparison','features','instrument'])
def test_arabian_capture_replay_export(client,mode):
    c=client.get('/api/guided-cases').json()['columns'][1]
    settings=dict(variable='temperature',time_index=1,time_window_hours=6,distance_km=5,max_vertical_gap_m=500,qc='good_probably_good')
    q=dict(variable='temperature',units='\u00b0C',time_index=1,operator='at_least',threshold=26,depth_min_m=0,depth_max_m=300,order='volume')
    recipe={'ocean':dict(variable='temperature',time_index=1,view='volume',depth_index=19,section_index=0,point=c['point'],cutaway=True),'comparison':dict(profile_id=c['comparison']['profile_id'],settings=settings),'features':dict(query=q),'instrument':dict(profile_id=c['comparison']['profile_id'],variable='temperature')}[mode]
    if mode=='ocean':recipe.update(paint=dict(min=0,max=30),iso=20,exaggeration=200,window_depth=1000,quality='auto',show_instruments=True)
    recipe.update(mode=mode,case_id=SEA)
    r=client.post('/api/investigations/capture',json={'title':'Arabian Sea evidence','recipe':recipe});assert r.status_code==200,r.text
    record=r.json();replay=client.post('/api/investigations/replay',json=record['replay']);assert replay.status_code==200,replay.text
    assert replay.json()['results']==record['results']
    assert any(ref.get('source_url','').endswith(SEA+'.nc') for ref in record['references'])
    export=client.post('/api/investigations/export',json={'replay':record['replay']});assert export.status_code==200

def test_old_release_records_still_replay(client):
    records=json.loads((ROOT/'docs/evidence/p08-local-records.json').read_text())
    for record in records:
        r=client.post('/api/investigations/replay',json=record['replay']);assert r.status_code==200,r.text
        assert r.json()['results']==record['results']

def test_guide_refuses_changed_native_value(tmp_path):
    class Cases:
        root=tmp_path
        def require(self,cid):return CaseStore(ROOT/'casepacks').require(cid)
        def _read_array(self,*args):
            result=CaseStore(ROOT/'casepacks')._read_array(*args);result[9*63+34]+=1;return result
    (tmp_path/'guides').mkdir();(tmp_path/'guides/indian-ocean.json').write_bytes((ROOT/'casepacks/guides/indian-ocean.json').read_bytes())
    with pytest.raises(UnsupportedData):GuideStore(Cases()).read()

def test_arabian_standards_availability_is_scoped(client):
    r=client.get('/api/data-access?case_id='+SEA).json();assert r['download'].endswith(SEA+'.nc')
    assert r['standards']['protocols']==[]
    assert r['standards']['verified_case_ids']==[BAY,'bay-bengal-2024-03']
    assert client.get('/api/data-access?case_id=unregistered').status_code==404

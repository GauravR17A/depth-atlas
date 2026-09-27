"""Replay, source mutation, export and independent source-reference boundaries."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from api.app import create_app
from api.case_store import CaseStore
from science.investigations import fingerprint

ROOT=Path(__file__).resolve().parents[1]
CASE='bay-bengal-2024-01'
PROFILE='argo-1902669-12-0-1c4592fce4'
SETTINGS=dict(variable='temperature',time_index=1,time_window_hours=6,distance_km=5,max_vertical_gap_m=500,qc='good_probably_good')
QUERY=dict(variable='temperature',units='\u00b0C',time_index=1,operator='at_least',threshold=26,upper_threshold=None,depth_min_m=0,depth_max_m=300,order='volume')
OCEAN=dict(mode='ocean',case_id=CASE,variable='temperature',time_index=0,view='slice',depth_index=19,section_index=19,point=[31,38,19],paint=dict(min=0,max=30,log=False,palette='thermal',opacity=1),iso=20,exaggeration=200,window_depth=1000,cutaway=True,quality='basic',show_instruments=True)
COMPARISON=dict(mode='comparison',case_id=CASE,profile_id=PROFILE,settings=SETTINGS,sample_index=4,view='comparison',rank='nearest',baseline=dict(profile_id=PROFILE,settings={**SETTINGS,'time_window_hours':1}))
FEATURE=dict(mode='features',case_id=CASE,query=QUERY,selected_region='r0',section=dict(query=QUERY,start=[86,13],end=[89,14],stations=81),section_pick=7*81+23)
INSTRUMENT=dict(mode='instrument',case_id=CASE,profile_id='bgc-6903091-100-0-20692904a9',variable='oxygen',sample_index=9,show_excluded=True)


@pytest.fixture(scope='module')
def client():return TestClient(create_app())


def capture(client,recipe,title='Pinned investigation'):
    r=client.post('/api/investigations/capture',json=dict(title=title,recipe=recipe))
    assert r.status_code==200,r.text
    return r.json()


@pytest.mark.parametrize('recipe',[OCEAN,COMPARISON,FEATURE,INSTRUMENT])
def test_record_recalculates_all_modules_and_export_values(client,recipe):
    record=capture(client,recipe)
    replay=client.post('/api/investigations/replay',json=record['replay']);assert replay.status_code==200,replay.text
    fresh=replay.json();assert fresh['results']==record['results']
    assert fresh['replay']==record['replay'] and fresh['result_sha256']==record['result_sha256']
    assert fingerprint({k:v for k,v in record.items() if k!='document_sha256'})==record['document_sha256']
    response=client.post('/api/investigations/export',json=dict(replay=record['replay']))
    assert response.status_code==200
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert {'investigation.json','settings.json','report.html','SOURCES.json','README.txt','source-credits.txt'}<=set(archive.namelist())
        saved=json.loads(archive.read('investigation.json'));assert saved['results']==record['results']
        for filename in archive.namelist():
            if filename.endswith('.csv'):
                rows=list(csv.reader(io.StringIO(archive.read(filename).decode('utf-8'))));assert rows and all(len(r)==len(rows[0]) for r in rows)
        if recipe['mode']=='comparison':
            csv_rows=list(csv.DictReader(io.StringIO(archive.read('paired-values.csv').decode())))
            output=next(r['output'] for r in record['results'] if r['module']=='comparison')
            assert len(csv_rows)==len(output['rows'])==103
            for exported,source in zip(csv_rows,output['rows']):
                for key in ['observed','model','residual','depth_m','upper_weight']:
                    assert (float(exported[key]) if exported[key] else None)==source[key]
            assert 'reference-paired-values.csv' in archive.namelist()
        if recipe['mode']=='features':
            reference=json.loads((ROOT/'tests/fixtures/p07-source-reference.json').read_text())
            expected=next(q for q in reference['source_queries'] if q.get('name')=='default-query')
            out=next(r['output'] for r in record['results'] if r['module']=='regions')
            assert out['qualified_cells']==80203
            assert out['regions'][0]['membership_sha256']==expected['components'][0]['membership_sha256']
            assert out['regions'][0]['estimated_volume_km3']==pytest.approx(12966.151584607129,rel=1e-12)
            section=next(r['output'] for r in record['results'] if r['module']=='section')
            csv_rows=list(csv.DictReader(io.StringIO(archive.read('section.csv').decode())))
            assert [float(r['value']) if r['value'] else None for r in csv_rows]==section['values']
            assert [r['region_id'] or None for r in csv_rows]==section['region_ids']
        if recipe['mode']=='ocean':
            col=record['results'][0]['output']['columns'][0]
            assert col['values'][19]==pytest.approx(22.30300010938663,abs=1e-9)
            rows=list(csv.DictReader(io.StringIO(archive.read('native-profile.csv').decode())))
            assert len(rows)==40 and rows[-1]['temperature [\u00b0C]']==''


@pytest.mark.parametrize('kind',['recipe','result','source','method'])
def test_replay_rejects_mismatch_without_substitution(client,kind):
    record=capture(client,COMPARISON);request=deepcopy(record['replay'])
    if kind in {'recipe','result'}:request['recipe']['settings']['time_index']=0
    if kind=='source':request['sources']['model_manifest_sha256']='0'*64
    if kind=='method':request['sources']['methods']['comparison']='different-method-v9'
    if kind!='recipe':request['expected_recipe_sha256']=fingerprint(dict(recipe=request['recipe'],sources=request['sources']))
    response=client.post('/api/investigations/replay',json=request)
    assert response.status_code==422 and response.json()['error']['code']==kind+'_mismatch'


def test_missing_source_is_explicit(client,monkeypatch):
    record=capture(client,OCEAN)
    def missing(*_args,**_kwargs):raise FileNotFoundError('test unavailable checked data')
    monkeypatch.setattr(CaseStore,'_read_array',missing)
    response=client.post('/api/investigations/replay',json=record['replay'])
    assert response.status_code==422 and response.json()['error']['code']=='source_unavailable'


def test_release_patch_does_not_invalidate_identical_science(client,monkeypatch):
    record=capture(client,OCEAN)
    monkeypatch.setattr('api.investigation_store.APP_VERSION','0.8.99')
    response=client.post('/api/investigations/replay',json=record['replay'])
    assert response.status_code==200
    assert response.json()['software']['app']=='0.8.99'
    assert response.json()['result_sha256']==record['result_sha256']


@pytest.mark.parametrize('change',[{'view':'currents'},{'point':[31,38,18]},{'point':[999,38,19]},{'section_index':999},{'time_index':7},{'window_depth':900},{'random_seed':5},{'paint':{'min':0,'max':30,'log':True}},{'paint':{'min':3,'max':2}}])
def test_invalid_recipe_cannot_be_silently_coerced(client,change):
    r=client.post('/api/investigations/capture',json=dict(title='Invalid',recipe={**OCEAN,**change}))
    assert r.status_code==422


def test_imported_profile_identifier_never_becomes_a_path(client):
    r=client.post('/api/investigations/capture',json=dict(title='Invalid',recipe={**INSTRUMENT,'profile_id':'../private.nc'}))
    assert r.status_code==422


def test_report_escapes_user_title_and_preserves_scientific_limits(client):
    record=capture(client,FEATURE,'<script>alert(1)</script> & section')
    r=client.post('/api/investigations/export',json=dict(replay=record['replay'],format='html'))
    assert r.status_code==200 and '<script>alert' not in r.text
    assert '&lt;script&gt;' in r.text and 'Volume is estimated' in r.text and 'model_time' not in r.text.split('<table>')[1].split('</table>')[0]


def test_numeric_fingerprints_survive_json_float_integer_and_key_order():
    assert fingerprint({'b':1.0,'a':[None,True,-0.0,'\u03b1\U0001f30a']})==fingerprint({'a':[None,True,0,'\u03b1\U0001f30a'],'b':1})
    assert fingerprint(1)!=fingerprint(True)!=fingerprint('1')
    assert fingerprint([1,2])!=fingerprint([2,1])
    assert fingerprint(1.0000000000000002)!=fingerprint(1)
    with pytest.raises(ValueError):fingerprint(float('nan'))


def test_current_speed_and_joint_masks_are_preserved(client):
    record=capture(client,{**OCEAN,'variable':'currents','view':'currents'})
    out=record['results'][0]['output'];east,north=out['columns']
    for a,b,speed in zip(east['values'],north['values'],out['horizontal_speed']):
        assert speed is None if a is None or b is None else speed==pytest.approx((a*a+b*b)**.5,rel=1e-14)


def test_capture_checks_the_visible_source_identity(client):
    r=client.post('/api/investigations/capture',json=dict(title='Changed',recipe=OCEAN,expected_model_sha256='0'*64))
    assert r.status_code==422 and r.json()['error']['code']=='source_mismatch'


def test_replay_in_two_fresh_python_processes(tmp_path):
    source=tmp_path/'recipes.json';source.write_text(json.dumps([OCEAN,COMPARISON,FEATURE,INSTRUMENT]))
    records=tmp_path/'records.json';result=tmp_path/'replay.json'
    for args in [('--capture',str(source),'--output',str(records)),('--replay',str(records),'--output',str(result))]:
        p=subprocess.run([sys.executable,'science/verify_p08_replay.py',*args],cwd=ROOT,capture_output=True,text=True,timeout=90)
        assert p.returncode==0,p.stderr+p.stdout
    report=json.loads(result.read_text());assert report['passed'] and report['records']==4


def test_zip_export_stops_if_required_credits_are_not_packaged(client,monkeypatch):
    record=capture(client,OCEAN)
    original=Path.read_text
    def unavailable(path,*args,**kwargs):
        if path.name=='third-party-notices.txt':raise FileNotFoundError('missing packaged credits')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',unavailable)
    response=client.post('/api/investigations/export',json={'replay':record['replay'],'format':'zip'})
    assert response.status_code==422
    assert response.json()['error']['code']=='export_unavailable'

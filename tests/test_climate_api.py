"""Real-pack API, case integration and portable investigation acceptance."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
from zipfile import ZipFile
import pytest
from fastapi.testclient import TestClient
from api.app import create_app
from api.case_store import CaseStore, PACIFIC_CASE_IDS
from api.climate_store import ClimateStore
from api.instrument_store import InstrumentStore
from science.climate_contracts import ClimateQuery, METHOD
from science.contracts import UnsupportedData
from science.investigations import fingerprint

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def client():
    assert (ROOT/'casepacks/climate/manifest.json').is_file(), 'Actual prepared climate sources are required.'
    return TestClient(create_app())


def analyse(client,**changes):
    q=ClimateQuery().model_dump();q.update(changes)
    r=client.post('/api/climate/analyse',json=q)
    assert r.status_code==200,r.text
    return r.json()


def capture(client,result):
    recipe=dict(mode='climate',case_id=result['case_id'],query=result['query'])
    r=client.post('/api/investigations/capture',json=dict(title='Historical climate comparison',recipe=recipe,
                  expected_model_sha256=result['model_manifest_sha256'],expected_climate_manifest_sha256=result['climate_manifest_sha256']))
    assert r.status_code==200,r.text
    return r.json()


def test_catalog_is_source_specific_and_complete(client):
    r=client.get('/api/climate/catalog');assert r.status_code==200,r.text
    d=r.json()
    assert d['method_version']==METHOD
    assert d['baseline']['start_year']==1991 and d['baseline']['end_year']==2020
    assert [e['year'] for e in d['events']]==[2013,2015,2022]
    assert {e['case_id'] for e in d['events']}==set(PACIFIC_CASE_IDS)
    assert len(d['coordinates']['longitude'])==140 and len(d['coordinates']['depth_m'])==28
    assert d['coordinates']['longitude'][0]==140.5 and d['coordinates']['longitude'][-1]==279.5
    assert d['index_definitions']['roni_v6']


@pytest.mark.parametrize('year',[2013,2015,2022])
@pytest.mark.parametrize('period',['SON','09','10','11'])
def test_actual_events_all_calendar_windows_and_native_coordinates(client,year,period):
    d=analyse(client,event_id=f'son-{year}',period=period)
    a,b=d['panels']
    assert a['case_id']==f'pacific-godas-{year}-son'
    assert a['pacific']['longitude']==b['pacific']['longitude']
    assert a['pacific']['depth_m']==b['pacific']['depth_m']
    assert a['pacific']['shape']==[28,140] and a['indian']['shape']==[28,70]
    assert a['pacific']['latitude']==a['indian']['latitude']!=0
    assert a['period_start'][:4]==str(year) and b['period_start'][:4]=='2013'
    assert a['period_start'][4:]==b['period_start'][4:]
    assert a['period_end_exclusive'][4:]==b['period_end_exclusive'][4:]
    assert d['selected_point']['longitude']==210.5
    assert all(p['time'][:4]==str(year) for p in d['observations'][0]['profiles'])
    assert len(json.dumps(d,allow_nan=False))<2_000_000


@pytest.mark.parametrize('case_id',PACIFIC_CASE_IDS)
def test_shared_explorer_reads_real_potential_temperature_and_original_instruments(client,case_id):
    m=client.get('/api/cases/'+case_id).json()
    assert m['coordinates']['longitude_convention']=='[0,360)'
    assert m['case']['variables']==['temperature']
    assert m['variables'][0]['standard_name']=='sea_water_potential_temperature'
    assert len(m['coordinates']['times'])==3
    d=client.get(f'/api/cases/{case_id}/subset',params=dict(variable='temperature',time_index=1,representation='display',operation='volume')).json()
    assert d['source_id']!='hycom-gofs31-93.0'
    assert d['shape']==[28,16,48] and any(v is not None for v in d['values'])
    assert d['standard_name']=='sea_water_potential_temperature'
    assert any('Monthly mean over' in line for line in d['processing'])
    index=client.get('/api/instruments',params={'case_id':case_id}).json()
    assert len(index['profiles'])==3
    for p in index['profiles']:
        assert p['time'][:4]==case_id.split('-')[2]
        detail=client.get('/api/instruments/profiles/'+p['id'])
        assert detail.status_code==200,detail.text
        assert detail.json()['source_sha256']==p['source_sha256']


@pytest.mark.parametrize('variable',['salinity','eastward_velocity','northward_velocity','horizontal_kinetic_energy'])
def test_unsupported_pacific_variables_explain_without_fabricated_data(client,variable):
    r=client.get('/api/cases/pacific-godas-2015-son/subset',params={'variable':variable,'depth_index':0})
    assert r.status_code==422,r.text
    assert r.json()['error']['code'] in {'unsupported_variable','unsupported_subset'}


def test_pacific_unsupported_modules_explain_without_internal_error(client):
    prefix='/api/cases/pacific-godas-2015-son'
    for path in [prefix+'/heat/catalog',prefix+'/drift/context','/api/data-access?case_id=pacific-godas-2015-son']:
        r=client.get(path)
        assert r.status_code==422,r.text
        assert r.json()['error']['code']!='internal_error'


def test_monthly_case_evidence_does_not_reuse_hycom_or_bay_caveats(client):
    case_id='pacific-godas-2015-son'
    profiles=client.get('/api/instruments',params={'case_id':case_id}).json()['profiles']
    r=client.get(f"/api/cases/{case_id}/evidence/profiles/{profiles[0]['id']}")
    assert r.status_code==200,r.text
    d=r.json();assert d['matched_count']==0
    caveats=' '.join(d['caveats'])
    assert 'GODAS' in caveats and 'HYCOM' not in caveats and 'verification run' not in caveats
    search=client.post(f'/api/cases/{case_id}/features/search',json={'variable':'temperature','units':'°C','time_index':1,'threshold':26,'depth_min_m':5})
    assert search.status_code==200,search.text
    result=search.json()
    assert result['quantity']['standard_name']=='sea_water_potential_temperature'
    assert result['temporal_support']['interval']==['2015-10-01T00:00:00Z','2015-11-01T00:00:00Z']


@pytest.mark.parametrize('changes',[{'event_id':'son-1997'},{'reference_event_id':'unknown'},{'period':'12'},{'longitude_index':140},{'depth_index':28},{'depth_index':True},{'longitude_index':1.5}])
def test_invalid_requests_do_not_fall_back(client,changes):
    q=ClimateQuery().model_dump();q.update(changes)
    r=client.post('/api/climate/analyse',json=q)
    assert r.status_code==422,r.text


@pytest.mark.parametrize('changes',[{}, {'event_id':'son-2022','period':'10'}, {'event_id':'son-2013','reference_event_id':'son-2013','period':'09'}])
def test_capture_exact_replay_and_numerical_exports(client,changes):
    d=analyse(client,**changes);record=capture(client,d)
    assert record['replay']['sources']['climate_manifest_sha256']==d['climate_manifest_sha256']
    assert 'heat_manifest_sha256' not in record['replay']['sources']
    assert record['results'][0]['output']==d
    r=client.post('/api/investigations/replay',json=record['replay'])
    assert r.status_code==200,r.text
    assert r.json()['result_sha256']==record['result_sha256']
    assert fingerprint(record['results'])==record['result_sha256']
    for format in ('csv','html','zip'):
        e=client.post('/api/investigations/export',json={'replay':record['replay'],'format':format})
        assert e.status_code==200,e.text[:500]
        if format=='csv':
            rows=list(csv.DictReader(io.StringIO(e.text)))
            assert len(rows)==2*28*(140+70)
            assert rows[0]['baseline_start_year']=='1991'
            assert rows[0]['period']==d['query']['period']
        elif format=='html':
            assert 'GODAS' in e.text and 'Climate analysis' in e.text and '<script' not in e.text
        else:
            with ZipFile(io.BytesIO(e.content)) as z:
                assert {'climate-sections.csv','climate-difference.csv','climate-profiles.csv','climate-index-context.csv','climate-selected-point.csv','SOURCES.json','source-credits.txt'} <= set(z.namelist())
                point=list(csv.DictReader(io.StringIO(z.read('climate-selected-point.csv').decode())))[0]
                assert float(point['selected_potential_temperature_c'])==d['selected_point']['selected']['potential_temperature_c']


def test_save_rejects_wrong_event_case_and_changed_source(client):
    d=analyse(client);recipe=dict(mode='climate',case_id=d['case_id'],query=d['query'])
    for changes in [dict(expected_climate_manifest_sha256='0'*64),dict(recipe={**recipe,'case_id':'pacific-godas-2013-son'})]:
        r=client.post('/api/investigations/capture',json={'title':'Mismatch','recipe':recipe,**changes})
        assert r.status_code==422,r.text


def test_saved_changes_and_result_tampering_stop_replay(client):
    r=capture(client,analyse(client))
    for key in ('expected_result_sha256','expected_recipe_sha256'):
        changed=deepcopy(r['replay']);changed[key]='0'*64
        result=client.post('/api/investigations/replay',json=changed)
        assert result.status_code==422,result.text


def test_pacific_visual_exaggeration_is_saved_without_altering_native_values(client):
    case_id='pacific-godas-2015-son'
    recipe=dict(mode='ocean',case_id=case_id,variable='temperature',time_index=1,view='slice',
                depth_index=10,section_index=7,point=[70,15,10],
                paint=dict(min=10,max=32,log=False,palette='thermal',opacity=1),iso=26,
                exaggeration=6000,window_depth=1000,cutaway=False,quality='basic',show_instruments=True)
    first=client.post('/api/investigations/capture',json={'title':'Pacific native column','recipe':recipe})
    assert first.status_code==200,first.text
    second=client.post('/api/investigations/capture',json={'title':'Same native column','recipe':{**recipe,'exaggeration':1}})
    assert second.status_code==200,second.text
    a,b=first.json(),second.json()
    assert a['replay']['recipe']['exaggeration']==6000
    assert a['results']==b['results'] and a['result_sha256']==b['result_sha256']
    assert a['replay']['expected_recipe_sha256']!=b['replay']['expected_recipe_sha256']
    replay=client.post('/api/investigations/replay',json=a['replay'])
    assert replay.status_code==200 and replay.json()['result_sha256']==a['result_sha256']


def test_missing_pack_does_not_substitute_indian_fields(tmp_path):
    c=TestClient(create_app(case_root=tmp_path))
    r=c.get('/api/climate/catalog')
    assert r.status_code==422 and r.json()['error']['code']=='climate_source_unavailable'


def test_source_fingerprint_failure_and_path_escape_are_blocked(tmp_path):
    source=ROOT/'casepacks/climate/manifest.json'
    dest=tmp_path/'climate';dest.mkdir();(dest/'manifest.json').write_bytes(source.read_bytes())
    (dest/'indices.json').write_text('{}',encoding='utf-8')
    store=ClimateStore(CaseStore(tmp_path),InstrumentStore(tmp_path/'instruments'))
    with pytest.raises(UnsupportedData,match='fingerprint'): store.source('indices.json')
    with pytest.raises(UnsupportedData,match='path is invalid'): store.checked_bytes({'path':'../escape','sha256':'0'*64,'bytes':0})


def test_reference_workspace_library_is_part_of_climate_identity(tmp_path):
    from shutil import copytree
    for folder in ('climate','pacific-godas-2013-son','pacific-godas-2015-son'):
        copytree(ROOT/'casepacks'/folder,tmp_path/folder)
    for case_id in ('pacific-godas-2013-son','pacific-godas-2015-son'):
        copytree(ROOT/'casepacks/instruments'/case_id,tmp_path/'instruments'/case_id)
    path=tmp_path/'instruments/pacific-godas-2013-son/index.json'
    data=json.loads(path.read_text(encoding='utf-8'));data['limitations'].append('Changed reference context')
    path.write_text(json.dumps(data),encoding='utf-8')
    store=ClimateStore(CaseStore(tmp_path),InstrumentStore(tmp_path/'instruments'))
    with pytest.raises(UnsupportedData,match='observation library differs'):
        store.analyse(ClimateQuery())

"""P15 scientific acceptance: original coordinates, identities and bounded resources."""
from pathlib import Path
import gzip,hashlib,json,threading
import numpy as np
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from api.wider_store import WiderStore,ByteCache,regional_csv
from science.wider_contracts import WiderQuery,WiderPack,WiderProfileRequest
from science.contracts import UnsupportedData
from api.app import create_app

ROOT=Path(__file__).resolve().parents[1]

def fixture_store(tmp_path):
    directory=tmp_path/'godas-2022';directory.mkdir()
    axes={'depth':[5.,15.,25.],'lat':[-2.,-1.,0.,1.,2.],'lon':[170.,175.,179.,181.,185.,190.]}
    base=np.arange(90,dtype='<f4').reshape(3,5,6)/100+280;base[1,2,3]=np.float32(-9.96921e36)
    files=[]
    for key in ['pottmp','salt']:
        for i in [8,9]:
            a=base if key=='pottmp' else np.full(base.shape,.035,dtype='<f4')
            name=f'{key}-{i}.f32.gz';b=gzip.compress(a.tobytes(),mtime=0);(directory/name).write_bytes(b)
            files.append({'path':name,'sha256':hashlib.sha256(b).hexdigest(),'shape':list(a.shape),'source_variable':key,'time':f'2022-{i+1:02}-01T00:00:00Z','source_url':'https://example.test/pinned','source_time_index':i})
    (directory/'source.json').write_text(json.dumps({'axes':axes,'files':files,'retrieved_at':'2026-09-26T00:00:00Z'}))
    return WiderStore(tmp_path),base

@pytest.fixture
def small(tmp_path):return fixture_store(tmp_path)
def q(**kw):return WiderQuery(west=170,east=-170,south=-2,north=2,level_min=5,level_max=25,resolution='native',**kw)

def test_dateline_indices_and_exact_conversion(small):
    store,raw=small;r=store.subset(q());assert r['longitude']==[170,175,179,181,185,190];assert r['source_indices']['longitude']==list(range(6))
    assert r['values'][0]==float(raw.flat[0])-273.15;assert r['values'][45] is None;assert r['shape']==[3,5,6]

def test_longitude_equivalence_preserves_data(small):
    store,_=small;r=store.subset(q());r2=store.subset(q().model_copy(update={'west':-180.,'east':-170.}));assert r2['longitude']==[-179,-175,-170];assert r2['source_indices']['longitude']==[3,4,5]
    a=np.asarray(r['values'],dtype=object).reshape(3,5,6)[:,:,3:].ravel().tolist();assert r2['values']==a

def test_source_salinity_is_not_practical(small):
    store,_=small;r=store.subset(q(variable='source_salinity'));assert r['units']=='g/kg';assert r['values'][0]==float(np.float32(.035))*1000;assert 'Not a computed TEOS-10' in r['dataset']['variables']['source_salinity']['definition']

@pytest.mark.parametrize('kw',[{'west':0,'east':0},{'west':0,'east':180},{'south':5,'north':5},{'south':-30,'north':30},{'level_min':50,'level_max':5},{'west':float('nan')},{'time_index':True},{'time_index':2},{'dataset':'../../secrets'},{'variable':'made_up'}])
def test_reject_invalid_requests(kw):
    with pytest.raises(ValidationError):WiderQuery(**kw)

@pytest.mark.parametrize('update,code',[({'south':-3},'outside_coverage'),({'level_min':0},'outside_coverage'),({'level_max':30},'outside_coverage'),({'west':40,'east':50},'empty_subset'),({'variable':'oxygen'},'unsupported_variable')])
def test_valid_but_unsupported_requests(small,update,code):
    store,_=small
    with pytest.raises(UnsupportedData) as e:store.subset(q().model_copy(update=update))
    assert e.value.code==code

def test_preview_never_changes_native(small):
    store,_=small;before=store.subset(q());preview=store.subset(q().model_copy(update={'resolution':'preview'}));after=store.subset(q());assert before==after
    native=np.asarray(before['values'],dtype=object).reshape(before['shape'])
    ids=preview['source_indices'];expected=native[np.ix_(ids['level'],ids['latitude'],ids['longitude'])].ravel().tolist();assert preview['values']==expected

def test_pack_replay_defaults_and_integrity(small):
    store,_=small;p=store.pack(q());assert store.replay(WiderPack(**p))['matched'];assert p==store.pack(WiderQuery.model_validate(json.loads(p['payload_text'])['field']['query']))
    tampered={**p,'payload_text':p['payload_text']+' '}
    with pytest.raises(UnsupportedData,match='checksum'):store.replay(WiderPack(**tampered))

def test_cached_result_mutation_is_isolated(small):
    store,_=small;r=store.subset(q());r['values'][0]=9999;assert store.subset(q())['values'][0]!=9999

def test_warmed_cache_checks_source_bytes(small):
    store,_=small;store.subset(q());p=store.root/'godas-2022/pottmp-8.f32.gz';p.write_bytes(p.read_bytes()+b'bad')
    with pytest.raises(UnsupportedData,match='integrity'):store.subset(q())

def test_unsupported_grid_rejected(small):
    store,_=small;p=store.root/'godas-2022/source.json';d=json.loads(p.read_text());d['axes']['lat']=[-2,0,-1,1,2];p.write_text(json.dumps(d))
    with pytest.raises(UnsupportedData,match='rectilinear'):store.preview(q())

def test_malformed_cycle_rejected(small):
    store,_=small;p=store.root/'godas-2022/source.json';d=json.loads(p.read_text());d['axes']['lon']=[170,179,175,181,185,190];p.write_text(json.dumps(d))
    with pytest.raises(UnsupportedData,match='cycle'):store.preview(q())

def test_missing_grid_shape_rejected(small):
    store,_=small;p=store.root/'godas-2022/source.json';d=json.loads(p.read_text());d['axes']['lat'].append(3);p.write_text(json.dumps(d))
    with pytest.raises(UnsupportedData,match='grid'):store.preview(q())

def test_point_profile_is_exact_and_uninterpolated(small):
    store,raw=small;r=store.profile(WiderProfileRequest(query=q(),longitude=-179,latitude=0));assert r['source_indices']=={'longitude':3,'latitude':2,'level':[0,1,2]};assert r['values']==[float(raw[0,2,3])-273.15,None,float(raw[2,2,3])-273.15]

def test_byte_and_item_cache_limits():
    c=ByteCache(10,2);c.put('a','a',6);c.put('b','b',6);assert c.get('a') is None;assert c.bytes==6
    c.put('c','c',2);c.get('b');c.put('d','d',1);assert c.get('c') is None;assert len(c.entries)==2;c.put('large','x',11);assert c.bytes<=10

def test_per_instance_concurrency_gate_releases(small):
    store,_=small
    with store.capacity(),store.capacity(),store.capacity(),store.capacity():
        with pytest.raises(UnsupportedData) as e:store.subset(q())
        assert e.value.code=='regional_capacity'
    assert store.subset(q())['shape']==[3,5,6]

def test_cap_rejects_before_native_loading(monkeypatch):
    store=WiderStore(ROOT/'casepacks/wider');monkeypatch.setattr(store,'_array',lambda *a:pytest.fail('Native data should not be read'))
    with pytest.raises(UnsupportedData) as e:store.subset(WiderQuery(west=0,east=90,south=-20,north=20))
    assert e.value.code=='subset_too_large'

@pytest.mark.parametrize('dataset,variable,lo,hi',[('godas-2022','potential_temperature',5,459),('godas-2022','source_salinity',5,459),('gobai-v2.2','oxygen',2.5,1975),('gobai-v2.2','oxygen_uncertainty',2.5,1975)])
def test_real_sources_exact_export_and_replay(dataset,variable,lo,hi):
    store=WiderStore(ROOT/'casepacks/wider');query=WiderQuery(dataset=dataset,variable=variable,level_min=lo,level_max=hi)
    p=store.pack(query);assert store.replay(WiderPack(**p))['matched'];payload=json.loads(p['payload_text']);assert len(payload['field']['values'])<=120000
    if variable=='oxygen':assert payload['uncertainty']['query']['variable']=='oxygen_uncertainty'
    assert len(regional_csv(p).splitlines())==len(payload['field']['values'])+1

def test_real_gobai_native_cycle_and_pressure():
    store=WiderStore(ROOT/'casepacks/wider');r=store.subset(WiderQuery(dataset='gobai-v2.2',variable='oxygen',west=170,east=-170,south=-5,north=5,level_min=2.5,level_max=1975,resolution='native'))
    assert r['dataset']['vertical_units']=='dbar';assert r['longitude']==[i+.5 for i in range(170,190)];assert r['source_indices']['longitude']==list(range(150,170));assert r['dataset']['intervals'][0]==['2022-09-01T00:00:00Z','2022-10-01T00:00:00Z'];assert r['time']=='2022-09-15T00:00:00Z'

def test_external_uncertainty_masks_are_independent():
    store=WiderStore(ROOT/'casepacks/wider');query=WiderQuery(dataset='gobai-v2.2',variable='oxygen',west=80,east=100,south=-10,north=5,level_min=2.5,level_max=1975)
    p=json.loads(store.pack(query)['payload_text']);assert p['uncertainty']['units']=='µmol/kg';assert p['field']['source_sha256']==p['uncertainty']['source_sha256'];assert 'quadrature' in p['field']['dataset']['uncertainty_definition']

def test_original_godas_slabs_independent_values():
    """Compare selected output to separately acquired original source slabs."""
    if not (ROOT/'data/raw/wider/pottmp-8-0.npy').is_file():
        pytest.skip("Acquire the original GODAS slabs for independent source checks.")
    store=WiderStore(ROOT/'casepacks/wider');query=WiderQuery(west=-65,east=-45,south=25,north=40,resolution='native')
    r=store.subset(query);indices=r['source_indices'];a=np.concatenate([np.load(ROOT/f'data/raw/wider/pottmp-8-{z}.npy',allow_pickle=False) for z in range(0,28,4)],axis=1)[0]
    expected=[]
    for z in indices['level']:
        for y in indices['latitude']:
            for x in indices['longitude']:
                v=float(a[z,y,x]);expected.append(v-273.15 if 260<=v<=310 else None)
    assert r['values']==expected

def test_original_gobai_big_endian_ranges_independent_values():
    if not (ROOT/'data/raw/wider/gobai/oxy-224.bin').is_file():
        pytest.skip("Acquire the original oxygen source ranges for independent source checks.")
    store=WiderStore(ROOT/'casepacks/wider');query=WiderQuery(dataset='gobai-v2.2',variable='oxygen',west=170,east=-170,south=-5,north=5,level_min=2.5,level_max=1975,resolution='native');r=store.subset(query)
    original=np.frombuffer((ROOT/'data/raw/wider/gobai/oxy-224.bin').read_bytes(),dtype='>f4').reshape(58,145,360);expected=[]
    for z in r['source_indices']['level']:
        for y in r['source_indices']['latitude']:
            for x in r['source_indices']['longitude']:
                v=float(original[z,y,x]);expected.append(v if np.isfinite(v) else None)
    assert r['values']==expected

@pytest.fixture(scope='module')
def client():return TestClient(create_app())

def test_api_flow_and_export(client):
    c=client.get('/api/wider/catalog');assert c.status_code==200;assert len(c.json()['datasets'])==2
    query=WiderQuery().model_dump();assert client.post('/api/wider/preview',json=query).status_code==200
    r=client.post('/api/wider/subset',json=query);assert r.status_code==200
    p=client.post('/api/wider/pack',json=query);assert p.status_code==200;assert client.post('/api/wider/replay',json=p.json()).json()['matched']
    assert client.post('/api/wider/csv',json=query).status_code==200
    # P16B added a real March HYCOM input without replacing the original cases.
    catalog=client.get('/api/catalog').json()
    assert {case['id'] for case in catalog['cases']} == {
        'bay-bengal-2024-01', 'arabian-sea-2024-01', 'bay-bengal-2024-03',
        'pacific-godas-2013-son', 'pacific-godas-2015-son', 'pacific-godas-2022-son',
    }
    assert client.get('/api/health').json()['case_count']==6

@pytest.mark.parametrize('change,status',[({'dataset':'../'},422),({'time_index':3},422),({'west':0,'east':90,'south':-20,'north':20},413),({'north':90,'south':70},422),({'resolution':'magic'},422)])
def test_api_limits(client,change,status):
    response=client.post('/api/wider/subset',json={**WiderQuery().model_dump(),**change});assert response.status_code==status;assert 'error' in response.json()

def test_unknown_url_cannot_trigger_fetch(client):
    r=client.post('/api/wider/subset',json={**WiderQuery().model_dump(),'url':'https://example.com'});assert r.status_code==422

def test_api_request_body_limit(client):
    r=client.post('/api/wider/subset',content=' '*8200,headers={'Content-Type':'application/json'});assert r.status_code==413

def test_api_busy_is_explicit_and_recovers(client):
    store=client.app.state.wider
    with store.capacity(),store.capacity(),store.capacity(),store.capacity():
        r=client.post('/api/wider/subset',json=WiderQuery().model_dump());assert r.status_code==429;assert r.json()['error']['code']=='regional_capacity'
    assert client.post('/api/wider/subset',json=WiderQuery().model_dump()).status_code==200

def test_source_loader_recognises_actual_cdf2_header(tmp_path):
    import netCDF4,struct
    from science.acquire_gobai import header
    path=tmp_path/'original.nc'
    with netCDF4.Dataset(path,'w',format='NETCDF3_64BIT_OFFSET') as ds:
        ds.createDimension('time',2);ds.createDimension('pres',2);ds.createDimension('lat',2);ds.createDimension('lon',2)
        v=ds.createVariable('oxy','f4',('time','pres','lat','lon'));v.units='micromoles per kilogram';v[:]=np.arange(16).reshape(2,2,2,2)
    raw=path.read_bytes();h=header(raw);v=h['variables'][0];assert [x[0] for x in v['dimensions']]==['time','pres','lat','lon'];assert struct.unpack_from('>f',raw,v['offset']+11*4)[0]==11

def test_curvilinear_adapter_rejected(small):
    store,_=small;p=store.root/'godas-2022/source.json';d=json.loads(p.read_text());d['axes']['lat']=[[-2,-1,0,1,2]]*5;p.write_text(json.dumps(d))
    with pytest.raises(UnsupportedData):store.preview(q())

def test_all_missing_native_result_is_not_zero():
    store=WiderStore(ROOT/'casepacks/wider');r=store.subset(WiderQuery(west=10,east=20,south=15,north=25))
    assert r['valid_count']==0;assert all(v is None for v in r['values'])


def test_missing_cached_native_file_is_not_silently_reused(small):
    store,_=small
    store.subset(q())
    _,_,_,_,record=store.selection(q())
    (store.root/q().dataset/record['path']).unlink()
    with pytest.raises(UnsupportedData) as exc:store.subset(q())
    assert exc.value.code=='source_unavailable'

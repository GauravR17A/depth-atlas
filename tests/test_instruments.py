"""P04 acceptance: source references, independent QC semantics and bounded IO."""
import csv
import io
import json
import hashlib
from pathlib import Path
import netCDF4
import numpy as np
import pytest
from fastapi.testclient import TestClient
from adapters.instruments import parse_instruments,reading
from api.app import create_app
from api.instrument_store import InstrumentStore
from science.contracts import UnsupportedData
from test_science_adapters import argo_fixture

ROOT=Path(__file__).resolve().parents[1]
EXAMPLES=ROOT/'casepacks/instruments/examples'


def parse(path):return parse_instruments(path.read_bytes(),path.name).profiles


def test_argo_quality_is_parameter_specific_and_missing_adjusted_never_backfills(tmp_path):
    p=parse(argo_fixture(tmp_path/'argo.nc'))[0]
    assert p.levels[1].readings['temperature'].accepted  # salinity QC 4 must not invalidate temperature
    assert not p.levels[1].readings['salinity'].accepted
    r=p.levels[2].readings['temperature']
    assert r.value is None and r.raw==33 and not r.accepted
    assert p.parameters['temperature'].accepted_count==2
    assert p.levels[0].depth_m==pytest.approx(9.9445834469453,abs=1e-9)
    assert p.time=='2024-01-01T12:00:00Z'


@pytest.mark.parametrize('mode,expected,field',[('R',31,'TEMP'),('A',21,'TEMP_ADJUSTED'),('D',21,'TEMP_ADJUSTED')])
def test_core_modes(tmp_path,mode,expected,field):
    p=parse(argo_fixture(tmp_path/'mode.nc',mode=mode))[0]
    assert p.levels[0].readings['temperature'].value==expected
    assert p.parameters['temperature'].source_field==field


@pytest.mark.parametrize('scheme,flag,passes',[('argo','2',True),('qartod','2',False),('qartod','1',True),('woce','1',False),('woce','2',True),('woce','3',False),('argo','8',False),('argo','9',False)])
def test_quality_flags_are_not_interchangeable(scheme,flag,passes):
    assert reading(20,flag,scheme,True).accepted is passes


def test_bgc_parameter_modes_and_source_values_are_preserved():
    path=EXAMPLES/'SR6903091_100.nc';p=parse(path)[0]
    assert p.instrument=='bgc'
    assert p.parameters['temperature'].mode=='R'
    assert p.parameters['oxygen'].mode=='A'
    assert p.parameters['oxygen'].source_field=='DOXY_ADJUSTED'
    assert p.parameters['oxygen'].accepted_count==351
    with netCDF4.Dataset(path) as d:
        selected=next(l for l in p.levels if l.readings['oxygen'].accepted);j=selected.index
        assert selected.readings['oxygen'].value==float(d['DOXY_ADJUSTED'][0,j])
        assert selected.readings['oxygen'].raw==float(d['DOXY'][0,j])
        assert selected.latitude==float(d['LATITUDE'][0])
    assert not reading(125,'1','argo',True,mode='R',bgc=True).accepted


@pytest.mark.parametrize('change,code',[('unit','incompatible_units'),('definition','incompatible_variable'),('mode','unsupported_data_mode'),('calendar','unsupported_calendar'),('position','invalid_position'),('bad_pressure',None)])
def test_bad_or_unsupported_argo_metadata(tmp_path,change,code):
    path=argo_fixture(tmp_path/'bad.nc')
    with netCDF4.Dataset(path,'a') as d:
        if change=='unit':d['TEMP_ADJUSTED'].units='kelvin'
        if change=='definition':d['TEMP_ADJUSTED'].standard_name='sea_water_potential_temperature'
        if change=='mode':d['DATA_MODE'][:]=np.array(['X'],dtype='S1')
        if change=='calendar':d['JULD'].calendar='360_day'
        if change=='position':d['LATITUDE'][:]=99
        if change=='bad_pressure':d['PRES_ADJUSTED'][:]=[[-10,50,125]]
    if code:
        with pytest.raises(UnsupportedData) as error:parse(path)
        assert error.value.code==code
    else:
        p=parse(path)[0];assert p.levels[0].depth_m is None and not p.levels[0].readings['temperature'].accepted


def test_genuine_glider_movement_qartod_and_inconsistent_metadata():
    path=EXAMPLES/'glider-ru29.nc';profiles=parse(path)
    assert len(profiles)==4
    p=profiles[2]
    assert p.samples==1582 and len(p.track)>1 and p.time!=p.time_end
    with netCDF4.Dataset(path) as d:
        for l in [p.levels[0],p.levels[500],p.levels[-1]]:
            j=l.index
            assert l.latitude==float(d['precise_lat'][j])
            assert l.longitude==float(d['precise_lon'][j])
            assert l.time==netCDF4.num2date(round(float(d['precise_time'][j])),d['precise_time'].units).strftime('%Y-%m-%dT%H:%M:%SZ')
        l=next(l for l in p.levels if l.readings['temperature'].accepted)
        assert l.readings['temperature'].value==float(d['temperature'][l.index])
    assert p.parameters['temperature'].accepted_count==959
    assert p.parameters['salinity'].accepted_count==0
    assert any('range metadata' in w for w in p.warnings)
    assert any(l.readings['salinity'].value is not None for l in p.levels)
    assert all(not l.readings['salinity'].accepted for l in p.levels)


def test_ctd_exchange_known_source_rows_units_and_missing_oxygen():
    p=parse(EXAMPLES/'ctd-station.csv')[0]
    assert p.time=='1996-02-21T11:16:00Z' and p.latitude==-33.1947 and p.longitude==28.0603
    assert p.samples==48 and p.levels[0].pressure_dbar==4
    assert p.levels[0].readings['temperature'].value==25.1553
    assert p.levels[0].readings['salinity'].value==35.2359
    assert p.levels[0].readings['oxygen'].value is None
    assert p.parameters['oxygen'].accepted_count==0


def test_documented_csv_preserves_real_values_and_does_not_claim_adjustments():
    p=parse(EXAMPLES/'argo-2903891-example.csv')[0];native=parse(EXAMPLES/'D2903891_012.nc')[0]
    assert p.samples==20 and p.parameters['temperature'].mode=='user supplied'
    for a,b in zip(p.levels,native.levels):
        assert a.depth_m==b.depth_m and a.time==b.time
        assert a.readings['temperature'].value==b.readings['temperature'].value
        assert a.readings['temperature'].adjusted is None


@pytest.mark.parametrize('edit,code',[('no_qc','missing_variable'),('no_timezone','invalid_time'),('bad_position','invalid_position'),('wrong_columns','invalid_csv'),('multiple_instruments','inconsistent_metadata')])
def test_csv_metadata_rejection(edit,code):
    body=(EXAMPLES/'argo-2903891-example.csv').read_text();rows=list(csv.DictReader(io.StringIO(body)));fields=list(rows[0])
    if edit=='no_qc':fields.remove('temperature_qc');[r.pop('temperature_qc') for r in rows]
    if edit=='no_timezone':rows[0]['time']=rows[0]['time'].replace('Z','')
    if edit=='bad_position':rows[0]['longitude']='200'
    if edit=='multiple_instruments':rows[1]['instrument']='glider'
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows);body=stream.getvalue()
    if edit=='wrong_columns':body+='broken,row\n'
    with pytest.raises(UnsupportedData) as error:parse_instruments(body.encode(),'test.csv')
    assert error.value.code==code


def test_parser_size_type_and_dimension_limits(tmp_path):
    for data,name in [(b'x'*2_000_001,'file.csv'),(b'x','file.zip'),(b'not netcdf','file.nc')]:
        with pytest.raises(UnsupportedData):parse_instruments(data,name)
    path=tmp_path/'oversized.nc'
    with netCDF4.Dataset(path,'w') as d:d.createDimension('N_PROF',25);d.createDimension('N_LEVELS',10)
    with pytest.raises(UnsupportedData) as error:parse(path)
    assert error.value.code=='file_limits'


def test_library_hashes_types_counts_and_unchanged_model_pack():
    store=InstrumentStore(ROOT/'casepacks/instruments');catalog=store.catalog()
    assert len(catalog['profiles'])==13 and {p['instrument'] for p in catalog['profiles']}=={'argo','ctd','bgc','glider'}
    for summary in catalog['profiles']:
        p=store.read(summary['id']);assert p.samples==len(p.levels)
        for k,v in p.parameters.items():assert v.accepted_count==sum(l.readings[k].accepted for l in p.levels)
    assert hashlib.sha256((ROOT/'casepacks/bay-bengal-2024-01/manifest.json').read_bytes()).hexdigest()=='9598b33dc9eef89cb909f2811e1590ca580a143c1dbcc25d97e51a84faf7d28d'


def test_api_genuine_examples_import_rejection_and_request_only_storage():
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'casepacks').rglob('*') if p.is_file()}
    with TestClient(create_app()) as client:
        catalog=client.get('/api/instruments');assert catalog.status_code==200
        for example in catalog.json()['examples']:
            response=client.get('/api/instruments/examples/'+example['name']);assert response.status_code==200
            parsed=client.post('/api/instruments/import',params={'filename':example['name']},content=response.content)
            assert parsed.status_code==200,parsed.text
            assert parsed.json()['persistence']=='request_only'
        assert client.get('/api/instruments/profiles/no-such-id').status_code==404
        assert client.get('/api/instruments/examples/not-a-file').status_code==404
        r=client.post('/api/instruments/import?filename=bad.csv',content=b'x'*2_000_001)
        assert r.status_code==413 and 'request_id' in r.json()['error']
        assert client.post('/api/instruments/import?filename=file.csv',content=b'a,b\n1,2').status_code==422
        assert client.post('/api/instruments/import?filename=file.csv',content=b'anything',headers={'Content-Encoding':'gzip'}).status_code==422
    after={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'casepacks').rglob('*') if p.is_file()}
    assert before==after

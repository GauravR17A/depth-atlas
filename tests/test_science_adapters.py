"""Independent numeric expectations and hostile/unsupported scientific inputs."""

from pathlib import Path

import gsw
import netCDF4
import numpy as np
import pytest

from adapters.argo import parse_argo
from adapters.cf_model import load_model
from science.contracts import UnsupportedData


def model_fixture(path: Path):
    with netCDF4.Dataset(path, "w") as ds:
        for key, vals, attrs in [
            ("time", [24, 0], {"units":"hours since 2024-01-01 00:00:00", "calendar":"gregorian"}),
            ("depth", [100, 10, 0], {"units":"m", "positive":"down"}),
            ("lat", [14, 12], {"units":"degrees_north"}),
            ("lon", [10, 350, 0], {"units":"degrees_east"}),
        ]:
            ds.createDimension(key,len(vals))
            v=ds.createVariable(key,"f8",(key,));v.setncatts(attrs);v[:]=vals
        variables = [("water_temp","sea_water_temperature","degC",20), ("salinity","sea_water_salinity","psu",20), ("water_u","eastward_sea_water_velocity","m/s",0), ("water_v","northward_sea_water_velocity","m/s",0)]
        # Source value is 1000*t + 100*z + 10*y + x, independent of adapter order.
        values=np.arange(2)[:,None,None,None]*1000+np.arange(3)[None,:,None,None]*100+np.arange(2)[None,None,:,None]*10+np.arange(3)[None,None,None,:]
        for name,standard,unit,offset in variables:
            v=ds.createVariable(name,"i2",("time","depth","lat","lon"),fill_value=-30000)
            v.setncatts({"standard_name":standard,"units":unit,"scale_factor":0.01,"add_offset":float(offset),"valid_range":np.array([-1000,2000],dtype='i2')})
            v.set_auto_maskandscale(False)
            a=values.copy();a[0,0,0,0]=-30000;a[0,0,0,1]=3000
            v[:]=a
    return path


def test_coordinate_reordering_irregular_depth_and_packed_values(tmp_path):
    grid=load_model(model_fixture(tmp_path/'case.nc'))
    assert grid.coordinates.depth_m == [0,10,100]
    assert grid.coordinates.latitude == [12,14]
    assert grid.coordinates.longitude == [-10,0,10]
    assert grid.coordinates.times == ['2024-01-01T00:00:00Z','2024-01-02T00:00:00Z']
    # time=Jan1 -> original t1, z0m -> original z2, lat12 -> y1, lon-10 -> x1.
    assert grid.fields['temperature'][0,0,0,0] == pytest.approx(32.11,abs=1e-12)
    assert grid.fields['eastward_velocity'][0,0,0,0] == pytest.approx(12.11,abs=1e-12)
    # Source fill and packed-domain invalid range must remain missing after reorder.
    assert np.isnan(grid.fields['temperature'][1,2,1,2])
    assert np.isnan(grid.fields['temperature'][1,2,1,0])
    assert grid.source_metadata['original_coordinates']['depth'] == [100,10,0]


def test_positive_up_metres_have_explicit_conversion(tmp_path):
    path=model_fixture(tmp_path/'up.nc')
    with netCDF4.Dataset(path,'a') as d:
        d['depth'][:]=[-100,-10,0];d['depth'].positive='up'
    assert load_model(path).coordinates.depth_m == [0,10,100]


@pytest.mark.parametrize('change,code',[
    ('duplicate_longitude','invalid_coordinates'),('calendar','unsupported_calendar'),
    ('potential_temperature','incompatible_variable'),('pressure_axis','unsupported_depth'),
    ('rotated_velocity','incompatible_variable'),('bad_coordinate','invalid_coordinates'),
])
def test_unsupported_semantics_are_rejected(tmp_path,change,code):
    path=model_fixture(tmp_path/'unsupported.nc')
    with netCDF4.Dataset(path,'a') as d:
        if change=='duplicate_longitude':d['lon'][:]=[0,360,10]
        elif change=='calendar':d['time'].calendar='360_day'
        elif change=='potential_temperature':d['water_temp'].standard_name='sea_water_potential_temperature'
        elif change=='pressure_axis':d['depth'].units='dbar'
        elif change=='rotated_velocity':d['water_u'].standard_name='sea_water_x_velocity'
        elif change=='bad_coordinate':d['lat'][:]=[14,100]
    with pytest.raises(UnsupportedData) as error:load_model(path)
    assert error.value.code == code


def argo_fixture(path: Path, mode='D'):
    with netCDF4.Dataset(path,'w') as d:
        d.createDimension('N_PROF',1);d.createDimension('N_LEVELS',3);d.createDimension('STRING8',8)
        for name,val in [('DATA_MODE',mode),('POSITION_QC','1'),('JULD_QC','1')]:
            d.createVariable(name,'S1',('N_PROF',))[:]=np.array([val],dtype='S1')
        d.createVariable('PLATFORM_NUMBER','S1',('N_PROF','STRING8'))[:]=np.array(list('1234567 '),dtype='S1')[None,:]
        d.createVariable('CYCLE_NUMBER','i4',('N_PROF',))[:]=12
        for name,val in [('LATITUDE',4),('LONGITUDE',88)]:d.createVariable(name,'f8',('N_PROF',),fill_value=99999)[:]=val
        j=d.createVariable('JULD','f8',('N_PROF',));j.units='days since 2024-01-01 00:00:00';j[:]=0.5
        for name,standard,unit,raw,adjusted in [
            ('PRES','sea_water_pressure','decibar',[10,50,125],[10,50,125]),
            ('TEMP','sea_water_temperature','degree_Celsius',[31,32,33],[21,22,99999]),
            ('PSAL','sea_water_salinity','psu',[35,35,35],[34,34,34]),
        ]:
            for suffix,vals in [('',raw),('_ADJUSTED',adjusted),('_ADJUSTED_ERROR',[0.1,0.1,0.1])]:
                v=d.createVariable(name+suffix,'f4',('N_PROF','N_LEVELS'),fill_value=99999);v.units=unit;v.standard_name=standard;v[:]=[vals]
            for suffix in ['_QC','_ADJUSTED_QC']:
                flags=['1','4','1'] if name=='PSAL' and suffix=='_ADJUSTED_QC' else ['1','1','1']
                d.createVariable(name+suffix,'S1',('N_PROF','N_LEVELS'))[:]=np.array([flags],dtype='S1')
    return path


def test_argo_uses_adjusted_preserves_raw_and_never_backfills(tmp_path):
    p=parse_argo(argo_fixture(tmp_path/'argo.nc'),'https://example.test/fixture.nc')[0]
    assert p.eligible_samples == 1
    assert p.levels[0]['temperature_c'] == 21
    assert p.levels[0]['parameters']['TEMP']['raw'] == 31
    assert p.levels[0]['parameters']['TEMP']['adjusted_error'] == pytest.approx(0.1)
    assert p.levels[1]['eligible'] is False  # bad salinity QC
    assert p.levels[2]['temperature_c'] is None  # adjusted missing, even though raw=33
    assert p.levels[2]['eligible'] is False
    assert p.time == '2024-01-01T12:00:00Z'
    # Published GSW example at 4N and 10 dbar, independent of this adapter.
    assert p.levels[0]['depth_m'] == pytest.approx(9.9445834469453,abs=1e-9)
    assert p.levels[0]['pressure_dbar'] == 10


def test_real_time_argo_selects_raw_without_hiding_mode(tmp_path):
    p=parse_argo(argo_fixture(tmp_path/'argo.nc',mode='R'),'https://example.test/fixture.nc')[0]
    assert p.data_mode == 'R'
    assert p.selected_fields['TEMP'] == 'TEMP'
    assert p.levels[2]['temperature_c'] == 33


def test_pressure_depth_conversion_matches_published_gsw_example():
    # https://www.teos-10.org/pubs/gsw/html/gsw_z_from_p.html (published example)
    expected=[9.9445834469453,49.7180897012550,124.2726219409978,248.4700576548589,595.8253480356214,992.0919060719987]
    np.testing.assert_allclose(-gsw.z_from_p([10,50,125,250,600,1000],4),expected,rtol=0,atol=1e-9)

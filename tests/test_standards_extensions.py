"""Extension and exchange boundaries, checked against original-file expectations."""
import json
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import netCDF4
import numpy as np
import pytest
from pydantic import ValidationError

from adapters.registry import ADAPTERS, Adapter, AdapterRegistry
from api.app import create_app
from science.check_cf_exchange import check_exchange
from science.contracts import UnsupportedData
from science.products import PRODUCTS, ProductMetadata, ProductRegistry, ScalarProduct

ROOT=Path(__file__).resolve().parents[1]
EXCHANGE=ROOT/'casepacks/standards/bay-bengal-2024-01.nc'


def test_cf_exchange_and_second_adapter_preserve_shared_grid():
    assert check_exchange(EXCHANGE)['passed']
    grid=ADAPTERS.load('cf-exchange',EXCHANGE)
    assert len(grid.coordinates.times)==7
    assert grid.coordinates.depth_m[19]==100
    assert grid.coordinates.longitude[0]==85.0400390625
    assert grid.fields['temperature'].shape==(7,40,76,63)
    assert np.isnan(grid.fields['temperature'][:,-1]).all()
    assert grid.fields['temperature'][1,19,10,10]==pytest.approx(21.178000055951998,abs=1e-12)
    assert grid.variables[1].standard_name=='sea_water_practical_salinity'


@pytest.mark.parametrize('mutation',['unit','calendar','depth_direction','axis_fill','variable_definition','missing_axis','coordinate_order'])
def test_cf_checks_reject_misleading_metadata(tmp_path,mutation):
    path=tmp_path/'bad.nc';shutil.copyfile(EXCHANGE,path)
    with netCDF4.Dataset(path,'a') as ds:
        if mutation=='unit':ds['salinity'].units='g/kg'
        elif mutation=='calendar':ds['time'].calendar='360_day'
        elif mutation=='depth_direction':ds['depth'].positive='up'
        elif mutation=='axis_fill':ds['depth'].missing_value=-999.
        elif mutation=='variable_definition':ds['temperature'].standard_name='sea_water_potential_temperature'
        elif mutation=='missing_axis':ds.renameVariable('longitude','x')
        elif mutation=='coordinate_order':ds['latitude'][:]=ds['latitude'][:][::-1]
    assert not check_exchange(path)['passed']


def test_registries_cannot_replace_registered_code_or_load_upload_names(tmp_path):
    registry=AdapterRegistry();a=Adapter('sample','1','adapters.cf_exchange:load_exchange','CF')
    registry.register(a)
    with pytest.raises(ValueError):registry.register(a)
    with pytest.raises(UnsupportedData):registry.load('../../untrusted',tmp_path/'a.nc')
    products=ProductRegistry();product=PRODUCTS.get('horizontal_kinetic_energy');products.register(product)
    with pytest.raises(ValueError):products.register(product)


def test_product_joint_mask_and_vector_components():
    result=PRODUCTS.evaluate('horizontal_kinetic_energy',dict(eastward_velocity=np.array([3.,-3,0,np.nan,4]),northward_velocity=np.array([4.,4,0,3,np.nan])))
    np.testing.assert_equal(result,np.array([12.5,12.5,0,np.nan,np.nan]))
    with pytest.raises(UnsupportedData):PRODUCTS.evaluate('horizontal_kinetic_energy',dict(eastward_velocity=np.ones(2),northward_velocity=np.ones(3)))
    with pytest.raises(UnsupportedData):PRODUCTS.evaluate('horizontal_kinetic_energy',dict(eastward_velocity=np.ones(2)))


def test_external_ml_contract_requires_provenance_and_evaluator_cannot_fill_masks():
    metadata=dict(id='external_example',label='External example',kind='ml_derived',units='degree_Celsius',definition='Externally produced temperature estimate',method_id='external/v1',inputs=['temperature'],limitations=['Not installed or available in this app.'])
    with pytest.raises(ValidationError):ProductMetadata(**metadata)
    spec=ProductMetadata(**metadata,model_version='test-only',training_data_reference='fixture-only',validation_reference='fixture-only')
    registry=ProductRegistry();registry.register(ScalarProduct(spec,lambda f:np.zeros_like(f['temperature'])))
    assert np.isnan(registry.evaluate('external_example',{'temperature':np.array([np.nan])})[0])
    assert all(p['kind']!='ml_derived' for p in PRODUCTS.catalog())


@pytest.mark.parametrize('row',json.loads((ROOT/'tests/fixtures/p06-source-samples.json').read_text())['rows'])
def test_native_derived_api_matches_original_file_expectations(row):
    with TestClient(create_app()) as client:
        params=dict(variable='horizontal_kinetic_energy',time_index=row['time_index'],depth_index=row['depth_index'],west=row['longitude'],east=row['longitude'],south=row['latitude'],north=row['latitude'])
        response=client.get('/api/cases/bay-bengal-2024-01/subset',params=params)
        assert response.status_code==200
        body=response.json();assert body['kind']=='derived' and body['units']=='m²/s²'
        assert body['values']==[None] if row['expected'] is None else body['values'][0]==pytest.approx(row['expected'],abs=1e-12)
        assert 'horizontal-ke-v1' in body['processing']


def test_public_contracts_and_download_allowlist():
    with TestClient(create_app()) as client:
        products=client.get('/api/products').json();assert len(products['products'])==1
        access=client.get('/api/data-access').json();assert access['standards']['public_url'] is None
        assert {a['id'] for a in access['adapters']} == {'hycom-rectilinear', 'cf-exchange', 'godas-monthly-subset', 'gobai-oxygen'}
        assert client.get('/data/manifest.json').json()['conventions']=='CF-1.10'
        assert client.get('/data/unknown.nc').status_code==404
        assert client.get('/api/cases/bay-bengal-2024-01/subset?variable=unregistered').status_code==422

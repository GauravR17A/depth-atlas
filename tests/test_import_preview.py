"""Independent conversion examples, original CHLA values and adversarial import review."""
import csv
import hashlib
import io
import json
from pathlib import Path

import netCDF4
import pytest
from fastapi.testclient import TestClient

from adapters.import_preview import inspect_import
from api.app import create_app
from science.contracts import UnsupportedData

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'casepacks/instruments/examples'


def mapped_file():
    # Synthetic, analytical fixture only. It is never published as an observation.
    return (b'profile_id,instrument,platform,time,latitude,longitude,pressure_dbar,pressure_qc,position_qc,time_qc,water_temperature,temperature_flag,chlorophyll,chlorophyll_flag,unused\n'
            b'a,ctd,test,2024-01-08T00:00:00Z,13,87,10,1,1,1,300,1,0.002,2,note\n'
            b'a,ctd,test,2024-01-08T00:00:00Z,13,87,20,1,1,1,,9,0.003,4,note\n')


MAPPING = {'temperature_c': {'source': 'water_temperature', 'units': 'K'},
           'temperature_qc': {'source': 'temperature_flag'},
           'chlorophyll_mg_m3': {'source': 'chlorophyll', 'units': 'mg/L'},
           'chlorophyll_qc': {'source': 'chlorophyll_flag'}}


def test_missing_names_offer_mapping_without_claiming_a_parsed_result():
    result = inspect_import(mapped_file(), 'custom.csv')
    assert result['result'] is None and result['mapping_supported']
    assert 'water_temperature' in result['columns'] and result['issue']


def test_kelvin_and_chlorophyll_conversion_preserve_missing_qc_and_original_identity():
    review = inspect_import(mapped_file(), 'custom.csv', MAPPING)
    p = review['result']['profiles'][0]
    assert p['source_sha256'] == hashlib.sha256(mapped_file()).hexdigest()
    assert p['levels'][0]['readings']['temperature']['value'] == pytest.approx(26.85, abs=1e-12)
    assert p['levels'][0]['readings']['chlorophyll']['value'] == 2
    assert p['levels'][1]['readings']['temperature']['value'] is None
    assert not p['levels'][1]['readings']['chlorophyll']['accepted']
    assert p['levels'][1]['readings']['chlorophyll']['value'] == 3
    assert p['parameters']['temperature']['source_field'] == 'water_temperature'
    assert p['metadata']['import_mapping']['temperature_c']['offset'] == -273.15
    assert review['ignored_fields'] == ['unused']
    changed = inspect_import(mapped_file(), 'custom.csv', {**MAPPING, 'temperature_c': {'source': 'water_temperature', 'units': 'degC'}})
    assert changed['result']['profiles'][0]['id'] != p['id']


@pytest.mark.parametrize('bad', [
    {'temperature_c': {'source': 'water_temperature', 'units': 'F'}},
    {'oxygen_umol_kg': {'source': 'water_temperature', 'units': 'mg/L'}},
    {'latitude': {'source': 'latitude', 'units': 'radians'}},
    {'temperature_c': {'source': 'water_temperature', 'units': ['K']}},
    {'surprise': {'source': 'water_temperature'}},
    {'temperature_qc': {'source': 'temperature_flag'}, 'pressure_qc': {'source': 'temperature_flag'}},
])
def test_unsupported_ambiguous_or_wrong_dimension_mapping_is_rejected(bad):
    with pytest.raises(UnsupportedData): inspect_import(mapped_file(), 'bad.csv', bad)


def test_native_inputs_are_not_relabelled_and_documented_units_cannot_be_overridden():
    with pytest.raises(UnsupportedData): inspect_import((EXAMPLES/'D2903891_012.nc').read_bytes(), 'float.nc', MAPPING)
    with pytest.raises(UnsupportedData):
        inspect_import((EXAMPLES/'argo-2903891-example.csv').read_bytes(), 'argo.csv', {'temperature_c': {'source': 'temperature_c', 'units': 'K'}})


def test_duplicate_columns_and_long_rows_rejected_before_a_preview():
    for body in [b'lat,lat\n1,2\n', b'a,b\n1,2,3\n', b'a,b\n1\n']:
        with pytest.raises(UnsupportedData): inspect_import(body, 'bad.csv')


def test_chlorophyll_matches_native_adjusted_values_and_raw_flags_without_model_claim():
    path = EXAMPLES/'SR1902594_034.nc'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '1368b43fca3d535e3d4745cfcc0c477706ce5e121137ae18e0bf4ac9a613bc2c'
    review = inspect_import(path.read_bytes(), path.name)
    p = review['result']['profiles'][0]
    assert p['time'] == '2024-03-29T02:30:44Z'
    assert 85.04 < p['longitude'] < 90 and 12 < p['latitude'] < 15
    assert p['parameters']['chlorophyll']['accepted_count'] == 1171
    assert p['parameters']['chlorophyll']['source_field'] == 'CHLA_ADJUSTED'
    assert 'CHLA_FLUORESCENCE' in review['ignored_fields']
    with netCDF4.Dataset(path) as ds:
        accepted = [l for l in p['levels'] if l['readings']['chlorophyll']['accepted']]
        for l in [accepted[0], accepted[len(accepted)//2], accepted[-1]]:
            j = l['index']
            assert l['readings']['chlorophyll']['value'] == float(ds['CHLA_ADJUSTED'][0,j])
            assert l['readings']['chlorophyll']['raw'] == float(ds['CHLA'][0,j])
        missing = next(l for l in p['levels'] if l['readings']['chlorophyll']['value'] is None)
        assert not missing['readings']['chlorophyll']['accepted']


def test_preview_api_retains_files_recognizes_only_exact_public_source_and_rejects_bad_maps():
    before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'casepacks').rglob('*') if p.is_file()}
    with TestClient(create_app()) as c:
        body = (EXAMPLES/'SR1902594_034.nc').read_bytes()
        r = c.post('/api/instruments/inspect?filename=renamed.nc', content=body)
        assert r.status_code == 200, r.text
        assert r.json()['result']['profiles'][0]['source_url'].endswith('SR1902594_034.nc')
        r = c.post('/api/instruments/inspect?filename=custom.csv', content=mapped_file(), headers={'X-Ocean-Column-Mapping': json.dumps(MAPPING)})
        assert r.status_code == 200, r.text
        assert r.json()['result']['profiles'][0]['source_url'] == ''
        for mapping in ['null', '[]', 'not-json']:
            assert c.post('/api/instruments/inspect?filename=a.csv', content=mapped_file(), headers={'X-Ocean-Column-Mapping':mapping}).status_code == 422
        assert c.post('/api/instruments/inspect?filename=a.csv', content=b'x'*2_000_001).status_code == 413
    assert before == {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before}


def test_extra_example_preserves_the_frozen_library_and_every_example_fits_preview_budget():
    from api.instrument_store import InstrumentStore
    store = InstrumentStore(ROOT/'casepacks/instruments')
    assert hashlib.sha256((store.root/'index.json').read_bytes()).hexdigest() == 'b1fc70a489a594dc8b9e11aacd0b087166dee396b4e2a79ac77884e96d02a082'
    assert len(store.index()['profiles']) == 13
    assert len(store.catalog()['examples']) == len(store.index()['examples']) + 1
    for example in store.catalog()['examples']:
        path = store.example(example['name'])
        result = inspect_import(path.read_bytes(), path.name)
        assert result['result']['profiles'], path.name
        assert len(json.dumps(result,separators=(',',':')).encode()) <= 3_500_000

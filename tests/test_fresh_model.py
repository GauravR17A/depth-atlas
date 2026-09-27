"""Fresh input, independent source arrays, import overlap and replay boundaries."""
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np
import pytest

from api.app import create_app
from api.case_store import CaseStore
from adapters.registry import ADAPTERS
from science.check_cf_exchange import check_exchange

ROOT=Path(__file__).resolve().parents[1]
CASE='bay-bengal-2024-03'
REFERENCE=json.loads((ROOT/'tests/fixtures/p16b-source-reference.json').read_text())


@pytest.mark.parametrize('row',REFERENCE['rows'],ids=lambda r:f'{r["variable"]}-{r["time_index"]}')
def test_every_native_value_and_mask_against_independent_source_hash(row):
    store=CaseStore(ROOT/'casepacks')
    a=np.asarray(store._read_array(CASE,'analytical',row['variable'],row['time_index']),dtype='<f8')
    a[np.isnan(a)]=np.nan
    assert hashlib.sha256(a.tobytes()).hexdigest()==row['sha256']
    assert np.isnan(a).sum()==row['missing']


def test_exchange_adapter_matches_fresh_case_without_new_decoder():
    path=ROOT/'casepacks/standards'/f'{CASE}.nc'
    assert check_exchange(path)['passed']
    grid=ADAPTERS.load('cf-exchange',path)
    assert grid.coordinates.times==[r['time'] for r in REFERENCE['rows'] if r['variable']=='temperature']
    for row in REFERENCE['rows']:
        if row['variable']=='horizontal_kinetic_energy':continue
        a=grid.fields[row['variable']][row['time_index']].astype('<f8');a[np.isnan(a)]=np.nan
        assert hashlib.sha256(a.tobytes()).hexdigest()==row['sha256']


def test_chlorophyll_import_has_real_space_time_overlap_without_claimed_model_chlorophyll():
    with TestClient(create_app()) as client:
        m=client.get('/api/cases/'+CASE).json()
        path=ROOT/'casepacks/instruments/examples/SR1902594_034.nc'
        r=client.post('/api/instruments/import?filename='+path.name,content=path.read_bytes())
        assert r.status_code==200,r.text
        p=r.json()['profiles'][0]
        assert m['coordinates']['times'][0]<p['time']<m['coordinates']['times'][-1]
        w,s,e,n=m['case']['bounds']
        assert w<=p['longitude']<=e and s<=p['latitude']<=n
        assert any(level['readings'].get('chlorophyll',{}).get('accepted') for level in p['levels'])
        assert 'chlorophyll' not in m['case']['variables']
        assert m['profiles']==[]
        assert m['representations']['unavailable_tools']==['heat']


def test_frozen_observation_library_is_unchanged():
    assert hashlib.sha256((ROOT/'casepacks/instruments/index.json').read_bytes()).hexdigest()=='b1fc70a489a594dc8b9e11aacd0b087166dee396b4e2a79ac77884e96d02a082'


def test_case_tool_availability_matches_scientific_method_gates():
    with TestClient(create_app()) as client:
        catalog=client.get('/api/catalog').json()
        assert catalog['unavailable_tools'][CASE]==['evolution','expedition','heat']
        assert catalog['unavailable_tools']['bay-bengal-2024-01']==[]
        assert catalog['unavailable_tools']['arabian-sea-2024-01']==[]
        assert 'evolution' in catalog['unavailable_tools']['pacific-godas-2015-son']

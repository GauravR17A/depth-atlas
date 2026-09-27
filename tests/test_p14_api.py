"""Phase 14 boundary, reproducibility and export checks with the real packs."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from science.evolution_contracts import EvolutionQuery
from science.blackout_contracts import BlackoutQuery
from science.investigations import fingerprint

ROOT = Path(__file__).resolve().parents[1]
BAY = 'bay-bengal-2024-01'
ARABIAN = 'arabian-sea-2024-01'


@pytest.fixture(scope='module')
def client():
    return TestClient(create_app())


def run(client, mode, case=BAY, **changes):
    query = (EvolutionQuery() if mode == 'evolution' else BlackoutQuery()).model_dump(mode='json')
    query.update(changes)
    response = client.post(f'/api/cases/{case}/{mode}/run', json=query)
    assert response.status_code == 200, response.text
    return response.json()


def capture(client, mode, result, **extra):
    recipe = dict(mode=mode, case_id=result['case_id'], query=result['query'])
    if mode == 'evolution':
        recipe['selected_node'] = None
    response = client.post('/api/investigations/capture', json=dict(
        title='P14 original evidence', recipe=recipe,
        expected_model_sha256=result['manifest_sha256'],
        expected_observation_library_sha256=result['observation_library_sha256'], **extra))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('case', [BAY, ARABIAN])
@pytest.mark.parametrize('mode', ['evolution', 'blackout'])
def test_real_result_capture_replay_and_numerical_archive(client, mode, case):
    result = run(client, mode, case)
    saved = capture(client, mode, result)
    assert saved['results'][0]['output'] == result
    assert saved['replay']['sources']['methods'][mode] == result['method_version']
    replay = client.post('/api/investigations/replay', json=saved['replay'])
    assert replay.status_code == 200, replay.text
    assert replay.json()['results'] == saved['results']
    response = client.post('/api/investigations/export', json=dict(replay=saved['replay'], format='zip'))
    assert response.status_code == 200, response.text
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert json.loads(archive.read('investigation.json'))['results'] == saved['results']
        tables = [name for name in archive.namelist() if name.endswith('.csv')]
        assert len(tables) >= 2
        for name in tables:
            rows = list(csv.reader(io.StringIO(archive.read(name).decode())))
            assert rows and len(rows[0]) > 1
            assert all(len(row) == len(rows[0]) for row in rows[1:])
        html = archive.read('report.html').decode()
        assert '<script' not in html.lower()
        assert result['method_version'] in html


def test_blackout_original_and_modified_are_separately_reproducible(client):
    original = run(client, 'blackout')
    eligible = next(p['profile']['id'] for p in original['baseline']['profiles'] if p['matched_count'])
    modified = run(client, 'blackout', excluded_profile_ids=[eligible])
    a, b = capture(client, 'blackout', original), capture(client, 'blackout', modified)
    assert a['result_sha256'] != b['result_sha256']
    assert a['replay']['sources'] == b['replay']['sources']
    assert modified['baseline'] == original['baseline']
    assert modified['modified']['matched_samples'] < original['baseline']['matched_samples']
    assert modified['model_unchanged'] and modified['source_qc_unchanged']
    for saved in [b, a, b, a]:
        response = client.post('/api/investigations/replay', json=saved['replay'])
        assert response.status_code == 200, response.text
        assert response.json()['result_sha256'] == saved['result_sha256']


@pytest.mark.parametrize('mode', ['evolution', 'blackout'])
def test_stale_observation_library_cannot_be_saved(client, mode):
    result = run(client, mode)
    recipe = dict(mode=mode, case_id=BAY, query=result['query'])
    response = client.post('/api/investigations/capture', json=dict(
        title='Stale observation library', recipe=recipe, expected_observation_library_sha256='0' * 64))
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'source_mismatch'


@pytest.mark.parametrize('mode', ['evolution', 'blackout'])
def test_tampered_recipe_results_and_method_rejected(client, mode):
    saved = capture(client, mode, run(client, mode))
    for alteration in ['recipe', 'result', 'method']:
        request = deepcopy(saved['replay'])
        if alteration == 'recipe':
            if mode == 'evolution':
                request['recipe']['query']['threshold'] += 1
            else:
                request['recipe']['query']['settings']['time_index'] = 3
        elif alteration == 'result':
            request['expected_result_sha256'] = '0' * 64
        else:
            request['sources']['methods'][mode] = 'unavailable-method'
            request['expected_recipe_sha256'] = fingerprint(dict(recipe=request['recipe'], sources=request['sources']))
        response = client.post('/api/investigations/replay', json=request)
        assert response.status_code == 422
        assert response.json()['error']['code'] == {'recipe': 'recipe_mismatch', 'result': 'result_mismatch', 'method': 'method_mismatch'}[alteration]


def test_evolution_selected_node_must_be_in_applied_result(client):
    result = run(client, 'evolution')
    request = dict(title='Unknown node', recipe=dict(mode='evolution', case_id=BAY, query=result['query'], selected_node='t0:r999999'))
    response = client.post('/api/investigations/capture', json=request)
    assert response.status_code == 422


@pytest.mark.parametrize('mode', ['evolution', 'blackout'])
def test_unknown_case_is_explained(client, mode):
    query = (EvolutionQuery() if mode == 'evolution' else BlackoutQuery()).model_dump(mode='json')
    response = client.post('/api/cases/not-a-case/' + mode + '/run', json=query)
    assert response.status_code in (404, 422)
    assert response.json()['error']['message']


def test_catalog_supplies_real_choices_and_no_secrets(client):
    response = client.get('/api/cases/' + BAY + '/blackout/catalog')
    assert response.status_code == 200, response.text
    assert BAY in response.text
    assert 'C:\\Users' not in response.text and 'api_key' not in response.text


def test_monthly_blackout_save_and_export_keep_original_multitime_source(client):
    case = 'pacific-godas-2015-son'
    result = run(client, 'blackout', case)
    assert result['baseline']['matched_samples'] == 0
    assert result['baseline']['exclusion_counts']['incompatible_variable'] > 0
    saved = capture(client, 'blackout', result)
    manifest = json.loads((ROOT / 'casepacks' / case / 'manifest.json').read_text(encoding='utf-8'))
    original_files = manifest['sources'][0]['files']
    assert original_files and all(record['timestamps'] for record in original_files)
    assert saved['references'][0]['files'] == original_files
    response = client.post('/api/investigations/export', json=dict(replay=saved['replay'], format='zip'))
    assert response.status_code == 200, response.text
    with ZipFile(io.BytesIO(response.content)) as archive:
        sources = json.loads(archive.read('SOURCES.json'))
        assert sources[0]['files'] == original_files
        assert all(record['sha256'] and record['source_url'] for record in sources[0]['files'])

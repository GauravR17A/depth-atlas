"""Publication lifecycle against real, unchanged historical model packs."""
import json
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from science.publication import publish, selected_root, inventory
from api.app import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def candidate(tmp_path):
    candidate = tmp_path / 'candidate'; candidate.mkdir()
    shutil.copytree(ROOT/'casepacks/bay-bengal-2024-03', candidate/'bay-bengal-2024-03')
    return candidate


def test_new_publication_pinned_readers_failure_and_restart(candidate, tmp_path, monkeypatch):
    destination = tmp_path/'store'
    first = publish(candidate, destination)
    monkeypatch.setenv('OCEAN_PUBLICATION_ROOT', str(destination))
    running = TestClient(create_app(web_dist=tmp_path/'no-web'))
    old = running.get('/api/cases/bay-bengal-2024-03').json()
    shutil.copytree(ROOT/'casepacks/pacific-godas-2013-son', candidate/'pacific-godas-2013-son')
    second = publish(candidate, destination)
    assert first['publication_id'] != second['publication_id']
    status = running.get('/api/publication').json()
    assert status['serving']['publication_id'] == first['publication_id']
    assert status['refresh']['restart_required'] is True
    assert running.get('/api/cases/pacific-godas-2013-son').status_code == 404
    restarted = TestClient(create_app(web_dist=tmp_path/'no-web'))
    assert restarted.get('/api/cases/pacific-godas-2013-son').status_code == 200
    assert restarted.get('/api/cases/bay-bengal-2024-03').json() == old
    pointer = (destination/'active.json').read_bytes()
    (candidate/'bay-bengal-2024-03/analytical/temperature-0.bin.gz').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='checksum'): publish(candidate,destination)
    assert (destination/'active.json').read_bytes() == pointer
    assert restarted.get('/api/publication').json()['refresh']['state'] == 'failed'
    assert restarted.get('/api/cases/bay-bengal-2024-03').json() == old
    assert len(list((destination/'releases').iterdir())) == 2


@pytest.mark.parametrize('failure',['cancel','timeout','lock','quota'])
def test_failed_work_keeps_previous_publication(candidate,tmp_path,monkeypatch,failure):
    destination=tmp_path/'store';publish(candidate,destination)
    pointer=(destination/'active.json').read_bytes()
    if failure=='lock': (destination/'refresh.lock').write_text('other job')
    if failure=='quota': monkeypatch.setattr('science.publication.MAX_STORE_BYTES',1)
    with pytest.raises((ValueError,TimeoutError,InterruptedError,FileExistsError)):
        publish(candidate,destination,timeout=-1 if failure=='timeout' else 120,cancel=lambda:failure=='cancel')
    assert (destination/'active.json').read_bytes()==pointer
    root,info=selected_root(destination)
    assert info['cases'][0]['time_start']=='2024-03-28T00:00:00Z'
    assert root.is_dir()
    if failure=='lock': assert (destination/'refresh.lock').read_text()=='other job'


def test_reject_traversal_version_tampering_and_bad_selected_bytes(candidate,tmp_path):
    destination=tmp_path/'store';publish(candidate,destination)
    original=(destination/'active.json').read_text();pointer=json.loads(original)
    for change in ({'release':'../escape'},{'app_version':'wrong'},{'publication_id':'0'*64}):
        (destination/'active.json').write_text(json.dumps({**pointer,**change}))
        with pytest.raises(ValueError):selected_root(destination)
    (destination/'active.json').write_text(original)
    root,_=selected_root(destination);(root/'bay-bengal-2024-03/source-metadata.json').write_bytes(b'broken')
    with pytest.raises(ValueError):selected_root(destination)


def test_bundled_status_is_bounded_has_dates_and_no_file_paths(monkeypatch,tmp_path):
    monkeypatch.delenv('OCEAN_PUBLICATION_ROOT',raising=False)
    client=TestClient(create_app(web_dist=tmp_path))
    r=client.get('/api/publication');assert r.status_code==200
    body=r.json();assert len(body['serving']['cases'])==6
    assert 'files' not in body['serving'];assert len(r.content)<20000
    assert body['refresh']['state']=='bundled'
    assert r.headers['cache-control']=='no-store'
    assert body['serving']['app_version']==body['app_version']


def test_candidate_mutation_during_copy_cannot_activate(candidate,tmp_path):
    destination=tmp_path/'store';publish(candidate,destination);previous=(destination/'active.json').read_bytes()
    def mutate():
        status=json.loads((destination/'status.json').read_text())
        if status['state']=='staging': (candidate/'bay-bengal-2024-03/source-metadata.json').write_bytes(b'mutated')
        return False
    with pytest.raises(ValueError,match='changed'):publish(candidate,destination,cancel=mutate)
    assert (destination/'active.json').read_bytes()==previous


def test_identity_uses_portable_order_not_filesystem_or_os_path_order(candidate,monkeypatch):
    (candidate/'README.md').write_text('Test-only inventory ordering sentinel.')
    (candidate/'a.json').write_text('{}')
    first=inventory(candidate)
    assert [f['path'] for f in first['files']]==sorted(f['path'] for f in first['files'])
    original=Path.rglob
    monkeypatch.setattr(Path,'rglob',lambda self,pattern:iter(reversed(list(original(self,pattern)))))
    second=inventory(candidate)
    assert first['files']==second['files']
    assert first['publication_id']==second['publication_id']

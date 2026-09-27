"""Verify the deployed release against local checked scientific assets."""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv('OCEAN_TEST_URL', 'https://depth-atlas-seifuku.vercel.app').rstrip('/')
OUT = ROOT / 'docs/evidence/p04-public-http.json'
rows = []
result = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'base': BASE, 'release': '0.4.0', 'rows': rows}


def request(path, status=200, body=None):
    response = requests.request('POST' if body is not None else 'GET', BASE + path, data=body, timeout=(15, 45))
    rows.append({'path': path, 'method': 'POST' if body is not None else 'GET', 'status': response.status_code,
                 'version': response.headers.get('X-Ocean-App-Version'), 'decoded_bytes': len(response.content),
                 'seconds': response.elapsed.total_seconds()})
    assert response.status_code == status, (path, response.status_code, response.text[:250])
    if path.startswith('/api/'):
        assert response.headers.get('X-Ocean-App-Version') == '0.4.0'
    return response


try:
    home = request('/').text
    assert request('/api/health').json()['version'] == '0.4.0'
    request('/api/catalog')
    local = (ROOT / 'casepacks/bay-bengal-2024-01/manifest.json').read_bytes()
    assert request('/api/cases/bay-bengal-2024-01').json() == json.loads(local)
    result['model_manifest_sha256'] = hashlib.sha256(local).hexdigest()
    for path in ['/privacy', '/terms', '/favicon.svg', '/third-party-notices.txt', '/observation-import-guide.txt',
                 '/licenses/GSW.txt', '/licenses/netCDF4.txt', '/licenses/NumPy.txt', '/licenses/cftime.txt']:
        request(path)
    for path in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', home):
        body = request(path).content
        assert len(body) > 100
        rows[-1]['sha256'] = hashlib.sha256(body).hexdigest()
        if path.endswith('.js'):
            assert b'0.4.0' in body and b'Import observations' in body
            for scene in set(re.findall(rb'scene-[A-Za-z0-9_-]+\.js', body)):
                request('/assets/' + scene.decode())
    index = json.loads((ROOT / 'casepacks/instruments/index.json').read_text(encoding='utf8'))
    catalog = request('/api/instruments').json()
    assert catalog['profiles'] == index['profiles'] and catalog['examples'] == index['examples']
    for summary in catalog['profiles']:
        profile = request('/api/instruments/profiles/' + summary['id']).json()
        assert profile == json.loads((ROOT / 'casepacks/instruments' / (summary['id'] + '.json')).read_text(encoding='utf8'))
    imported = []
    for example in catalog['examples']:
        body = request('/api/instruments/examples/' + example['name']).content
        assert hashlib.sha256(body).hexdigest() == example['sha256']
        parsed = request('/api/instruments/import?filename=' + quote(example['name']), body=body).json()
        assert parsed['persistence'] == 'request_only'
        for profile in parsed['profiles']:
            assert profile['source_sha256'] == example['sha256']
            for key, parameter in profile['parameters'].items():
                assert parameter['accepted_count'] == sum(level['readings'][key]['accepted'] for level in profile['levels'])
        imported.append({'name': example['name'], 'profiles': len(parsed['profiles']), 'format': parsed['format']})
    assert request('/api/instruments').json() == catalog
    request('/api/instruments/import?filename=bad.csv', status=422, body=b'a,b\n1,2')
    request('/api/instruments/import?filename=large.csv', status=413, body=b'x' * 2_000_001)
    request('/api/instruments/profiles/no-such-id', status=404)
    fixture = json.loads((ROOT / 'web/e2e/fixtures/phase-03-source.json').read_text())
    for point in [*fixture['points'], fixture['cut_face']]:
        _, _, z = point['indices']; lon, lat, depth = point['coordinates']
        path = f'/api/cases/bay-bengal-2024-01/subset?variable=temperature&time_index=0&depth_index={z}&west={lon}&east={lon}&south={lat}&north={lat}'
        subset = request(path).json()
        assert subset['longitude'] == [lon] and subset['latitude'] == [lat] and subset['depth_m'] == [depth]
        assert abs(subset['values'][0] - point['expected']) < 1e-9
    result.update(status='passed', library_profiles=len(catalog['profiles']), imported=imported, source_probes=3)
except Exception as error:
    result.update(status='failed', error=str(error))
    raise
finally:
    OUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))

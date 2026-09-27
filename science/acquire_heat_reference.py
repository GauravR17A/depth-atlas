"""Acquire a pinned offline reference for P12 checks, never production execution.

The upstream GPL-3.0-or-later code and its licence remain in ignored data/.
Run from the project root: python -m science.acquire_heat_reference
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

COMMIT = 'd7292bf08ade0af213fa760b0d7e4adfe5f52894'
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'data/reference/p12'


def acquire():
    TARGET.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ('marineHeatWaves.py', 'LICENSE.txt'):
        url = f'https://raw.githubusercontent.com/ecjoliver/marineHeatWaves/{COMMIT}/{name}'
        with urlopen(url, timeout=60) as response:
            body = response.read()
        path = TARGET / name
        path.write_bytes(body)
        records.append({'name': name, 'url': url, 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)})
    result = {
        'repository': 'https://github.com/ecjoliver/marineHeatWaves',
        'commit': COMMIT,
        'licence': 'GPL-3.0-or-later',
        'use': 'Independent offline reference checks only; no upstream implementation is used in the deployed service.',
        'execution_compatibility': 'Tests replace the removed NumPy alias np.NaN with np.nan in memory. Original downloaded bytes are unchanged.',
        'files': records,
    }
    gsw_url = 'https://raw.githubusercontent.com/TEOS-10/GSW-Python/v3.6.20/gsw/tests/gsw_cv_v3_0.npz'
    with urlopen(gsw_url, timeout=60) as response:
        gsw_body = response.read()
    expected_sha = '402d9aa4aced457b53402839708a40ebd9f7af2f7c02604a4af4ce57f7daa1ee'
    if hashlib.sha256(gsw_body).hexdigest() != expected_sha:
        raise ValueError('The pinned GSW reference data failed its checksum.')
    (TARGET / 'gsw_cv_v3_0.npz').write_bytes(gsw_body)
    result['gsw_reference'] = {'url': gsw_url, 'sha256': expected_sha, 'bytes': len(gsw_body)}
    (TARGET / 'provenance.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    print(json.dumps(acquire(), indent=2))

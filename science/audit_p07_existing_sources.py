"""Independent P07 regression audit of existing model packs against acquired files.

Numerical expectations use manual decoding of the original packed NetCDF variables
through the P06 independent verifier. No production adapter, store or product
calculator is imported. Both analytical and display binary files are read directly.
"""
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from science.verify_p06_standards import SOURCES, source_fields

ROOT = Path(__file__).resolve().parents[1]


def main():
    acquisition = json.loads((ROOT / 'data/raw/acquisition.json').read_text())
    sources = sorted((f for f in acquisition['files'] if f['archive_kind'] == 'packed_source_subset_reconstructed_as_netcdf'), key=lambda f: f['time'])
    directory = ROOT / 'casepacks/bay-bengal-2024-01'
    manifest = json.loads((directory / 'manifest.json').read_text())
    checks = []
    examined = 0
    for ti, source in enumerate(sources):
        path = ROOT / source['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']
        coordinates, expected = source_fields(path)
        for target, original in [('longitude', 'lon'), ('latitude', 'lat'), ('depth_m', 'depth')]:
            assert np.array_equal(manifest['coordinates'][target], coordinates[original])
        assert manifest['coordinates']['times'][ti] == source['time']
        for variable in SOURCES:
            for representation, dtype in [('analytical', '<f8'), ('display', '<f4')]:
                relative = f'{representation}/{variable}-{ti}.bin.gz'
                record = next(f for f in manifest['files'] if f['path'] == relative)
                body = (directory / relative).read_bytes()
                assert hashlib.sha256(body).hexdigest() == record['sha256']
                actual = np.frombuffer(gzip.decompress(body), dtype=dtype).reshape(record['shape'])
                wanted = expected[variable][0]
                if representation == 'display':
                    d = manifest['representations']['display']
                    wanted = wanted[:, d['latitude_source_indices'], :][:, :, d['longitude_source_indices']].astype(np.float32)
                assert np.array_equal(actual, wanted, equal_nan=True), relative
                examined += actual.size
                checks.append(dict(file=relative, passed=True, values=actual.size, missing=int(np.isnan(actual).sum()), max_absolute_error=0.0))
    result = dict(checked_utc=datetime.now(timezone.utc).isoformat(), method='Manual packed-source decoding, direct binary reads and exact mask/value equality. Display expectations explicitly select native coordinates then cast to float32.', snapshots=len(sources), array_checks=len(checks), scalar_positions_including_missing=examined, passed=True, checks=checks)
    (ROOT / 'docs/evidence/p07-audit-existing-source-arrays.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'checks'}))


if __name__ == '__main__':
    main()

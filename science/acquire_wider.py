"""Pin native NOAA GODAS global monthly subsets for bounded P15 requests.

Acquisition is a maintainer command, never triggered by public arbitrary URLs.
Source float32 values, original coordinates and monthly support are retained.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import netCDF4
import numpy as np
from pydap.client import open_url

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/wider'
OUT = ROOT / 'casepacks/wider/godas-2022'


def clean(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, dict): return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [clean(x) for x in value]
    return value


def acquire():
    RAW.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
    record_path = RAW / 'godas-acquisition.json'
    journal = json.loads(record_path.read_text()) if record_path.exists() else {'retrieved_at': datetime.now(timezone.utc).isoformat(), 'files': []}
    axes = None
    for variable in ('pottmp', 'salt'):
        metadata_path=RAW / f'{variable}-metadata.json'
        if not metadata_path.exists():
            url=f'https://psl.noaa.gov/thredds/dodsC/Datasets/godas/{variable}.2022.nc'
            ds=open_url(url,protocol='dap2',timeout=60)
            metadata={'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'global':clean(ds.attributes),'variable':clean(ds[variable].attributes),'axes':{k:{'attributes':clean(ds[k].attributes),'values':clean(np.asarray(ds[k][:].data).ravel())} for k in ['time','level','lat','lon']}}
            metadata_path.write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        metadata = json.loads(metadata_path.read_text())
        assert metadata['variable']['units']==('K' if variable=='pottmp' else 'kg/kg'), 'Review changed source units'
        coords = metadata['axes']
        indices = [i for i, z in enumerate(coords['level']['values']) if z <= 500]
        assert indices == list(range(28)), 'Unexpected GODAS depth support'
        shape = (28, len(coords['lat']['values']), len(coords['lon']['values']))
        assert shape == (28, 418, 360), 'Review changed source grid'
        current_axes = {k: coords[k]['values'] for k in ('lat', 'lon')}
        current_axes['depth'] = coords['level']['values'][:28]
        if axes is not None: assert axes == current_axes, 'Variables must share native coordinates'
        axes = current_axes
        for index in (8, 9):
            name = f'{variable}-{index}.f32.gz'; target = OUT / name
            previous = next((x for x in journal['files'] if x['path'] == name), None)
            if previous and target.is_file():
                assert hashlib.sha256(target.read_bytes()).hexdigest() == previous['sha256'], 'Source changed'
                print('Verified cached', name, flush=True); continue
            ds = open_url(metadata['url'], protocol='dap2', timeout=60)
            # Small depth slabs avoid large provider responses being truncated.
            slabs = []
            for z in range(0, 28, 4):
                part = RAW / f'{variable}-{index}-{z}.npy'
                if part.is_file():
                    slab = np.load(part, allow_pickle=False)
                else:
                    slab = np.asarray(ds[variable][index:index+1, z:z+4, :, :].data, dtype='<f4')
                    assert slab.shape == (1, 4, 418, 360)
                    np.save(part, slab, allow_pickle=False)
                slabs.append(slab)
                print('Source slab', variable, index, z, flush=True)
            values = np.concatenate(slabs, axis=1)
            assert values.shape == (1, *shape), values.shape
            raw = values.tobytes(order='C')
            packed = gzip.compress(raw, compresslevel=6, mtime=0)
            target.write_bytes(packed)
            date = netCDF4.num2date(coords['time']['values'][index], coords['time']['attributes']['units'], calendar='standard')
            journal['files'].append({'path': name, 'sha256': hashlib.sha256(packed).hexdigest(), 'raw_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(packed), 'shape': list(shape), 'source_url': metadata['url'], 'source_variable': variable, 'source_time_index': index, 'source_level_indices': [0,27], 'time': date.strftime('%Y-%m-%dT%H:%M:%SZ')})
            record_path.write_text(json.dumps(journal, indent=2), encoding='utf-8')
            print('Acquired', name, len(packed), flush=True)
    (OUT / 'source.json').write_text(json.dumps({'axes': axes, 'files': journal['files'], 'retrieved_at': journal['retrieved_at'], 'metadata': {v: json.loads((RAW / f'{v}-metadata.json').read_text()) for v in ('pottmp','salt')}}, indent=2), encoding='utf-8')


if __name__ == '__main__': acquire()

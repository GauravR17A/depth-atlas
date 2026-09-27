"""Acquire bounded original NOAA GODAS SON fields and original Pacific Argo files."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import netCDF4
import numpy as np
import requests
from pydap.client import open_url

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/climate'
BASE = 'https://psl.noaa.gov/thredds/dodsC/Datasets/godas'
YEARS = [*range(1991, 2021), 2022]
EVENT_YEARS = [2013, 2015, 2022]
MONTHS = [9, 10, 11]


def fingerprint(path: Path) -> dict:
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def clean(value):
    if isinstance(value, np.ndarray): return [clean(x) for x in value.tolist()]
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, dict): return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [clean(x) for x in value]
    return value


def acquire(years=YEARS, profiles=True):
    RAW.mkdir(parents=True, exist_ok=True)
    journal_path = RAW / 'field-acquisition.json'
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else {
        'schema_version': '1', 'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'bounds': [40, -5, 280, 5], 'depth_limit_m': 500, 'months': MONTHS,
        'baseline_years': [1991, 2020], 'files': [], 'attempts': []}

    def save():
        journal_path.write_text(json.dumps(journal, indent=2), encoding='utf8')

    def cached(path):
        record = next((x for x in journal['files'] if x['path'] == path.relative_to(ROOT).as_posix()), None)
        if record and path.exists():
            if fingerprint(path)['sha256'] != record['sha256']:
                raise ValueError('Cached source fingerprint changed; do not replace silently.')
            print('Verified cached', path.name, flush=True)
            return True
        return False

    for year in years:
        path = RAW / 'godas' / f'pottmp-son-{year}.nc'
        path.parent.mkdir(exist_ok=True)
        if cached(path): continue
        url = f'{BASE}/pottmp.{year}.nc'
        for attempt in range(2):
            started = time.monotonic()
            attempt_record = {'year': year, 'attempt': attempt + 1, 'url': url,
                              'started_at': datetime.now(timezone.utc).isoformat()}
            try:
                ds = open_url(url, protocol='dap2', timeout=45)
                coords = {k: np.asarray(ds[k][:].data) for k in ('time', 'level', 'lat', 'lon')}
                dates = netCDF4.num2date(coords['time'], ds['time'].attributes['units'], calendar='standard')
                ids = {'time': np.array([i for i, d in enumerate(dates) if d.year == year and d.month in MONTHS]),
                       'level': np.flatnonzero(coords['level'] <= 500),
                       'lat': np.flatnonzero((coords['lat'] >= -5) & (coords['lat'] <= 5)),
                       'lon': np.flatnonzero((coords['lon'] >= 40) & (coords['lon'] <= 280))}
                if [dates[i].month for i in ids['time']] != MONTHS:
                    raise ValueError('All three exact SON months are required.')
                for values in ids.values():
                    if not len(values) or not np.all(np.diff(values) == 1):
                        raise ValueError('Acquisition must use contiguous original source indices.')
                slices = tuple(slice(int(ids[k][0]), int(ids[k][-1]) + 1) for k in ('time','level','lat','lon'))
                values = np.asarray(ds['pottmp'][slices].data, dtype=np.float32)
                expected = tuple(len(ids[k]) for k in ('time','level','lat','lon'))
                if values.shape != expected or expected != (3, 28, 30, 240):
                    raise ValueError(f'Unexpected native shape: {values.shape}')
                temp = path.with_suffix('.partial.nc')
                with netCDF4.Dataset(temp, 'w', format='NETCDF4') as out:
                    out.setncatts(clean(ds.attributes.get('NC_GLOBAL', {})))
                    out.setncattr('ocean_navigator_acquisition', 'Native Float32 OPeNDAP subset, reconstructed as NetCDF without interpolation; this is not the original entire archive file.')
                    out.setncattr('source_url', url)
                    for key in ('time','level','lat','lon'):
                        out.createDimension(key, len(ids[key]))
                        v = out.createVariable(key, 'f8' if key == 'time' else 'f4', (key,))
                        attrs = {k: v for k, v in ds[key].attributes.items() if k not in {'_ChunkSizes','_FillValue'}}
                        v.setncatts(clean(attrs)); v[:] = coords[key][ids[key]]
                    v = out.createVariable('pottmp','f4',('time','level','lat','lon'),zlib=True,complevel=4)
                    v.setncatts(clean({k: v for k, v in ds['pottmp'].attributes.items() if k not in {'_ChunkSizes','_FillValue'}}))
                    v.set_auto_maskandscale(False); v[:] = values
                temp.replace(path)
                record = fingerprint(path) | {'archive_kind':'source_float32_subset_reconstructed_as_netcdf',
                         'source_url':url,'year':year,'shape':list(values.shape),
                         'source_indices':{k:[int(v[0]),int(v[-1])] for k,v in ids.items()},
                         'timestamps':[dates[i].strftime('%Y-%m-%dT%H:%M:%SZ') for i in ids['time']],
                         'source_time_units':ds['time'].attributes['units'],
                         'temporal_support':'Calendar-month mean; timestamp is first day of averaging period.'}
                journal['files'].append(record)
                attempt_record.update(status='success',seconds=time.monotonic()-started,bytes=path.stat().st_size)
                journal['attempts'].append(attempt_record);save()
                print('Saved',year,values.shape,path.stat().st_size,round(time.monotonic()-started,2),flush=True)
                break
            except Exception as exc:
                attempt_record.update(status='failed',seconds=time.monotonic()-started,error=f'{type(exc).__name__}: {exc}')
                journal['attempts'].append(attempt_record);save()
                print('Failed',year,attempt+1,str(exc),flush=True)
                if attempt == 1: raise

    if profiles:
        index = ROOT / 'data/raw/argo/ar_index_global_prof.txt.gz'
        if not index.is_file(): raise ValueError('The original checked GDAC index is required for deterministic selection.')
        chosen = {}
        with gzip.open(index,'rt') as stream:
            rows = csv.DictReader(line for line in stream if not line.startswith('#'))
            for row in rows:
                date = row['date']
                if len(date) != 14: continue
                year, month = int(date[:4]), int(date[4:6])
                if year not in EVENT_YEARS or month not in MONTHS: continue
                try: lat, lon = float(row['latitude']), float(row['longitude'])
                except ValueError: continue
                if not (-5 <= lat <= 5 and -160 <= lon <= -120): continue
                # Select by geography and date before examining any measured values or QC.
                score = (abs(lat) + abs(lon + 140), abs(int(date[6:8])-15), row['file'])
                key = (year,month)
                if key not in chosen or score < chosen[key][0]: chosen[key] = (score,row)
        if len(chosen) != 9: raise ValueError('One original indexed Argo profile is required per event month.')
        journal['profile_selection'] = {'index':fingerprint(index),
            'rule':'For each event month, among profiles within 5S–5N,160W–120W, minimize abs(latitude)+abs(longitude+140), then abs(day-15), then source path. Selection precedes any QC or value inspection.',
            'rows':[row for _,row in sorted(chosen.values(),key=lambda x:x[1]['date'])]}
        save()
        for (year,month),(_,row) in sorted(chosen.items()):
            path = RAW / 'argo' / row['file'].rsplit('/',1)[1]
            path.parent.mkdir(exist_ok=True)
            if cached(path): continue
            url = 'https://data-argo.ifremer.fr/dac/' + row['file']
            started = time.monotonic()
            r = requests.get(url,timeout=45);r.raise_for_status()
            if len(r.content)>4_000_000: raise ValueError('Original profile exceeds 4MB limit.')
            path.write_bytes(r.content)
            journal['files'].append(fingerprint(path)|{'archive_kind':'original_gdac_file','source_url':url,
                 'event_year':year,'event_month':month,'index_row':row})
            save();print('Saved Argo',year,month,path.name,len(r.content),round(time.monotonic()-started,2),flush=True)
    print('Acquisition complete',journal_path,flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--years',type=int,nargs='+',default=YEARS)
    parser.add_argument('--no-profiles',action='store_true')
    args=parser.parse_args();acquire(args.years,not args.no_profiles)

"""Independent original-NetCDF audit of the six added profile records."""
from pathlib import Path
import json
import hashlib
import netCDF4
import numpy as np
import gsw
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
def number(v):return None if np.ma.is_masked(v) or not np.isfinite(float(v)) else float(v)
def flag(v):return '' if np.ma.is_masked(v) else bytes(v).decode().strip()
def main():
    checks=[]
    for path in sorted((ROOT/'casepacks/instruments-arabian-sea').glob('argo*.json')):
        profile=json.loads(path.read_text(encoding='utf8'));source=ROOT/'data/raw/arabian-sea/argo'/profile['source_file'];assert hashlib.sha256(source.read_bytes()).hexdigest()==profile['source_sha256']
        i=profile['metadata']['source_profile_index']
        with netCDF4.Dataset(source) as ds:
            lat=number(ds['LATITUDE'][i]);lon=number(ds['LONGITUDE'][i]);assert (lat,lon)==(profile['latitude'],profile['longitude'])
            timestamp=netCDF4.num2date(ds['JULD'][i],'days since 1950-01-01 00:00:00',only_use_cftime_datetimes=False).replace(tzinfo=timezone.utc)
            assert abs((timestamp-datetime.fromisoformat(profile['time'].replace('Z','+00:00'))).total_seconds())<=.5
            assert profile['metadata']['source_juld']==float(ds['JULD'][i])
            pres=profile['metadata']['pressure_field'];modes=profile['metadata']['parameter_modes'];accepted={key:0 for key in profile['parameters']}
            for level in profile['levels']:
                j=level['index'];p=number(ds[pres][i,j]);assert p==level['pressure_dbar']
                z=None if p is None else max(0.,float(-gsw.z_from_p(p,lat)))
                assert z==level['depth_m']
                for key,src in [('temperature','TEMP'),('salinity','PSAL')]:
                    reading=level['readings'][key];chosen=src+'_ADJUSTED' if modes[src] in ('A','D') else src
                    assert reading['value']==number(ds[chosen][i,j]);assert reading['qc']==flag(ds[chosen+'_QC'][i,j])
                    for field,nc in [('raw',src),('adjusted',src+'_ADJUSTED'),('adjusted_error',src+'_ADJUSTED_ERROR')]:
                        assert reading[field]==number(ds[nc][i,j])
                    assert reading['raw_qc']==flag(ds[src+'_QC'][i,j]);assert reading['adjusted_qc']==flag(ds[src+'_ADJUSTED_QC'][i,j])
                    usable=reading['value'] is not None and reading['qc'] in ('1','2') and level['coordinate_eligible']
                    assert reading['accepted']==usable
                    accepted[key]+=usable
            assert accepted=={k:v['accepted_count'] for k,v in profile['parameters'].items()}
        checks.append(dict(profile=profile['id'],source=source.name,source_sha256=profile['source_sha256'],source_profile_index=i,levels=len(profile['levels']),accepted=accepted,passed=True))
    output={'date':'2026-09-22','method':'Original GDAC values/QC/modes and pressure-to-depth checked without importing application adapters. Uses the declared GSW routine, so it does not independently validate GSW physics.','profiles':checks}
    (ROOT/'docs/evidence/p09-observation-source-check.json').write_text(json.dumps(output,indent=2)+'\n');print(f"{len(checks)} source profiles, {sum(c['levels'] for c in checks)} levels checked.")
if __name__=='__main__':main()

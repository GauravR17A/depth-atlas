"""Deterministic CF exchange file from the immutable native case, not the display grid."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import netCDF4
import numpy as np

from api.case_store import CaseStore, CASE_ID, CASE_IDS
from science.case_recipes import RECIPES
from science.products import PRODUCTS

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'casepacks' / 'standards'


def prepare(destination: Path = DEST, case_id=CASE_ID):
    store = CaseStore(ROOT / 'casepacks')
    manifest, digest = store.require(case_id)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / (case_id+'.nc')
    c = manifest.coordinates
    shape = manifest.representations['analytical']['shape']
    with netCDF4.Dataset(path, 'w', format='NETCDF4_CLASSIC') as ds:
        ds.setncatts(dict(Conventions='CF-1.10', title=RECIPES[case_id].get('title', 'Historical '+RECIPES[case_id]['name']+' HYCOM subset, 7-10 January 2024'),
            source='HYCOM GOFS 3.1 + NCODA, GLBy0.08/expt_93.0',
            references=manifest.sources[0].source_url, license=manifest.sources[0].licence,
            history=('2026-09-27' if 'times' in RECIPES[case_id] else '2026-09-22')+': p06-cf-exchange-v1; native coordinates and float64 decoded fields from checked case pack.',
            source_manifest_sha256=digest,
            comment='Historical model analysis. Original metadata remains in the case manifest. No spatial/temporal interpolation. Missing is not zero.'))
        axes = [('time',netCDF4.date2num([datetime.fromisoformat(t.replace('Z','+00:00')) for t in c.times], 'hours since 2024-01-07 00:00:00', calendar='proleptic_gregorian'),dict(standard_name='time',axis='T',units='hours since 2024-01-07 00:00:00',calendar='proleptic_gregorian')),
                ('depth',c.depth_m,dict(standard_name='depth',axis='Z',units='m',positive='down')),
                ('latitude',c.latitude,dict(standard_name='latitude',axis='Y',units='degrees_north')),
                ('longitude',c.longitude,dict(standard_name='longitude',axis='X',units='degrees_east'))]
        for name, values, attrs in axes:
            ds.createDimension(name,len(values))
            v=ds.createVariable(name,'f8',(name,),fill_value=False);v.setncatts(attrs);v[:]=values
        for spec in manifest.variables:
            v=ds.createVariable(spec.id,'f8',tuple(a[0] for a in axes),fill_value=np.float64(9.969209968386869e36),zlib=True,complevel=4,chunksizes=(1,1,min(76,len(c.latitude)),min(63,len(c.longitude))))
            # The project explicitly interprets this HYCOM psu field as practical salinity.
            # CF's dimensionless practical-salinity unit is 1; numbers are unchanged.
            standard='sea_water_practical_salinity' if spec.id=='salinity' else spec.standard_name
            units='1' if spec.id=='salinity' else 'degree_Celsius' if spec.id=='temperature' else 'm s-1'
            v.setncatts(dict(standard_name=standard,units=units,long_name=spec.label,
                source_variable=spec.source_name,source_units=spec.source_units,source_standard_name=spec.standard_name,comment=spec.definition))
            for ti in range(len(c.times)):
                values=np.asarray(store._read_array(case_id,'analytical',spec.id,ti)).reshape(shape)
                v[ti]=np.ma.masked_invalid(values)
        for spec in PRODUCTS.catalog():
            v=ds.createVariable(spec['id'],'f8',tuple(a[0] for a in axes),fill_value=np.float64(9.969209968386869e36),zlib=True,complevel=4,chunksizes=(1,1,min(76,len(c.latitude)),min(63,len(c.longitude))))
            # No CF standard_name is assigned to the horizontal-only approximation.
            v.setncatts(dict(long_name=spec['label'],units='m2 s-2',comment=spec['definition']+' '+' '.join(spec['limitations']),method_id=spec['method_id']))
            for ti in range(len(c.times)):
                v[ti]=np.ma.masked_invalid(np.asarray(store._read_array(case_id,'analytical',spec['id'],ti)).reshape(shape))
    record=dict(schema_version='1',file=path.name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_manifest_sha256=digest,conventions='CF-1.10',method_id='p06-cf-exchange-v1',shape=[len(c.times),*shape],variables=[v.id for v in manifest.variables]+[p['id'] for p in PRODUCTS.catalog()])
    (destination/('manifest.json' if case_id==CASE_ID else case_id+'.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record,indent=2))
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--case",choices=CASE_IDS,default=CASE_ID);prepare(case_id=parser.parse_args().case)

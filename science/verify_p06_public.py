"""Public release and scientific download verification, with no implicit retries."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import numpy as np
import requests

ROOT=Path(__file__).resolve().parents[1]


def verify(base,output):
    checks=[];calls=[];session=requests.Session()
    def get(path):
        start=time.perf_counter();r=session.get(base+path,timeout=(15,60));calls.append(dict(path=path,status=r.status_code,seconds=round(time.perf_counter()-start,3),bytes=len(r.content),version=r.headers.get('X-Ocean-App-Version')));return r
    def check(name,value,**extra):checks.append(dict(check=name,passed=bool(value),**extra))
    release=json.loads((ROOT/'api/release.json').read_text())['version']
    for path in ['/','/data-access','/privacy','/terms','/favicon.svg','/third-party-notices.txt']:
        r=get(path);check('page '+path,r.status_code==200)
        if path in ['/','/data-access','/privacy','/terms']:
            for asset in sorted(set(re.findall(r'(?:src|href)="(/assets/[^\"]+)"',r.text))):
                a=get(asset);check('asset '+asset,a.status_code==200 and len(a.content)>100)
    r=get('/api/health');check('release',r.status_code==200 and r.json()['version']==release and r.headers.get('X-Ocean-App-Version')==release)
    r=get('/api/data-access');access=r.json();check('service boundary',r.status_code==200 and access['standards']['public_url'] is None and len(access['adapters'])==2)
    r=get('/api/products');check('derived product metadata',r.status_code==200 and r.json()['products'][0]['id']=='horizontal_kinetic_energy' and r.json()['products'][0]['kind']=='derived')
    expected=json.loads((ROOT/'casepacks/standards/manifest.json').read_text())
    r=get('/data/manifest.json');check('exchange manifest',r.status_code==200 and r.json()==expected)
    r=get('/data/'+expected['file']);check('complete native NetCDF download',r.status_code==200 and len(r.content)==expected['bytes'] and hashlib.sha256(r.content).hexdigest()==expected['sha256'],actual_bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest())
    manifest=get('/api/cases/bay-bengal-2024-01').json()
    refs=json.loads((ROOT/'tests/fixtures/p06-source-samples.json').read_text())['rows']
    for row in refs:
        params=dict(variable='horizontal_kinetic_energy',time_index=row['time_index'],depth_index=row['depth_index'],west=row['longitude'],east=row['longitude'],south=row['latitude'],north=row['latitude'])
        query=requests.Request('GET',base+'/api/cases/bay-bengal-2024-01/subset',params=params).prepare().url
        r=get(query[len(base):]);b=r.json()
        valid=r.status_code==200 and b['kind']=='derived' and b['units']=='m²/s²' and b['manifest_sha256']==expected['source_manifest_sha256']
        if valid:valid=b['values']==[None] if row['expected'] is None else abs(b['values'][0]-row['expected'])<1e-12
        check(f"native energy {row['time_index']}/{row['depth_index']}/{row['x']}/{row['y']}",valid)
    for ti in [0,6]:
        r=get(f'/api/cases/bay-bengal-2024-01/subset?variable=horizontal_kinetic_energy&time_index={ti}&representation=display&operation=volume')
        b=r.json();check('display grid '+str(ti),r.status_code==200 and b['shape']==[40,39,32] and b['kind']=='derived' and b['latitude']==manifest['display_coordinates']['latitude'] and b['longitude']==manifest['display_coordinates']['longitude'])
    for path,status in [('/api/cases/bay-bengal-2024-01/subset?variable=unregistered',422),('/api/cases/bay-bengal-2024-01/subset?variable=horizontal_kinetic_energy&time_index=7',422),('/data/unknown.nc',404),('/api/products/unknown',404)]:
        r=get(path);check('unsupported '+path,r.status_code==status)
    report=dict(base=base,release=release,passed=all(c['passed'] for c in checks),checks=checks,requests=calls,method='Anonymous HTTP requests without retry. Native values use original-file independent fixtures; downloaded NetCDF checked in full by SHA-256.')
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],checks=len(checks),requests=len(calls),failures=[c for c in checks if not c['passed']]),indent=2))
    return report['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='https://depth-atlas-seifuku.vercel.app');parser.add_argument('--output',type=Path,default=ROOT/'docs/evidence/p06-public-http.json');args=parser.parse_args()
    raise SystemExit(0 if verify(args.base.rstrip('/'),args.output) else 1)

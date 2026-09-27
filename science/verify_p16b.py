"""Source-reference generation and bounded release checks for the March case.

Reference mode decodes packed NetCDF independently of the application adapter.
HTTP mode also works against a clean runtime-only installation.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
from time import perf_counter
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
CASE = 'bay-bengal-2024-03'
FIXTURE = ROOT / 'tests/fixtures/p16b-source-reference.json'


def reference():
    import netCDF4
    import numpy as np
    from science.verify_p06_standards import source_fields
    journal = json.loads((ROOT/'data/raw/bay-march/acquisition.json').read_text())
    records = sorted(journal['files'], key=lambda r:r['time'])
    result = {'case_id': CASE, 'source_files': [], 'rows': []}
    for ti, item in enumerate(records):
        path = ROOT/item['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
        axes, fields = source_fields(path)
        with netCDF4.Dataset(path) as ds:
            time = netCDF4.num2date(ds['time'][:], ds['time'].units, ds['time'].calendar)[0].strftime('%Y-%m-%dT%H:%M:%SZ')
        assert time == item['time']
        result['source_files'].append(item)
        for variable, field in fields.items():
            a = field[0].astype('<f8')
            # A fixed canonical missing-byte pattern makes whole-array hashes portable.
            a[np.isnan(a)] = np.nan
            samples = []
            for z,y,x in [(0,0,0),(19,17,3),(26,13,6),(39,25,12)]:
                samples.append({'indices':[z,y,x], 'depth_m':float(axes['depth'][z]),
                    'latitude':float(axes['lat'][y]), 'longitude':float(axes['lon'][x]),
                    'value':float(a[z,y,x]) if np.isfinite(a[z,y,x]) else None})
            result['rows'].append({'time_index':ti,'time':time,'variable':variable,
                'shape':list(a.shape),'sha256':hashlib.sha256(a.tobytes()).hexdigest(),
                'missing':int(np.isnan(a).sum()), 'samples':samples})
    result['latitude'] = axes['lat'].tolist()
    result['longitude'] = axes['lon'].tolist()
    result['depth_m'] = axes['depth'].tolist()
    FIXTURE.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(f'Wrote {len(result["rows"])} independently decoded source arrays.')


def verify(url, report):
    reference = json.loads(FIXTURE.read_text())
    measurements=[];checks=[]
    def request(path, data=None):
        body=None if data is None else json.dumps(data).encode()
        r=Request(url.rstrip('/')+path,body,headers={'Accept-Encoding':'gzip','Content-Type':'application/json'})
        start=perf_counter()
        with urlopen(r,timeout=55) as response:
            wire=response.read();content=gzip.decompress(wire) if response.headers.get('Content-Encoding')=='gzip' else wire
            measurements.append({'path':path,'seconds':round(perf_counter()-start,4),'wire_bytes':len(wire),'decoded_bytes':len(content),'status':response.status})
            return content
    def get(path,data=None):return json.loads(request(path,data))
    def check(name,condition):
        checks.append({'check':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    health=get('/api/health');check('six cases available',health['case_count']==6)
    m=get('/api/cases/'+CASE);check('historical dates',m['coordinates']['times']==[r['time'] for r in reference['rows'] if r['variable']=='temperature'])
    for axis in ('depth_m','latitude','longitude'):check('native '+axis,m['coordinates'][axis]==reference[axis])
    for row in reference['rows']:
        sample=row['samples'][1];z,y,x=sample['indices']
        result=get(f'/api/cases/{CASE}/subset?variable={row["variable"]}&time_index={row["time_index"]}&depth_index={z}&west={sample["longitude"]}&east={sample["longitude"]}&south={sample["latitude"]}&north={sample["latitude"]}')
        check(f'original value {row["variable"]} {row["time_index"]}',result['values']==[sample['value']] and result['time']==row['time'])
    result=get(f'/api/cases/{CASE}/subset?variable=temperature&time_index=2&representation=display&operation=volume')
    check('bounded display volume',result['shape']==[40,14,7] and len(result['values'])==3920)
    recipe=dict(mode='ocean',case_id=CASE,variable='temperature',time_index=2,view='slice',depth_index=19,section_index=13,point=[3,17,19],paint=dict(min=0,max=30,log=False,palette='thermal',opacity=1),iso=20,exaggeration=200,window_depth=1000,cutaway=True,quality='basic',show_instruments=True)
    capture=get('/api/investigations/capture',{'title':'March source proof','recipe':recipe})
    replay=get('/api/investigations/replay',capture['replay'])
    check('exact replay',capture['results']==replay['results'] and capture['result_sha256']==replay['result_sha256'])
    with ZipFile(io.BytesIO(request('/api/investigations/export',{'replay':capture['replay']}))) as archive:
        check('export retains exact results',json.loads(archive.read('investigation.json'))['results']==capture['results'])
    access=get('/api/data-access?case_id='+CASE)
    download=request(access['download'])
    check('CF download hash',hashlib.sha256(download).hexdigest()==access['file']['sha256'])
    check('public THREDDS remains explicit',access['standards']['public_url'] is None)
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps({'passed':all(c['passed'] for c in checks),'url':url,'checks':checks,'measurements':measurements,
        'limitations':['Serial representative requests on this machine and connection, not a concurrency capacity claim.','Replay applies to the model investigation, not imported profiles.']},indent=2)+'\n',encoding='utf8')
    print(json.dumps({'passed':True,'checks':len(checks),'requests':len(measurements),'max_seconds':max(m['seconds'] for m in measurements)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',action='store_true');parser.add_argument('--url')
    parser.add_argument('--report',type=Path,default=ROOT/'docs/evidence/p16b-http.json')
    args=parser.parse_args()
    if args.reference:reference()
    elif args.url:verify(args.url,args.report)
    else:parser.error('Choose --reference or --url.')

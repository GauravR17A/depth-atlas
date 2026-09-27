"""Small reproducible measurements, not capacity predictions or stress certification."""
import argparse,concurrent.futures,ctypes,gzip,hashlib,json,os,threading,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import requests
from api.wider_store import WiderStore,canonical
from science.wider_contracts import WiderQuery
from science.contracts import UnsupportedData
ROOT=Path(__file__).resolve().parents[1]

def rss():
    if os.name!='nt':return None
    class Memory(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('pagefault',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ['peak','working','peakpool','pool','peaknon','non','pagefile','peakpagefile']]
    current=ctypes.windll.kernel32.GetCurrentProcess;current.restype=ctypes.c_void_p
    read=ctypes.windll.psapi.GetProcessMemoryInfo;read.argtypes=[ctypes.c_void_p,ctypes.POINTER(Memory),ctypes.c_ulong];read.restype=ctypes.c_int
    m=Memory();m.cb=ctypes.sizeof(m)
    if not read(current(),ctypes.byref(m),m.cb):raise OSError('Working-set measurement failed')
    assert m.working>0
    return m.working

def main():
    p=argparse.ArgumentParser();p.add_argument('--base-url',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-audit',action='store_true');a=p.parse_args()
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'base_url':a.base_url,'scope':'Single local process cache measurements plus a bounded four-client HTTP sample. This is not a sustained load test.','cold_warm':[],'source_audit':[],'http_concurrency':[]}
    if a.source_audit:
        for dataset in ['godas-2022','gobai-v2.2']:
            source=json.loads((ROOT/f'casepacks/wider/{dataset}/source.json').read_text('utf-8'))
            for r in source['files']:
                raw=gzip.decompress((ROOT/f'casepacks/wider/{dataset}'/r['path']).read_bytes());packed=np.frombuffer(raw,dtype='<f4').reshape(r['shape']);v=r['source_variable'];t=r['source_time_index']
                if dataset=='godas-2022':original=np.concatenate([np.load(ROOT/f'data/raw/wider/{v}-{t}-{z}.npy',allow_pickle=False) for z in range(0,28,4)],axis=1)[0]
                else:original=np.frombuffer((ROOT/f'data/raw/wider/gobai/{v}-{t}.bin').read_bytes(),dtype='>f4').reshape(r['shape'])
                assert np.array_equal(packed,original,equal_nan=True)
                # GODAS journal records little-endian prepared bytes; GOBAI
                # records the original big-endian HTTP byte range.
                source_bytes=raw if dataset=='godas-2022' else (ROOT/f'data/raw/wider/gobai/{v}-{t}.bin').read_bytes()
                assert hashlib.sha256(source_bytes).hexdigest()==r['raw_sha256']
                assert hashlib.sha256((ROOT/f'casepacks/wider/{dataset}'/r['path']).read_bytes()).hexdigest()==r['sha256']
                report['source_audit'].append({'dataset':dataset,'file':r['path'],'values_compared':packed.size,'exact':True,'raw_sha256':r['raw_sha256']})
    for source in ['godas-2022','gobai-v2.2']:
        q=WiderQuery() if source=='godas-2022' else WiderQuery(dataset=source,variable='oxygen',level_min=2.5,level_max=1975)
        w=WiderStore(ROOT/'casepacks/wider');before=rss()
        for resolution in ['preview','display','native']:
            selected=q.model_copy(update={'resolution':resolution});times=[]
            for i in range(2):
                t=time.perf_counter();r=w.subset(selected);times.append(time.perf_counter()-t)
            raw=canonical(r).encode();report['cold_warm'].append({'dataset':source,'resolution':resolution,'first_seconds':times[0],'cached_seconds':times[1],'note':'Fresh store only for preview; later stages share native cache. OS disk cache is not cleared.','json_bytes':len(raw),'gzip_bytes':len(gzip.compress(raw)),'shape':r['shape'],'rss_before_bytes':before,'rss_after_bytes':rss(),'native_cache_bytes':w.native.bytes,'response_cache_bytes':w.responses.bytes})
        for i in range(18):w.subset(q.model_copy(update={'west':-65+i/10,'east':-45+i/10,'time_index':i%2}))
        assert w.native.bytes<=40*1024**2 and len(w.native.entries)<=3 and w.responses.bytes<=12*1024**2 and len(w.responses.entries)<=12
    # Verify saturation deterministically instead of assuming a timing-dependent 429.
    w=WiderStore(ROOT/'casepacks/wider')
    with w.capacity(),w.capacity(),w.capacity(),w.capacity():
        try:w.subset(WiderQuery());raise AssertionError('Capacity bound failed')
        except UnsupportedData as e:assert e.code=='regional_capacity'
    assert w.subset(WiderQuery())['valid_count']>0;report['capacity_bound_and_recovery']=True
    for round_index in range(2):
        gate=threading.Barrier(4)
        def fetch(i):
            query=WiderQuery(time_index=i%2,variable='source_salinity' if i>=2 else 'potential_temperature').model_dump();gate.wait();t=time.perf_counter();r=requests.post(a.base_url+'/api/wider/subset',json=query,timeout=40);assert r.status_code==200,(r.status_code,r.text[:200]);field=r.json();assert field['valid_count']>0;return {'client':i,'status':r.status_code,'seconds':time.perf_counter()-t,'decoded_bytes':len(r.content),'content_encoding':r.headers.get('Content-Encoding'),'source_sha256':field['source_sha256']}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:report['http_concurrency'].append({'round':round_index+1,'clients':list(executor.map(fetch,range(4)))})
    report['passed']=True;a.output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'passed':True,'source_files':len(report['source_audit']),'http_requests':8}))

if __name__=='__main__':main()

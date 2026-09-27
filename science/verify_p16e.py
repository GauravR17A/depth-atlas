"""Serial hosted publication and six-format original-input verification."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import httpx
from adapters.import_preview import inspect_import
from api.version import APP_VERSION
from api.instrument_store import InstrumentStore

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    if args.report.exists():raise SystemExit('Use a new evidence path; prior results are retained.')
    checks=[];requests=[];completed=False
    def check(name,condition):
        checks.append(dict(name=name,passed=bool(condition)))
        if not condition:raise AssertionError(name)
    with httpx.Client(base_url=args.url.rstrip('/'),timeout=45,follow_redirects=True) as client:
        def request(method,path,**kwargs):
            start=time.perf_counter();r=client.request(method,path,**kwargs)
            requests.append(dict(path=path,status=r.status_code,seconds=time.perf_counter()-start,decoded_bytes=len(r.content)))
            check('compatible '+path,r.headers.get('X-Ocean-App-Version')==APP_VERSION)
            return r
        try:
            r=request('GET','/api/publication');check('publication available',r.status_code==200)
            publication=r.json();local=json.loads((ROOT/'api/publication.json').read_text())
            check('exact prepared identity',publication['serving']['publication_id']==local['publication_id'])
            check('historical dates and retrieval unchanged',publication['serving']['cases']==local['cases'])
            check('public status bounded without file inventory',len(r.content)<20_000 and 'files' not in publication['serving'])
            check('bundled deployment is explicit',publication['refresh']['state']=='bundled')
            check('status is never stale-cached',r.headers['cache-control']=='no-store')
            for path in sorted((ROOT/'casepacks/instruments/examples').glob('*')):
                if path.suffix not in {'.nc','.csv'}:continue
                body=path.read_bytes();source=next((e['source_url'] for e in InstrumentStore(ROOT/'casepacks/instruments').catalog()['examples'] if e['sha256']==hashlib.sha256(body).hexdigest()),'')
                expected=json.loads(json.dumps(inspect_import(body,path.name,None,source)))
                r=request('POST','/api/instruments/inspect',params={'filename':path.name},content=body,headers={'Content-Type':'application/octet-stream'})
                check(path.name+' decoded review matches local original-byte parsing',r.status_code==200 and r.json()==expected)
            r=request('POST','/api/instruments/inspect?filename=too-large.csv',content=b'x'*2_000_001,headers={'Content-Type':'application/octet-stream'})
            check('single-file bound unchanged',r.status_code==413)
            completed=True
        finally:
            report=dict(url=args.url,app_version=APP_VERSION,passed=completed and bool(checks) and all(c['passed'] for c in checks),checks=checks,requests=requests,limitations=['Serial requests on the available connection; not concurrent capacity.','Generated workload fixtures are tested separately from these genuine source files.'])
            args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],checks=len(checks),requests=len(requests),report=str(args.report))))


if __name__=='__main__':main()

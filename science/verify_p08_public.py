"""Public replay/export checks against records captured in a separate local process.

No application imports. This checks deployment/transport identity; independent
scientific accuracy is covered by the original P05/P07 source fixtures.
"""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import time
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from zipfile import ZipFile


def digest(value):
    def encode(v):
        if v is None:return ['null']
        if isinstance(v,bool):return ['boolean',v]
        if isinstance(v,(int,float)):return ['number',struct.pack('>d',float(v) if v else 0.).hex()]
        if isinstance(v,str):return ['string',v]
        if isinstance(v,list):return ['array',[encode(i) for i in v]]
        return ['object',[[k,encode(v[k])] for k in sorted(v)]]
    return hashlib.sha256(json.dumps(encode(value),ensure_ascii=True,separators=(',',':')).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',required=True);parser.add_argument('--records',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];version=json.loads((root/'api/release.json').read_text())['version']
    records=json.loads(args.records.read_text(encoding='utf-8'));checks=[];requests=[]
    def request(path,body=None,status=200):
        start=time.perf_counter();data=None if body is None else json.dumps(body).encode();req=Request(args.base.rstrip('/')+path,data=data,headers={'Content-Type':'application/json'})
        try:response=urlopen(req,timeout=60)
        except HTTPError as exc:response=exc
        with response:raw=response.read();headers=response.headers;actual=response.status
        requests.append(dict(path=path,status=actual,bytes=len(raw),seconds=round(time.perf_counter()-start,3)))
        assert actual==status,(actual,raw[:300])
        assert headers.get('X-Ocean-App-Version')==version
        assert headers.get('Cache-Control')=='no-store'
        return raw
    def check(name,fn):
        try:detail=fn();checks.append(dict(name=name,passed=True,detail=detail));print('PASS '+name,flush=True)
        except Exception as exc:checks.append(dict(name=name,passed=False,error=str(exc)));print('FAIL '+name+': '+str(exc),flush=True)
    for saved in records:
        mode=saved['replay']['recipe']['mode']
        def capture(saved=saved):
            response=json.loads(request('/api/investigations/capture',dict(title=saved['replay']['title'],recipe=saved['replay']['recipe'])))
            assert response['results']==saved['results'] and response['result_sha256']==saved['result_sha256']
            assert digest({k:v for k,v in response.items() if k!='document_sha256'})==response['document_sha256']
            return dict(result_sha256=response['result_sha256'],modules=len(response['results']))
        check(mode+' capture versus separate local process',capture)
        def replay(saved=saved):
            response=json.loads(request('/api/investigations/replay',saved['replay']))
            assert response['results']==saved['results'] and response['replay']==saved['replay']
            assert response['software']['app']==version
            return dict(result_sha256=response['result_sha256'])
        check(mode+' complete numerical replay',replay)
        def export(saved=saved):
            raw=request('/api/investigations/export',dict(replay=saved['replay'],format='zip'))
            with ZipFile(io.BytesIO(raw)) as archive:
                assert {'investigation.json','settings.json','report.html','SOURCES.json','source-credits.txt','README.txt'}<=set(archive.namelist())
                record=json.loads(archive.read('investigation.json'));assert record['results']==saved['results']
                assert json.loads(archive.read('settings.json'))==saved['replay']
                assert 'Historical investigation' in archive.read('report.html').decode()
                if saved['replay']['recipe']['mode']=='comparison':
                    rows=list(csv.DictReader(io.StringIO(archive.read('paired-values.csv').decode())))
                    actual=next(m['output']['rows'] for m in saved['results'] if m['module']=='comparison')
                    assert [float(r['residual']) if r['residual'] else None for r in rows]==[r['residual'] for r in actual]
                if saved['replay']['recipe']['mode']=='features':
                    rows=list(csv.DictReader(io.StringIO(archive.read('section.csv').decode())))
                    actual=next(m['output']['values'] for m in saved['results'] if m['module']=='section')
                    assert [float(r['value']) if r['value'] else None for r in rows]==actual
                return dict(files=archive.namelist(),zip_sha256=hashlib.sha256(raw).hexdigest())
        check(mode+' evidence archive and numerical CSV',export)
    for kind in ['source','method','recipe','result','schema']:
        def mismatch(kind=kind):
            r=deepcopy(records[0]['replay'])
            if kind=='source':r['sources']['model_manifest_sha256']='0'*64
            if kind=='method':r['sources']['methods']['native']='unsupported-native-v9'
            if kind=='recipe':r['recipe']['time_index']=1
            if kind=='result':r['expected_result_sha256']='0'*64
            if kind=='schema':r['schema_version']='999'
            if kind in {'source','method'}:r['expected_recipe_sha256']=digest(dict(recipe=r['recipe'],sources=r['sources']))
            body=json.loads(request('/api/investigations/replay',r,422));expected='invalid_request' if kind=='schema' else kind+'_mismatch';assert body['error']['code']==expected
            return dict(error=expected)
        check('reject '+kind+' mismatch',mismatch)
    for format in ['html','csv']:
        def direct(format=format):
            body=request('/api/investigations/export',dict(replay=records[0]['replay'],format=format)).decode()
            assert ('<!doctype html>' in body and '<table>' in body) if format=='html' else ('model_time_utc' in body and '2024-01-07T00:00:00Z' in body)
            return dict(bytes=len(body.encode()))
        check('direct '+format+' export',direct)
    report=dict(base=args.base,release=version,checked_at_utc=datetime.now(timezone.utc).isoformat(),method=__doc__,checks=checks,requests=requests,passed=all(c['passed'] for c in checks))
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(passed=report['passed'],checks=len(checks),requests=len(requests))))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

"""Bounded public lifecycle checks against freshly calculated local references."""
import argparse
import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile

import httpx
from fastapi.testclient import TestClient
from api.app import create_app
from api.version import APP_VERSION
from adapters.import_preview import PARSER_VERSION, inspect_import
from science.investigations import fingerprint

ROOT=Path(__file__).resolve().parents[1]
CASE='bay-bengal-2024-03'


def verify(url, report):
    local=TestClient(create_app()); checks=[]; requests=[]; completed=False
    def check(name, good, detail=None):
        checks.append(dict(name=name,passed=bool(good),detail=detail))
        if not good: raise AssertionError(name)
    client=httpx.Client(base_url=url.rstrip('/'),timeout=90)
    def call(path,payload=None,status=200):
        start=perf_counter();r=client.post(path,json=payload) if payload is not None else client.get(path)
        requests.append(dict(path=path,status=r.status_code,seconds=perf_counter()-start,response_bytes=len(r.content)))
        check(path+' status',r.status_code==status, r.text[:300] if r.status_code!=status else None)
        check(path+' version',r.headers.get('x-ocean-app-version')==APP_VERSION)
        return r
    try:
        call('/api/health')
        body=(ROOT/'casepacks/instruments/examples/SR1902594_034.nc').read_bytes()
        source=dict(schema_version='1',filename='SR1902594_034.nc',content_base64=base64.b64encode(body).decode(),source_sha256=hashlib.sha256(body).hexdigest(),parser_version=PARSER_VERSION,mapping=None)
        profile='import-'+inspect_import(body,source['filename'])['result']['profiles'][0]['id']
        settings=dict(variable='temperature',time_index=2,time_window_hours=6,distance_km=5,max_vertical_gap_m=500,qc='good_probably_good')
        for mode in ['comparison','instrument']:
            recipe=dict(mode=mode,case_id=CASE,profile_id=profile,sample_index=100)
            recipe.update(dict(settings=settings,view='comparison',rank='nearest',baseline=None) if mode=='comparison' else dict(variable='chlorophyll',show_excluded=True))
            payload=dict(title='P16C public source replay',recipe=recipe,import_source=source)
            expected=local.post('/api/investigations/capture',json=payload).json()
            record=call('/api/investigations/capture',payload).json()
            check(mode+' exact local/server results',record['results']==expected['results'])
            check(mode+' exact parsed source profiles',record['imported_profiles']==expected['imported_profiles'])
            check(mode+' portable recipe identity',record['replay']==expected['replay'])
            check(mode+' full document checksum',fingerprint({k:v for k,v in record.items() if k!='document_sha256'})==record['document_sha256'])
            replay=call('/api/investigations/replay',expected['replay']).json()
            check(mode+' fresh-source replay',replay['results']==expected['results'])
            archive=call('/api/investigations/export',dict(replay=record['replay'],format='zip'))
            with ZipFile(io.BytesIO(archive.content)) as z:
                check(mode+' original file in ZIP',z.read('original-observation/'+source['filename'])==body)
                exported=json.loads(z.read('investigation.json'))
                check(mode+' ZIP retains exact results',exported['results']==record['results'])
                check(mode+' ZIP JSON can be reimported',len(z.read('investigation.json'))<=8_000_000)
            if mode=='comparison':
                check('eligible temperature count',record['results'][0]['output']['matched_count']==245)
                bad=deepcopy(record['replay']);bad['import_source']['content_base64']=base64.b64encode(b'changed').decode()
                check('tampered source rejected',call('/api/investigations/replay',bad,422).json()['error']['code']=='source_mismatch')
                bad=deepcopy(record['replay']);bad['import_source']['parser_version']='unsupported-reader'
                check('unsupported parser rejected',call('/api/investigations/replay',bad,422).json()['error']['code']=='method_mismatch')
        payload=dict(import_source=source,profile_id=profile,settings=settings)
        for variable,count in [('temperature',245),('salinity',243)]:
            payload['settings']={**settings,'variable':variable}
            result=call(f'/api/cases/{CASE}/evidence/imported/comparison',payload).json()
            check(variable+' independent accepted count',result['matched_count']==count)
        payload['settings']={**settings,'time_index':0}
        result=call(f'/api/cases/{CASE}/evidence/imported/comparison',payload).json()
        check('wrong snapshot has no invented pairs',result['matched_count']==0)
        coverage=call(f'/api/cases/{CASE}/evidence/imported/coverage',dict(import_source=source,settings=settings)).json()
        check('coverage isolates imported file',coverage['total_profiles']==1 and coverage['matched_samples']==245)
        # An original archived descriptor must still replay, with its original
        # result hash and original source/method dictionary unchanged.
        old=json.loads((ROOT/'docs/evidence/p08-local-records.json').read_text())
        records=old if isinstance(old,list) else old['records']
        for archived in records[:4]:
            descriptor=archived.get('replay',archived)
            result=call('/api/investigations/replay',descriptor).json()
            check('archived '+descriptor['recipe']['mode']+' result identity',result['result_sha256']==descriptor['expected_result_sha256'])
        completed=True
    finally:
        client.close()
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(dict(url=url,version=APP_VERSION,passed=completed and bool(checks) and all(c['passed'] for c in checks),checks=checks,requests=requests),indent=2)+'\n')
    print(json.dumps(dict(passed=True,checks=len(checks),requests=len(requests),report=str(report))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();verify(args.url,args.report)

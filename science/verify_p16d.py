"""Check served support against local sources, eligible P05 rows and empty gates."""
import argparse
import base64
import hashlib
import json
import time
import urllib.request
from pathlib import Path

from api.case_store import CaseStore
from api.instrument_store import InstrumentStore
from api.evidence_store import EvidenceStore
from api.feature_store import FeatureStore
from api.support_store import SupportStore
from science.feature_contracts import FeatureQuery
from science.support import SupportRequest

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);parser.add_argument('--report',required=True)
    args=parser.parse_args();checks=[];requests=[]
    def check(name,condition):
        checks.append(dict(name=name,passed=bool(condition)))
        if not condition: raise AssertionError(name)
    def post(path,payload):
        request=urllib.request.Request(args.url.rstrip('/')+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        start=time.monotonic()
        with urllib.request.urlopen(request,timeout=60) as response:
            data=response.read();requests.append(dict(path=path,status=response.status,seconds=round(time.monotonic()-start,4),bytes=len(data)))
        return json.loads(data)
    cases=CaseStore(ROOT/'casepacks');instruments=InstrumentStore(ROOT/'casepacks/instruments')
    evidence=EvidenceStore(cases,instruments);features=FeatureStore(cases,instruments,evidence);store=SupportStore(features)
    original=(ROOT/'casepacks/instruments/examples/SR1902594_034.nc').read_bytes()
    imported=dict(schema_version='1',filename='SR1902594_034.nc',source_sha256=hashlib.sha256(original).hexdigest(),parser_version='observation-preview-v1',mapping=None,content_base64=base64.b64encode(original).decode())
    try:
        for case_id,query,source in [
            ('bay-bengal-2024-01',FeatureQuery(),None),
            ('arabian-sea-2024-01',FeatureQuery(),None),
            ('bay-bengal-2024-03',FeatureQuery(time_index=2,threshold=20),imported),
        ]:
            search=features.search(case_id,query);region=search['regions'][0]['id']
            payload=dict(query=query.model_dump(mode='json'),region_id=region,settings=dict(variable=query.variable,time_index=query.time_index))
            if source: payload['import_source']=source
            expected=store.run(case_id,SupportRequest.model_validate(payload))
            actual=post(f'/api/cases/{case_id}/features/support',payload)
            check(case_id+' exact local/source result',actual==expected)
            check(case_id+' disjoint cell accounting',actual['supported_cells']+actual['unsupported_cells']==actual['region_cells'])
            check(case_id+' distinct cell count',len({tuple(r['cell']) for r in actual['rows']})==actual['supported_cells'])
            check(case_id+' distinct profile count',len({r['profile_id'] for r in actual['rows']})==actual['eligible_profiles'])
            check(case_id+' source dates retained',all(r['observation_time'].startswith('2024-') for r in actual['rows']))
            check(case_id+' residual identity',all(abs(r['residual']-(r['model']-r['observed']))<1e-12 for r in actual['rows']))
            empty_payload={**payload,'settings':{**payload['settings'],'time_window_hours':0}}
            empty=post(f'/api/cases/{case_id}/features/support',empty_payload)
            check(case_id+' strict window exact replay',empty==store.run(case_id,SupportRequest.model_validate(empty_payload)))
            check(case_id+' empty support has all gaps',empty['eligible_samples']==0 and empty['unsupported_cells']==empty['region_cells'])
        report=dict(url=args.url,checked_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),passed=all(c['passed'] for c in checks),checks=checks,requests=requests)
    except Exception as error:
        report=dict(url=args.url,passed=False,error=str(error),checks=checks,requests=requests)
    Path(args.report).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],checks=len(checks),requests=len(requests),error=report.get('error'))))
    if not report['passed']: raise SystemExit(1)


if __name__=='__main__': main()

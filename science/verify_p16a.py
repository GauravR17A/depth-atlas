"""Verify real import examples, source identity and explicit model overlap.

Optional HTTP checks use the same public input files, never user uploads.
Overlap counts establish geometry/time only, not numerical comparability.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

from adapters.import_preview import inspect_import
from api.case_store import CaseStore
from api.instrument_store import InstrumentStore

ROOT = Path(__file__).resolve().parents[1]


def fetch(url, body=None):
    headers={'Accept-Encoding':'gzip'}
    if body is not None: headers['Content-Type']='application/octet-stream'
    with urlopen(Request(url,data=body,headers=headers),timeout=45) as response:
        raw=response.read(4_000_001)
        assert len(raw)<=4_000_000, 'Unexpectedly large public response'
        return gzip.decompress(raw) if response.headers.get('Content-Encoding')=='gzip' else raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    dest = Path(args.report)
    dest.parent.mkdir(parents=True,exist_ok=True)
    instruments = InstrumentStore(ROOT/'casepacks/instruments')
    cases = CaseStore(ROOT/'casepacks')
    output = {'url': args.url, 'examples': [], 'limits': [
        'Counts concern samples, including multiple variables at the same sample.',
        'Rectangle/time intersection does not establish valid matching or independent validation.',
        'No model chlorophyll field is supplied. Imported numerical comparisons remain unavailable.',
    ]}
    for example in instruments.catalog()['examples']:
        path = instruments.example(example['name'])
        body = path.read_bytes()
        # Compare the wire contract: Python coordinate tuples serialize as JSON arrays.
        review = json.loads(json.dumps(inspect_import(body, path.name, source_url=example['source_url'])))
        item = {'name': path.name, 'sha256': hashlib.sha256(body).hexdigest(),
                'source_url': example['source_url'], 'profiles': [], 'http_verified': False}
        output['examples'].append(item)
        if args.url:
            endpoint = args.url.rstrip('/') + '/api/instruments/'
            print('Checking '+path.name,flush=True)
            try:
                assert fetch(endpoint+'examples/'+path.name)==body, 'Published example differs'
                published=json.loads(fetch(endpoint+'inspect?filename='+path.name,body))
                assert published == review, 'Published import interpretation differs from local reference'
                item['http_verified'] = True
            except Exception as error:
                item['http_error']=str(error)
                dest.write_text(json.dumps(output,indent=2),encoding='utf-8')
                raise
        for p in review['result']['profiles']:
            summary = {k:p[k] for k in ['id','instrument','time','time_end','latitude','longitude','samples']}
            summary['accepted_by_variable'] = {k:v['accepted_count'] for k,v in p['parameters'].items()}
            summary['case_overlap'] = {}
            for manifest, _ in cases.available():
                w,s,e,n = manifest.case.bounds
                start,end = min(manifest.coordinates.times), max(manifest.coordinates.times)
                inside = []
                for level in p['levels']:
                    lon = level['longitude'] + 360 * round(((w+e)/2-level['longitude'])/360)
                    if level['coordinate_eligible'] and w<=lon<=e and s<=level['latitude']<=n:
                        inside.append(level)
                summary['case_overlap'][manifest.case.id] = {
                    'coordinate_eligible_samples_inside_rectangle':len(inside),
                    'also_inside_time_range':sum(start<=level['time']<=end for level in inside),
                }
            item['profiles'].append(summary)
    output['complete']=True
    dest.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(f"Verified {len(output['examples'])} examples; report: {dest}")


if __name__ == '__main__': main()

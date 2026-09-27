"""Measure bounded import workloads. Generated CSVs are test fixtures, not observations."""
import argparse
import hashlib
import json
import time
import tracemalloc
from pathlib import Path

from adapters.import_preview import inspect_import

ROOT = Path(__file__).resolve().parents[1]


def fixture(index, samples=2500):
    header = 'profile_id,instrument,platform,time,latitude,longitude,pressure_dbar,pressure_qc,position_qc,time_qc,temperature_c,temperature_qc,salinity_psu,salinity_qc\n'
    return (header + ''.join(f'load-{index},argo,TEST-FIXTURE-{index},2024-03-29T00:00:00Z,12.5,85.5,{i/2},1,1,1,{28-i/500},1,35,1\n' for i in range(samples))).encode()


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--report',required=True);args=parser.parse_args()
    inputs = [(p.name,p.read_bytes(),'genuine source') for p in (ROOT/'casepacks/instruments/examples').glob('*') if p.suffix in {'.nc','.csv'}]
    folder=ROOT/'.runtime/p16e/workload';folder.mkdir(parents=True,exist_ok=True)
    generated=[]
    for i in range(8):
        body=fixture(i);name=f'workload-{i}.csv';(folder/name).write_bytes(body)
        generated.append((name,body,'generated workload fixture, not observations'))
    reports=[]
    for name,body,kind in inputs+generated:
        tracemalloc.start();start=time.perf_counter()
        result=inspect_import(body,name);seconds=time.perf_counter()-start
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        profiles=result['result']['profiles'] if result['result'] else []
        reports.append(dict(filename=name,kind=kind,source_bytes=len(body),source_sha256=hashlib.sha256(body).hexdigest(),profiles=len(profiles),samples=sum(p['samples'] for p in profiles),normalized_bytes=len(json.dumps(profiles,separators=(',',':')).encode()),review_bytes=len(json.dumps(result,separators=(',',':')).encode()),seconds=seconds,python_traced_peak_bytes=peak,issue=result['issue']))
    batch=reports[-8:]
    report=dict(measured_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),method='serial parser, tracemalloc tracks Python allocations, not full native RSS',inputs=reports,batch=dict(files=8,samples=sum(r['samples'] for r in batch),source_bytes=sum(r['source_bytes'] for r in batch),normalized_bytes=sum(r['normalized_bytes'] for r in batch),seconds=sum(r['seconds'] for r in batch)),limitations=['Single-file and response limits are unchanged.','Browser heap, source retention, concurrent users and deployment need separate checks.','Generated samples exercise resource handling, not scientific validation.'])
    Path(args.report).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'batch':report['batch'],'genuine_files':len(inputs),'issues':sum(bool(r['issue']) for r in reports)}))


if __name__=='__main__':main()

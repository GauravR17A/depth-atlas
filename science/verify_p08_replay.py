"""Run capture and replay in separate processes, without warmed application caches."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from api.app import create_app
from fastapi.testclient import TestClient

def main():
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--capture',type=Path);group.add_argument('--replay',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    client=TestClient(create_app());source=json.loads((args.capture or args.replay).read_text(encoding='utf-8'))
    if args.capture:
        records=[]
        for recipe in source:
            response=client.post('/api/investigations/capture',json={'title':'Fresh process '+recipe['mode'],'recipe':recipe});assert response.status_code==200,response.text;records.append(response.json())
        args.output.write_text(json.dumps(records,ensure_ascii=True),encoding='utf-8')
    else:
        rows=[]
        for record in source:
            response=client.post('/api/investigations/replay',json=record['replay']);assert response.status_code==200,response.text
            actual=response.json();same=actual['results']==record['results'] and actual['result_sha256']==record['result_sha256']
            rows.append({'mode':record['replay']['recipe']['mode'],'passed':same,'result_sha256':actual['result_sha256']})
        args.output.write_text(json.dumps({'passed':all(r['passed'] for r in rows),'records':len(rows),'checks':rows},indent=2),encoding='utf-8')
        assert all(r['passed'] for r in rows)
    print('Fresh-process '+('capture' if args.capture else 'replay')+' passed')
if __name__=='__main__':main()

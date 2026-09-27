"""Compare deployed case data with independently checked, immutable local assets."""
import argparse
import json
import hashlib
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    session=requests.Session();checks=[]
    def get(path):
        r=session.get(args.base.rstrip('/')+path,timeout=(15,60));assert r.status_code==200,(path,r.status_code,r.text[:100]);return r
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)});assert condition,name
    guide=json.loads((ROOT/'casepacks/guides/indian-ocean.json').read_text(encoding='utf8'))
    check('deployed guide exact identity',get('/api/guided-cases').json()==guide)
    check('two available cases',get('/api/health').json()['case_count']==2)
    for c in guide['columns']:
        cid=c['case_id'];m=get('/api/cases/'+cid).json();check(cid+' manifest',m==json.loads((ROOT/'casepacks'/cid/'manifest.json').read_text(encoding='utf8')))
        for depth_index in (0,19,26,39):
            params=f'?variable=temperature&time_index=1&operation=depth_slice&depth_index={depth_index}&west={c["longitude"]}&east={c["longitude"]}&south={c["latitude"]}&north={c["latitude"]}'
            value=get('/api/cases/'+cid+'/subset'+params).json();check(cid+f' native value at {c["depth_m"][depth_index]} m',value['values']==[c['temperature_c'][depth_index]] and value['manifest_sha256']==c['manifest_sha256'])
        record=json.loads((ROOT/'casepacks/standards'/('manifest.json' if cid.startswith('bay-') else cid+'.json')).read_text(encoding='utf8'))
        exchange=get('/data/'+cid+'.nc');check(cid+' exchange checksum',hashlib.sha256(exchange.content).hexdigest()==record['sha256'])
        comp=get('/api/cases/'+cid+'/evidence/profiles/'+c['comparison']['profile_id']+'?time_index=1').json();check(cid+' eligible guide comparison',comp['matched_count']==c['comparison']['matched_count'])
        check(cid+' comparison source identity',comp['manifest_sha256']==c['manifest_sha256'])
    check('Arabian THREDDS is not advertised',get('/api/data-access?case_id=arabian-sea-2024-01').json()['standards']['protocols']==[])
    wrong=session.post(args.base.rstrip('/')+'/api/investigations/capture',json={'title':'Case isolation check','recipe':{'mode':'instrument','case_id':'bay-bengal-2024-01','profile_id':guide['columns'][1]['comparison']['profile_id'],'variable':'temperature'}},timeout=(15,60))
    check('reject cross-library investigation',wrong.status_code==404 and wrong.json()['error']['code']=='profile_not_found')
    Path(args.output).write_text(json.dumps({'base':args.base,'checks':checks},indent=2)+'\n');print(f'{len(checks)} public case and source checks passed.')
if __name__=='__main__':main()

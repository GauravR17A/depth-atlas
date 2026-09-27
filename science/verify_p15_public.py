"""Bounded transport checks; local arithmetic is not independent ocean validation."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from api.wider_store import WiderStore, regional_csv
from science.wider_contracts import WiderQuery, WiderProfileRequest, WIDER_METHOD
from science.verify_p13_public import Audit, exact

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--records-output',type=Path);p.add_argument('--replay-records',type=Path)
    p.add_argument('--replay-only',action='store_true');p.add_argument('--expected-version',default='0.15.2')
    p.add_argument('--timeout-seconds',type=float,default=40);p.add_argument('--max-runtime-seconds',type=float,default=900)
    a=p.parse_args();audit=Audit(a);audit.report.update(method_version=WIDER_METHOD,method=__doc__)
    store=WiderStore(ROOT/'casepacks/wider');records=[]
    def health():
        h=audit.json('/api/health');assert h['version']==a.expected_version and h['case_count']==5;return h
    audit.check('release and original five cases',health)
    def catalog():
        c=audit.json('/api/wider/catalog');exact(c,store.catalog());return {'datasets':len(c['datasets']),'presets':len(c['presets'])}
    audit.check('exact source catalogue',catalog)
    if not a.replay_only:
        queries=[('Atlantic temperature',WiderQuery()),('Atlantic October salinity',WiderQuery(variable='source_salinity',time_index=1)),('date line GODAS',WiderQuery(west=170,east=-170,south=-5,north=5)),('Southern Indian',WiderQuery(west=60,east=80,south=-55,north=-40)),('date line oxygen',WiderQuery(dataset='gobai-v2.2',variable='oxygen',west=170,east=-170,south=-5,north=5,level_min=2.5,level_max=1975)),('Southern oxygen October',WiderQuery(dataset='gobai-v2.2',variable='oxygen',time_index=1,west=60,east=80,south=-55,north=-40,level_min=2.5,level_max=1975)),('missing land',WiderQuery(west=10,east=20,south=15,north=25))]
        for name,q in queries:
            def run(q=q):
                exact(audit.json('/api/wider/preview',q.model_dump()),store.preview(q))
                for res in ['preview','display','native']:
                    rq=q.model_copy(update={'resolution':res});field=audit.json('/api/wider/subset',rq.model_dump());exact(field,store.subset(rq))
                pq=WiderProfileRequest(query=q,longitude=field['longitude'][len(field['longitude'])//2],latitude=field['latitude'][len(field['latitude'])//2]);exact(audit.json('/api/wider/profile',pq.model_dump()),store.profile(pq))
                pack=audit.json('/api/wider/pack',q.model_dump());exact(pack,store.pack(q));assert audit.json('/api/wider/replay',pack)['matched']
                csv=audit.request('/api/wider/csv',q.model_dump())[0].decode();assert csv==regional_csv(pack)
                records.append(pack)
                if a.records_output:a.records_output.write_text(json.dumps(dict(base_url=a.base_url,packs=records)),encoding='utf-8')
                return {'sha256':pack['sha256'],'shape':field['shape'],'valid_values':field['valid_count'],'vertical_units':field['dataset']['vertical_units']}
            audit.check(name+': exact native/display/profile/pack/replay/CSV',run)
        for name,changes,code in [('polar',dict(south=70,north=80),422),('size',dict(west=0,east=90,south=-20,north=20),413),('time',dict(time_index=3),422),('unknown source',dict(dataset='../'),422),('URL not accepted',dict(url='https://example.com'),422),('reversed latitude',dict(south=40,north=25),422)]:
            audit.check('reject '+name,lambda c=changes,s=code:audit.json('/api/wider/subset',{**WiderQuery().model_dump(),**c},status=s)['error']['code'])
        if records:
            bad=deepcopy(records[0]);bad['sha256']='0'*64
            audit.check('reject corrupted pack',lambda:audit.json('/api/wider/replay',bad,status=422)['error']['code'])
    if a.replay_records:
        for i,pack in enumerate(json.loads(a.replay_records.read_text('utf-8'))['packs']):
            def replay(pack=pack):
                assert audit.json('/api/wider/replay',pack)['matched'];q=json.loads(pack['payload_text'])['field']['query'];exact(audit.json('/api/wider/pack',q),pack);return pack['sha256']
            audit.check(f'exact cross-host pack {i+1}',replay)
    return audit.finish()

if __name__=='__main__':raise SystemExit(main())

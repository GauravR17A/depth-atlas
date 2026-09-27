"""Select a reproducible teaching pair, explicitly chosen to illustrate contrast."""
import json
from pathlib import Path
import numpy as np
from api.case_store import CaseStore, CASE_IDS
from api.instrument_store import InstrumentStore
from api.evidence_store import EvidenceStore
from science.evidence_contracts import MatchSettings

ROOT=Path(__file__).resolve().parents[1]

def prepare():
    cases=CaseStore(ROOT/'casepacks'); instruments=InstrumentStore(ROOT/'casepacks/instruments'); evidence=EvidenceStore(cases,instruments)
    arrays=[]; manifests=[]
    for cid in CASE_IDS:
        m,sha=cases.require(cid); manifests.append((m,sha))
        arrays.append(np.asarray(cases._read_array(cid,'analytical','temperature',1)).reshape(m.representations['analytical']['shape']))
    # Same snapshot, native 0 and 100 m, finite both. Largest depth contrast,
    # then first flattened Bay/Arabian index. This is illustrative selection.
    z=manifests[0][0].coordinates.depth_m.index(100)
    a,b=arrays; bs,bd=b[0].ravel(),b[z].ravel(); best=None
    for i,(surface,deep) in enumerate(zip(a[0].ravel(),a[z].ravel())):
        if not np.isfinite(surface+deep): continue
        js=np.flatnonzero(np.isfinite(bs)&np.isfinite(bd)&(np.abs(bs-surface)<=.05))
        if not len(js): continue
        j=int(js[np.argmax(np.abs(bd[js]-deep))]); candidate=(float(abs(bd[j]-deep)),-i,-j)
        if best is None or candidate>best: best=candidate
    if best is None: raise ValueError('No pair meets the declared surface tolerance.')
    columns=[]
    for cid,(m,sha),array,flat in zip(CASE_IDS,manifests,arrays,[-best[1],-best[2]]):
        y,x=divmod(flat,len(m.coordinates.longitude)); recommended=None
        for p in sorted(instruments.catalog(cid)['profiles'],key=lambda p:p['id']):
            result=evidence.comparison(cid,p['id'],MatchSettings(time_index=1))
            if result.matched_count:
                recommended={'profile_id':p['id'],'platform':p['platform'],'matched_count':result.matched_count};break
        if recommended is None: raise ValueError('Guide needs a supported comparison at its timestamp.')
        columns.append(dict(case_id=cid,region_id=m.case.region_id,label=m.case.title.split(' \u00b7')[0],manifest_sha256=sha,time_index=1,time=m.coordinates.times[1],point=[x,y,z],latitude=m.coordinates.latitude[y],longitude=m.coordinates.longitude[x],depth_m=m.coordinates.depth_m,temperature_c=[float(v) if np.isfinite(v) else None for v in array[:,y,x]],comparison=recommended))
    value=dict(schema_version='1',method='p09-native-teaching-pair-v1',surface_tolerance_c=.05,comparison_depth_m=100,selection='At 2024-01-07 12:00 UTC, compare every native column pair with finite values at 0 and 100 m and a surface difference no greater than 0.05 degrees Celsius. Choose the largest absolute 100 m difference, then the first flattened Bay and Arabian indices. Selected to illustrate contrast; not a representative basin average or a causal explanation.',columns=columns)
    out=ROOT/'casepacks/guides/indian-ocean.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'surface_difference_c':abs(columns[0]['temperature_c'][0]-columns[1]['temperature_c'][0]),'difference_at_100m_c':best[0],'columns':[{k:v for k,v in c.items() if k not in ('depth_m','temperature_c')} for c in columns]},indent=2))

if __name__=='__main__': prepare()

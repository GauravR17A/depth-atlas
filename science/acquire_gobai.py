"""Read a pinned CDF-2 GOBAI source using validated bounded HTTP byte ranges.

The full multi-gigabyte file is not downloaded or claimed to have a local hash.
Header, coordinate and selected monthly byte ranges are retained with hashes.
"""
from __future__ import annotations
import gzip
import hashlib
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import requests
import netCDF4

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/wider/gobai'
OUT = ROOT / 'casepacks/wider/gobai-v2.2'
BASE = 'https://www.nodc.noaa.gov/archive/arc0207/0259304/4.4/data/0-data/'
URL = BASE + 'GOBAI-O2-v2.2.nc'


def header(data):
    if data[:4] != b'CDF\x02': raise ValueError('Only checked CDF-2 input is supported')
    pos = 4
    def integer():
        nonlocal pos
        value = struct.unpack_from('>I', data, pos)[0]; pos += 4; return value
    def name():
        nonlocal pos
        n = integer()
        if n > 10000: raise ValueError('Header name exceeds limit')
        value = data[pos:pos+n].decode(); pos += (n+3)//4*4; return value
    def attributes():
        nonlocal pos
        tag, count = integer(), integer()
        if tag not in (0,12) or count > 256: raise ValueError('Unsupported attribute header')
        result = {}; sizes = {1:1,2:1,3:2,4:4,5:4,6:8}; formats = {1:'b',3:'h',4:'i',5:'f',6:'d'}
        for _ in range(count):
            key=name(); kind=integer(); count=integer(); size=sizes[kind]*count
            value=data[pos:pos+size]; pos+=(size+3)//4*4
            result[key]=value.decode() if kind==2 else list(struct.unpack('>'+formats[kind]*count,value))
        return result
    records=integer();tag,count=integer(),integer()
    if tag!=10 or count>16 or records!=0: raise ValueError('Unsupported record/grid layout')
    dimensions=[(name(),integer()) for _ in range(count)]
    attrs=attributes();tag,count=integer(),integer()
    if tag!=11 or count>32: raise ValueError('Unsupported variable layout')
    variables=[]
    for _ in range(count):
        key=name(); n=integer(); ids=[integer() for _ in range(n)]; at=attributes(); kind=integer(); size=integer()
        offset=struct.unpack_from('>Q',data,pos)[0];pos+=8
        variables.append({'name':key,'dimensions':[dimensions[i] for i in ids],'attributes':at,'type':kind,'size':size,'offset':offset})
    return {'dimensions':dimensions,'attributes':attrs,'variables':variables,'header_bytes':pos}


def acquire():
    RAW.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    jp=RAW/'ranges.json'; journal=json.loads(jp.read_text()) if jp.exists() else {'url':URL,'retrieved_at':datetime.now(timezone.utc).isoformat(),'ranges':[]}
    def fetch(start,length,label):
        path=RAW/(label+'.bin');known=next((x for x in journal['ranges'] if x['label']==label),None)
        if known and path.is_file():
            data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==known['sha256'];return data
        if not 0<length<=16_000_000:raise ValueError('Acquisition range exceeds limit')
        r=requests.get(URL,headers={'Range':f'bytes={start}-{start+length-1}','Accept-Encoding':'identity'},timeout=40)
        r.raise_for_status()
        if r.status_code!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {start}-{start+length-1}/') or len(r.content)!=length:raise ValueError('Provider did not honour exact byte range')
        identity={k:r.headers.get(k) for k in ['ETag','Last-Modified']}
        if 'identity' in journal and journal['identity']!=identity:raise ValueError('Source changed during acquisition')
        journal['identity']=identity;data=r.content;path.write_bytes(data)
        journal['ranges'].append({'label':label,'start':start,'bytes':length,'sha256':hashlib.sha256(data).hexdigest()})
        jp.write_text(json.dumps(journal,indent=2),encoding='utf-8');return data
    h=header(fetch(0,65536,'header')); by={v['name']:v for v in h['variables']}
    (RAW/'header.json').write_text(json.dumps(h,indent=2),encoding='utf-8')
    print('Header',json.dumps(h),flush=True)
    axes={}
    for key in ['lon','lat','pres','time']:
        v=by[key];assert len(v['dimensions'])==1
        dtype={5:'>f4',6:'>f8'}[v['type']];count=v['dimensions'][0][1]
        axes[key]=np.frombuffer(fetch(v['offset'],count*np.dtype(dtype).itemsize,key),dtype=dtype).tolist()
    dates=netCDF4.num2date(axes['time'],by['time']['attributes']['units'],calendar='standard')
    ids=[i for i,d in enumerate(dates) if d.year==2022 and d.month in (9,10)]
    if len(ids)!=2:raise ValueError('Expected September and October 2022')
    shape=(len(axes['pres']),len(axes['lat']),len(axes['lon']));block=int(np.prod(shape))*4;files=[]
    for variable in ['oxy','uncer']:
        v=by[variable]
        assert v['type']==5 and [d[0] for d in v['dimensions']]==['time','pres','lat','lon']
        for i in ids:
            data=fetch(v['offset']+i*block,block,f'{variable}-{i}')
            values=np.frombuffer(data,dtype='>f4').astype('<f4')
            packed=gzip.compress(values.tobytes(),compresslevel=6,mtime=0);name=f'{variable}-{i}.f32.gz';(OUT/name).write_bytes(packed)
            files.append({'path':name,'bytes':len(packed),'sha256':hashlib.sha256(packed).hexdigest(),'raw_sha256':hashlib.sha256(data).hexdigest(),'shape':list(shape),'source_variable':variable,'source_time_index':i,'time':dates[i].strftime('%Y-%m-%dT%H:%M:%SZ'),'source_url':URL,'source_range':[v['offset']+i*block,block]})
            print('Acquired',name,len(packed),flush=True)
    licence=requests.get(BASE+'GOBAI-O2-v2.2-license.txt',timeout=20);licence.raise_for_status();(OUT/'LICENSE.txt').write_bytes(licence.content)
    (OUT/'source.json').write_text(json.dumps({'axes':axes,'files':files,'header':h,'retrieved_at':journal['retrieved_at'],'source_identity':journal['identity'],'source_url':URL},indent=2),encoding='utf-8')


if __name__=='__main__':acquire()

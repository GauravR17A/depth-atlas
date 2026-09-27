"""Build the checked observation library. Does not alter the P02 model case."""
import hashlib
import json
import shutil
from pathlib import Path
from adapters.instruments import parse_instruments
from science.instruments import InstrumentSummary

ROOT=Path(__file__).resolve().parents[1]


def prepare():
    out=ROOT/'casepacks/instruments';out.mkdir(parents=True,exist_ok=True)
    raw=ROOT/'data/raw/instruments';items=[];examples=[];profiles=[]
    acquisition=json.loads((ROOT/'data/raw/acquisition.json').read_text())
    for path in sorted((ROOT/'data/raw/argo').glob('D*_012.nc')):
        item=next(x for x in acquisition['files'] if x['path'].endswith(path.name))
        url=item.get('source_url',item.get('url',''))
        if not url: url='https://data-argo.ifremer.fr/dac/incois/'+path.stem[1:8]+'/profiles/'+path.name
        items.append((path,url,'Bay of Bengal · January 2024','Argo GDAC / INCOIS DAC'))
    items.extend([
        (raw/'SR6903091_100.nc','https://data-argo.ifremer.fr/dac/coriolis/6903091/profiles/SR6903091_100.nc','Tropical Atlantic · September 2023','Argo GDAC / Coriolis'),
        (raw/'glider-ru29.nc',(raw/'glider-url.txt').read_text(),'Caribbean Sea · April 2024','IOOS Glider DAC / Rutgers University'),
        (raw/'ctd-station.csv','https://cchdo.ucsd.edu/data/6331/i06sb_ct1.zip','Southwest Indian Ocean · February 1996','CCHDO / CIVA2, MARION DUFRESNE'),
    ])
    files=[];sources=[]
    for path,url,collection,provider in items:
        body=path.read_bytes();parsed=parse_instruments(body,path.name,url)
        for p in parsed.profiles:
            p.collection=collection;p.metadata.update(provider=provider,acquired_date='2026-09-22',source_url=url)
            if p.instrument=='ctd':p.metadata['archive_member']='i06sb_00001_00001_ct1.csv'
            target=out/(p.id+'.json');target.write_text(p.model_dump_json(),encoding='utf8')
            files.append({'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
            profiles.append(InstrumentSummary.model_validate(p.model_dump(include=set(InstrumentSummary.model_fields))).model_dump())
        if path.name in {'D2903891_012.nc','SR6903091_100.nc','glider-ru29.nc','ctd-station.csv'}:
            example=out/'examples'/path.name;example.parent.mkdir(exist_ok=True);shutil.copyfile(path,example)
            examples.append({'name':path.name,'format':parsed.format,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'source_url':url,'collection':collection})
        sources.append({'file':path.name,'source_url':url,'provider':provider,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)})
    # A real additional file in our documented CSV format, exported without inventing values.
    import csv,io
    argo=next(p for p in profiles if p['platform']=='2903891')
    p=json.loads((out/(argo['id']+'.json')).read_text(encoding='utf8'))
    columns=['profile_id','instrument','platform','time','latitude','longitude','pressure_dbar','pressure_qc','position_qc','time_qc','temperature_c','temperature_qc','salinity_psu','salinity_qc']
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(columns)
    for l in p['levels'][:20]:
        writer.writerow(['2903891-12','argo','2903891',l['time'],l['latitude'],l['longitude'],l['pressure_dbar'],l['coordinate_qc']['pressure'],l['coordinate_qc']['position'],l['coordinate_qc']['time'],l['readings']['temperature']['value'],l['readings']['temperature']['qc'],l['readings']['salinity']['value'],l['readings']['salinity']['qc']])
    example=out/'examples/argo-2903891-example.csv';example.write_text(stream.getvalue(),encoding='utf8')
    examples.append({'name':example.name,'format':'Depth Atlas CSV v1','bytes':example.stat().st_size,'sha256':hashlib.sha256(example.read_bytes()).hexdigest(),'source_url':p['source_url'],'collection':'Bay of Bengal · first 20 original levels, adjusted selections exported'})
    index={'schema_version':'2','profiles':profiles,'examples':examples,'files':files,'sources':sources,'limitations':['Only the Bay of Bengal collection shares the current model domain. Other collections are separate historical observation examples.','Selection does not establish a scientifically eligible model-observation match.','Glider salinity has inconsistent provider range metadata and remains inspect-only.']}
    (out/'index.json').write_text(json.dumps(index,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    print(json.dumps({'profiles':len(profiles),'types':sorted({p['instrument'] for p in profiles}),'examples':len(examples),'bytes':sum(p.stat().st_size for p in out.rglob('*') if p.is_file())}))

if __name__=='__main__':prepare()

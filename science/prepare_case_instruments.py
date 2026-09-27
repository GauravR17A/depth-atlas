"""Prepare an additional checked collection without mutating the original library."""
import argparse
import hashlib
import json
from pathlib import Path
from adapters.instruments import parse_instruments
from science.instruments import InstrumentSummary
from science.case_recipes import RECIPES

ROOT=Path(__file__).resolve().parents[1]

def prepare(case_id='arabian-sea-2024-01'):
    recipe=RECIPES[case_id]
    journal=json.loads((ROOT/recipe['raw']/'acquisition.json').read_text())
    out=ROOT/'casepacks/instruments-arabian-sea'
    out.mkdir(parents=True,exist_ok=True)
    profiles,files,sources=[],[],[]
    for item in journal['files']:
        if item['archive_kind']!='original_gdac_file':continue
        path=ROOT/item['path'];body=path.read_bytes()
        if hashlib.sha256(body).hexdigest()!=item['sha256']:raise ValueError('Original profile checksum mismatch.')
        result=parse_instruments(body,path.name,item['source_url'])
        for profile in result.profiles:
            profile.collection=recipe['name']+' \u00b7 January 2024'
            profile.metadata.update(provider='Argo GDAC / INCOIS DAC',acquired_date=journal['retrieved_at'][:10],source_url=item['source_url'])
            target=out/(profile.id+'.json');target.write_text(profile.model_dump_json(),encoding='utf-8')
            files.append(dict(name=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
            profiles.append(InstrumentSummary.model_validate(profile.model_dump(include=set(InstrumentSummary.model_fields))).model_dump())
        sources.append(dict(file=path.name,source_url=item['source_url'],provider='Argo GDAC / INCOIS DAC',sha256=item['sha256'],bytes=len(body)))
    index=dict(schema_version='2',profiles=profiles,examples=[],files=files,sources=sources,limitations=['Selected historical Arabian Sea profiles; model compatibility is checked per sample and variable.'])
    (out/'index.json').write_text(json.dumps(index,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps(dict(profiles=len(profiles),files=len(files)),indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',choices=['arabian-sea-2024-01'],default='arabian-sea-2024-01');prepare(parser.parse_args().case)

"""Freeze the independently prepared field and index packs into one identity."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(root=ROOT/'casepacks'/'climate'):
    from science.climate_contracts import METHOD
    records = {}
    for name in ('field-manifest.json', 'indices.json'):
        path = root/name
        body = path.read_bytes()
        data = json.loads(body)
        expected_schema = 'p13-indices-v1' if name == 'indices.json' else '1'
        if data.get('schema_version') != expected_schema:
            raise ValueError('Unsupported climate source pack schema.')
        records[name] = {'path':name,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}
    fields = json.loads((root/'field-manifest.json').read_text(encoding='utf-8'))
    indices = json.loads((root/'indices.json').read_text(encoding='utf-8'))
    if fields['event_years'] != [2013,2015,2022] or sorted(e['year'] for e in indices['events']) != fields['event_years']:
        raise ValueError('Field and index years must agree exactly.')
    if (fields['baseline']['start_year'],fields['baseline']['end_year'],fields['baseline']['months']) != (1991,2020,[9,10,11]):
        raise ValueError('Unexpected baseline or calendar window.')
    manifest={'schema_version':'1','method_version':METHOD,'sources':records,
              'event_ids':[f'son-{y}' for y in fields['event_years']],
              'case_ids':[f'pacific-godas-{y}-son' for y in fields['event_years']],
              'policy':'Pinned field and index files. Source changes require a new identity; old records are never silently migrated.'}
    manifest['workspace_cases']={}
    for case_id in manifest['case_ids']:
        case_path=root.parent/case_id/'manifest.json'
        library_path=root.parent/'instruments'/case_id/'index.json'
        manifest['workspace_cases'][case_id]={
            'model_manifest_sha256':hashlib.sha256(case_path.read_bytes()).hexdigest(),
            'observation_index_sha256':hashlib.sha256(library_path.read_bytes()).hexdigest(),
        }
    body=(json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
    (root/'manifest.json').write_bytes(body)
    return {'manifest_sha256':hashlib.sha256(body).hexdigest(),'sources':records}


if __name__=='__main__':
    print(json.dumps(prepare(),indent=2))

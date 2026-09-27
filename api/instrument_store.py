"""Checked, immutable observation library. Untrusted IDs never become paths."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from science.contracts import UnsupportedData
from science.instruments import InstrumentProfile
from api.case_store import PACIFIC_CASE_IDS


class InstrumentStore:
    def __init__(self,root:Path): self.root=root

    @lru_cache(maxsize=8)
    def index(self,case_id='bay-bengal-2024-01'):
        if case_id in PACIFIC_CASE_IDS:
            path=self.root/case_id/'index.json'
            if not path.is_file():
                return {'schema_version':'2','profiles':[],'examples':[],'files':[],'sources':[], 'limitations':['No checked observation library is supplied for this Pacific case. No other case profiles are substituted.']}
            return json.loads(path.read_text(encoding='utf8'))
        if case_id=='arabian-sea-2024-01':
            base=self.index()
            extra=self.root.parent/'instruments-arabian-sea'/'index.json'
            if not extra.is_file(): return base
            addition=json.loads(extra.read_text(encoding='utf8'))
            return {**base,**{k:base.get(k,[])+addition.get(k,[]) for k in ['profiles','examples','files','sources']},'limitations':['Model overlap depends on the selected case bounds and dates. Matching applies source, QC, time, distance and depth gates.','Separate historical collections do not extend model coverage.','Glider salinity has inconsistent provider range metadata and remains inspect-only.']}
        path=self.root/'index.json'
        if not path.exists(): return {'schema_version':'2','profiles':[],'examples':[],'files':[],'limitations':['No observation library configured.']}
        return json.loads(path.read_text(encoding='utf8'))

    def catalog(self,case_id='bay-bengal-2024-01'):
        result={k:v for k,v in self.index(case_id).items() if k in {'schema_version','profiles','examples','limitations'}}
        result['examples']=result.get('examples',[])+self.import_examples()
        return result

    def import_examples(self):
        path=self.root/'import-examples.json'
        return json.loads(path.read_text(encoding='utf8'))['examples'] if path.is_file() else []

    @lru_cache(maxsize=16)
    def read(self,profile_id):
        index=self.index()
        directory=self.root
        known=next((x for x in index['profiles'] if x['id']==profile_id),None)
        if not known:
            index=self.index('arabian-sea-2024-01')
            known=next((x for x in index['profiles'] if x['id']==profile_id),None)
            directory=self.root.parent/'instruments-arabian-sea'
        if not known:
            for case_id in PACIFIC_CASE_IDS:
                index=self.index(case_id)
                known=next((x for x in index['profiles'] if x['id']==profile_id),None)
                if known:
                    directory=self.root/case_id
                    break
        if not known: raise UnsupportedData('profile_not_found','This profile is not in the observation library.')
        name=known['id']+'.json';record=next(x for x in index['files'] if x['name']==name)
        body=(directory/name).read_bytes()
        if hashlib.sha256(body).hexdigest()!=record['sha256']: raise UnsupportedData('case_integrity_error','Observation failed its source integrity check.')
        return InstrumentProfile.model_validate_json(body)

    def example(self,name):
        record=next((x for x in self.catalog()['examples'] if x['name']==name),None)
        if not record: raise UnsupportedData('profile_not_found','This example file is not available.')
        path=self.root/'examples'/record['name']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']: raise UnsupportedData('case_integrity_error','Example failed its integrity check.')
        return path

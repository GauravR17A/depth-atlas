"""Checked historical monthly fields and versioned ENSO/IOD context."""
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

from science.climate import METHODS, CAVEATS, ordered_mean, finite_list, signed_difference, section_result, common_scale, profile_from_section
from science.climate_contracts import ClimateQuery, METHOD
from science.contracts import UnsupportedData


class ClimateStore:
    def __init__(self,cases,instruments):
        self.cases,self.instruments=cases,instruments
        self.root=cases.root/'climate'

    @lru_cache(maxsize=1)
    def manifest(self):
        path=self.root/'manifest.json'
        if not path.is_file():
            raise UnsupportedData('climate_source_unavailable','The checked historical climate pack is unavailable. No substitute fields are used.')
        body=path.read_bytes(); manifest=json.loads(body)
        if manifest.get('schema_version')!='1' or manifest.get('method_version')!=METHOD:
            raise UnsupportedData('case_integrity_error','The climate source pack does not match the declared method.')
        return manifest,hashlib.sha256(body).hexdigest()

    def checked_bytes(self,record):
        path=(self.root/record['path']).resolve()
        if self.root.resolve() not in path.parents:
            raise UnsupportedData('case_integrity_error','A climate source path is invalid.')
        try: body=path.read_bytes()
        except OSError as exc:
            raise UnsupportedData('climate_source_unavailable','A checked climate source file is unavailable.') from exc
        if hashlib.sha256(body).hexdigest()!=record['sha256'] or len(body)!=record['bytes']:
            raise UnsupportedData('case_integrity_error','A climate source failed its original fingerprint check.')
        return body

    @lru_cache(maxsize=2)
    def source(self,name):
        manifest,_=self.manifest()
        return json.loads(self.checked_bytes(manifest['sources'][name]))

    def event(self,event_id):
        event=next((e for e in self.source('indices.json')['events'] if e['event_id']==event_id),None)
        if not event:
            raise UnsupportedData('unsupported_climate_event','Choose a supported historical climate event.')
        return event

    @staticmethod
    def case_id(event): return f"pacific-godas-{event['year']}-son"

    def checked_case(self,case_id):
        combined,_=self.manifest()
        expected=combined.get('workspace_cases',{}).get(case_id)
        model,digest=self.cases.require(case_id)
        index_path=self.instruments.root/case_id/'index.json'
        if not expected or digest!=expected['model_manifest_sha256'] or not index_path.is_file() or hashlib.sha256(index_path.read_bytes()).hexdigest()!=expected['observation_index_sha256']:
            raise UnsupportedData('case_integrity_error','A shared Pacific case or observation library differs from the pinned climate source identity.')
        return model,digest

    @lru_cache(maxsize=15)
    def array(self,role,year,month):
        fields=self.source('field-manifest.json')
        record=next((r for r in fields['files'] if r['role']==role and r.get('year')==year and r['month']==month),None)
        if record is None:
            raise UnsupportedData('incomplete_climate_window','The requested climate month or baseline is not supplied.')
        if record['dtype'] not in {'<f8','<u2'}:
            raise UnsupportedData('case_integrity_error','Unexpected climate array encoding.')
        values=np.frombuffer(gzip.decompress(self.checked_bytes(record)),dtype=record['dtype'])
        coords=fields['coordinates']
        shape=(len(coords['depth_m']),len(coords['latitude']),len(coords['longitude']))
        if list(shape)!=record['shape'] or values.size!=np.prod(shape):
            raise UnsupportedData('case_integrity_error','Climate array dimensions do not match the source grid.')
        values=values.reshape(shape)
        if role=='baseline':
            counts=self.array('baseline_count',None,month)
            if np.any(np.isfinite(values)!=(counts==30)):
                raise UnsupportedData('case_integrity_error','The climate baseline does not meet its declared complete-year policy.')
        return values

    def catalog(self):
        fields,indices=self.source('field-manifest.json'),self.source('indices.json')
        events=[{**event,'case_id':self.case_id(event)} for event in indices['events']]
        for event in events: self.checked_case(event['case_id'])
        coords=fields['coordinates']
        return dict(schema_version='1',method_version=METHOD,climate_manifest_sha256=self.manifest()[1],
                    baseline=fields['baseline'],field_source=fields['source'],
                    index_definitions=indices['definitions'],index_sources=indices['sources'],events=events,
                    coordinates=dict(depth_m=coords['depth_m'],latitude=coords['latitude'],
                                     longitude=[x for x in coords['longitude'] if 140.5<=x<=279.5]),
                    periods=[dict(id='SON',label='September to November'),dict(id='09',label='September'),dict(id='10',label='October'),dict(id='11',label='November')],
                    default_query=ClimateQuery().model_dump(),methods=METHODS,caveats=CAVEATS)

    def analyse(self,query): return self._analyse(query.model_dump_json())

    @lru_cache(maxsize=10)
    def _analyse(self,query_json):
        query=ClimateQuery.model_validate_json(query_json)
        fields,indices=self.source('field-manifest.json'),self.source('indices.json')
        coords=fields['coordinates']
        months=[9,10,11] if query.period=='SON' else [int(query.period)]
        baseline=ordered_mean([self.array('baseline',None,m) for m in months])
        panels,observations=[],[]
        for event_id in (query.event_id,query.reference_event_id):
            event=self.event(event_id); case_id=self.case_id(event)
            model,model_sha=self.checked_case(case_id)
            values=ordered_mean([self.array('event',event['year'],m) for m in months])
            if model.coordinates.depth_m!=coords['depth_m'] or model.coordinates.latitude!=coords['latitude']:
                raise UnsupportedData('incompatible_grid','The shared case and climate section coordinates differ.')
            pacific=section_result(values,baseline,coords['latitude'],coords['longitude'],coords['depth_m'],140.5,279.5)
            indian=section_result(values,baseline,coords['latitude'],coords['longitude'],coords['depth_m'],40.5,109.5)
            if model.coordinates.longitude!=pacific['longitude']:
                raise UnsupportedData('incompatible_grid','The shared Pacific case and climate source longitudes differ.')
            if query.depth_index>=len(coords['depth_m']):
                raise UnsupportedData('invalid_selection','Choose an available native climate depth.')
            # The same source subset must drive both the workspace and the lab.
            for month in months:
                time_index=month-9
                native=np.asarray(self.cases._read_array(case_id,'analytical','temperature',time_index)).reshape(model.representations['analytical']['shape'])
                source=self.array('event',event['year'],month)[:,:,pacific['longitude_source_indices']]
                if not np.array_equal(native,source,equal_nan=True):
                    raise UnsupportedData('case_integrity_error','The shared Pacific case differs from its pinned climate source.')
            profile=profile_from_section(pacific,query.longitude_index)
            year=event['year']
            panels.append(dict(event={**event,'case_id':case_id},case_id=case_id,model_manifest_sha256=model_sha,
                               period_start=f'{year}-{months[0]:02d}-01T00:00:00Z',
                               period_end_exclusive=f'{year}-{months[-1]+1:02d}-01T00:00:00Z',
                               pacific=pacific,indian=indian,profile=profile))
            profiles=[]
            for item in self.instruments.catalog(case_id)['profiles']:
                if item['time'][:7] not in {f'{year}-{m:02d}' for m in months}: continue
                p=self.instruments.read(item['id'])
                profiles.append(dict(id=p.id,title=p.title,instrument=p.instrument,platform=p.platform,time=p.time,
                                     latitude=p.latitude,longitude=p.longitude,source_url=p.source_url,
                                     source_sha256=p.source_sha256,
                                     note='Original profile during this calendar window. Inspect its actual location and source QC; no direct monthly potential-temperature residual is calculated.'))
            observations.append(dict(event_id=event_id,case_id=case_id,profiles=profiles))
        difference={}; scales={}
        for basin in ('pacific','indian'):
            a,b=panels[0][basin],panels[1][basin]
            values=signed_difference(np.asarray(a['potential_temperature_c'],dtype=float),np.asarray(b['potential_temperature_c'],dtype=float))
            geometry={k:a[k] for k in ('latitude','longitude','depth_m','shape','dimensions')}
            difference[basin]={**geometry,'values_c':finite_list(values),'meaning':'Selected event minus reference event; identical native coordinates and calendar window.'}
            scales[basin]=dict(temperature=common_scale([a,b],'potential_temperature_c'),
                              anomaly=common_scale([a,b],'anomaly_c',True),
                              difference=common_scale([difference[basin]],'values_c',True))
        difference['profile_c']=finite_list(signed_difference(np.asarray(panels[0]['profile']['potential_temperature_c'],dtype=float),np.asarray(panels[1]['profile']['potential_temperature_c'],dtype=float)))
        point=dict(latitude=panels[0]['profile']['latitude'],longitude=panels[0]['profile']['longitude'],depth_m=coords['depth_m'][query.depth_index],
                   longitude_index=query.longitude_index,depth_index=query.depth_index)
        for key,panel in zip(('selected','reference'),panels):
            point[key]={field:panel['profile'][field][query.depth_index] for field in ('potential_temperature_c','baseline_c','anomaly_c')}
        point['difference_c']=difference['profile_c'][query.depth_index]
        return dict(schema_version='1',kind='derived',method_version=METHOD,case_id=panels[0]['case_id'],
                    query=query.model_dump(),climate_manifest_sha256=self.manifest()[1],model_manifest_sha256=panels[0]['model_manifest_sha256'],
                    baseline=fields['baseline'],field_source=fields['source'],index_definitions=indices['definitions'],
                    events=[p['event'] for p in panels],period=dict(id=query.period,label={'SON':'September to November','09':'September','10':'October','11':'November'}[query.period],months=months,aggregation='equal_weight_complete_month_mean'),
                    panels=panels,difference=difference,scales=scales,selected_point=point,observations=observations,methods=METHODS,caveats=CAVEATS)

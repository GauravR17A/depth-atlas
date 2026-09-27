"""Stateless capture/replay. Durable records live with the user, never /tmp."""
import csv
from datetime import datetime, timezone, timedelta
from html import escape
import io
import json
import math
import platform
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
from api.version import APP_VERSION
from science.contracts import UnsupportedData
from science.evidence_contracts import METHOD_VERSION as COMPARISON_METHOD
from science.feature_contracts import METHOD as FEATURE_METHOD, RegionQuery
from science.investigations import METHOD, HASH_METHOD, fingerprint, ReplayRequest
from science.products import PRODUCTS
from science.expedition_contracts import METHOD as EXPEDITION_METHOD
from science.drift_contracts import METHOD as DRIFT_METHOD
from science.heat_contracts import METHOD as HEAT_METHOD
from science.climate_contracts import METHOD as CLIMATE_METHOD
from science.evolution_contracts import METHOD as EVOLUTION_METHOD
from science.blackout_contracts import METHOD as BLACKOUT_METHOD


class InvestigationStore:
    def __init__(self, cases, instruments, evidence, features, expeditions=None, drifts=None, heats=None, climates=None, evolutions=None, blackouts=None):
        self.cases, self.instruments, self.evidence, self.features = cases, instruments, evidence, features
        from api.expedition_store import ExpeditionStore
        self.expeditions = expeditions or ExpeditionStore(cases)
        from api.drift_store import DriftStore
        self.drifts = drifts or DriftStore(cases)
        from api.heat_store import HeatStore
        self.heats = heats or HeatStore(cases, instruments)
        from api.climate_store import ClimateStore
        self.climates = climates or ClimateStore(cases,instruments)
        from api.evolution_store import EvolutionStore
        from api.blackout_store import BlackoutStore
        self.evolutions = evolutions or EvolutionStore(features)
        self.blackouts = blackouts or BlackoutStore(evidence)

    def sources(self, recipe):
        _, digest = self.cases.require(recipe.case_id)
        if recipe.mode == 'instrument' and recipe.profile_id not in {p['id'] for p in self.instruments.catalog(recipe.case_id)['profiles']}:
            raise UnsupportedData('profile_not_found','This profile is not in the selected case observation library. Choose its study case before saving.')
        imported = getattr(self, 'import_source', None)
        return dict(model_manifest_sha256=digest, observation_library_sha256=self.evidence.library_sha_for(recipe.case_id),
                    **(dict(import_context_sha256=self.instruments.context_sha, import_profiles_sha256=self.instruments.profiles_sha) if imported else {}),
                    **({'heat_manifest_sha256': self.heats.manifest()[1]} if recipe.mode == 'heat' else {}),
                    **({'climate_manifest_sha256': self.climates.manifest()[1]} if recipe.mode == 'climate' else {}),
                    methods=dict(replay=METHOD, fingerprint=HASH_METHOD, native='p02-native-float64-v1',
                                 instruments='p04-library-v2', comparison=COMPARISON_METHOD,
                                 **(dict(import_parser=imported.parser_version, imported='p16c-original-input-v1') if imported else {}),
                                 features=FEATURE_METHOD, kinetic_energy=PRODUCTS.get('horizontal_kinetic_energy').metadata.method_id,
                                 **({'expedition': EXPEDITION_METHOD} if recipe.mode == 'expedition' else {}),
                                 **({'drift': DRIFT_METHOD} if recipe.mode == 'drift' else {}),
                                 **({'heat': HEAT_METHOD} if recipe.mode == 'heat' else {}),
                                 **({'climate': CLIMATE_METHOD} if recipe.mode == 'climate' else {}),
                                 **({'evolution': EVOLUTION_METHOD} if recipe.mode == 'evolution' else {}),
                                 **({'blackout': BLACKOUT_METHOD} if recipe.mode == 'blackout' else {})))

    def calculate(self, recipe):
        manifest, _ = self.cases.require(recipe.case_id)
        modules = []
        def add(module, method, parameters, output, seed=None):
            data = output.model_dump(mode='json') if hasattr(output, 'model_dump') else output
            modules.append(dict(module=module, method_version=method, parameters=parameters,
                                random_seed=seed, output=data, output_sha256=fingerprint(data)))
        if recipe.mode == 'ocean':
            c = manifest.coordinates
            x, y, z = recipe.point
            if x >= len(c.longitude) or y >= len(c.latitude) or z >= len(c.depth_m) or recipe.section_index >= len(manifest.display_coordinates.latitude):
                raise UnsupportedData('invalid_selection', 'The saved grid selection is outside the available source coordinates.')
            names = ['eastward_velocity', 'northward_velocity'] if recipe.variable == 'currents' else [recipe.variable]
            columns = [self.cases.subset(recipe.case_id, v, recipe.time_index, 'analytical', 'volume', None,
                        (c.longitude[x], c.latitude[y], c.longitude[x], c.latitude[y])).model_dump(mode='json') for v in names]
            speed = [math.hypot(a,b) if a is not None and b is not None else None for a,b in zip(columns[0]['values'],columns[1]['values'])] if recipe.variable == 'currents' else None
            add('native_profile', 'p02-native-float64-v1', dict(variable=recipe.variable,time_index=recipe.time_index,point=list(recipe.point)),
                dict(columns=columns, horizontal_speed=speed, selected_depth_m=c.depth_m[z], selected_values=[p['values'][z] for p in columns]))
        elif recipe.mode == 'comparison':
            result = self.evidence.comparison(recipe.case_id, recipe.profile_id, recipe.settings)
            if recipe.sample_index >= len(result.rows): raise UnsupportedData('invalid_selection','The saved observation sample is unavailable.')
            add('comparison', COMPARISON_METHOD, dict(profile_id=recipe.profile_id, settings=recipe.settings.model_dump()), result)
            add('coverage', COMPARISON_METHOD, recipe.settings.model_dump(), self.evidence.coverage(recipe.case_id, recipe.settings))
            if recipe.baseline:
                b = recipe.baseline
                add('reference_comparison', COMPARISON_METHOD, b.model_dump(), self.evidence.comparison(recipe.case_id,b.profile_id,b.settings))
        elif recipe.mode == 'features':
            search = self.features.search(recipe.case_id,recipe.query)
            add('regions', FEATURE_METHOD, recipe.query.model_dump(), search)
            if recipe.selected_region:
                if recipe.selected_region not in {r['id'] for r in search['regions']}:
                    raise UnsupportedData('invalid_selection','The saved region is not in the returned query list.')
                add('region_boundary', FEATURE_METHOD, dict(region_id=recipe.selected_region),
                    self.features.region(recipe.case_id,RegionQuery(query=recipe.query,region_id=recipe.selected_region)))
            if recipe.section:
                section = self.features.section(recipe.case_id,recipe.section)
                if recipe.section_pick >= max(1,len(section['values'])): raise UnsupportedData('invalid_selection','The saved section sample is unavailable.')
                add('section', FEATURE_METHOD, recipe.section.model_dump(), section)
        elif recipe.mode == 'evolution':
            result = self.evolutions.run(recipe.case_id, recipe.query)
            if recipe.selected_node and not any(recipe.selected_node == node['node_id'] for frame in result['frames'] for node in frame['regions']):
                raise UnsupportedData('invalid_selection', 'The selected evolution node is not in the applied result.')
            add('evolution_analysis', EVOLUTION_METHOD, recipe.query.model_dump(mode='json'), result)
        elif recipe.mode == 'blackout':
            add('blackout_analysis', BLACKOUT_METHOD, recipe.query.model_dump(mode='json'), self.blackouts.run(recipe.case_id, recipe.query))
        elif recipe.mode == 'climate':
            climate_result=self.climates.analyse(recipe.query)
            if climate_result['case_id']!=recipe.case_id:
                raise UnsupportedData('invalid_selection','Save the applied climate event with its actual Pacific source case.')
            add('climate_analysis',CLIMATE_METHOD,recipe.query.model_dump(mode='json'),climate_result)
        elif recipe.mode == 'heat':
            heat_result = self.heats.analyse(recipe.case_id, recipe.query)
            if heat_result['query'] != recipe.query.model_dump(mode='json'):
                raise UnsupportedData('invalid_selection', 'Calculate and apply the current Heat & Depth selection before saving it.')
            add('heat_analysis', HEAT_METHOD, recipe.query.model_dump(mode='json'), heat_result)
        elif recipe.mode == 'drift':
            add('drift_run', DRIFT_METHOD, recipe.query.model_dump(mode='json'), self.drifts.run(recipe.case_id,recipe.query), recipe.query.seed)
            if recipe.comparison:
                add('reference_drift_run', DRIFT_METHOD, recipe.comparison.model_dump(mode='json'), self.drifts.run(recipe.case_id,recipe.comparison), recipe.comparison.seed)
        elif recipe.mode == 'expedition':
            add('station_plan', EXPEDITION_METHOD, recipe.query.model_dump(), self.expeditions.plan(recipe.case_id, recipe.query))
            if recipe.survey:
                add('virtual_survey', EXPEDITION_METHOD, recipe.survey.model_dump(), self.expeditions.survey(recipe.case_id, recipe.survey))
            if recipe.experiment:
                add('sampling_experiment', EXPEDITION_METHOD, recipe.query.model_dump(), self.expeditions.experiment(recipe.case_id, recipe.query), recipe.query.seed)
        else:
            profile = self.instruments.read(recipe.profile_id)
            if recipe.model_time_index is not None and recipe.model_time_index >= len(manifest.coordinates.times):
                raise UnsupportedData('invalid_selection', 'The saved model context timestamp is unavailable.')
            if recipe.variable not in profile.parameters or recipe.sample_index >= len(profile.levels):
                raise UnsupportedData('invalid_selection','The saved variable or sample is unavailable in this checked profile.')
            add('observation_profile','p16c-original-input-v1' if getattr(self, 'import_source', None) else 'p04-library-v2',dict(profile_id=recipe.profile_id,variable=recipe.variable),profile)
        return modules

    def capture(self, request):
        if request.import_source is not None and not getattr(self, 'import_source', None):
            from api.imported_store import imported_investigations
            return imported_investigations(self, request.import_source, request.recipe).capture(request)
        source = self.sources(request.recipe)
        if request.expected_model_sha256 and request.expected_model_sha256 != source['model_manifest_sha256']:
            raise UnsupportedData('source_mismatch','The source changed since this view loaded. Reload it before saving.')
        if request.expected_observation_library_sha256 and request.expected_observation_library_sha256 != source['observation_library_sha256']:
            raise UnsupportedData('source_mismatch', 'The observation library changed since this view loaded. Reload it before saving.')
        if request.expected_heat_manifest_sha256 and request.expected_heat_manifest_sha256 != source.get('heat_manifest_sha256'):
            raise UnsupportedData('source_mismatch','The daily SST source changed since this view loaded. Reload it before saving.')
        if request.expected_climate_manifest_sha256 and request.expected_climate_manifest_sha256 != source.get('climate_manifest_sha256'):
            raise UnsupportedData('source_mismatch','The climate fields or index snapshot changed since this view loaded. Reload it before saving.')
        if request.expected_profile_sha256 and self.instruments.read(request.recipe.profile_id).source_sha256 != request.expected_profile_sha256:
            raise UnsupportedData('source_mismatch','The observation source changed since this view loaded.')
        try:
            results=self.calculate(request.recipe)
        except OSError as exc:
            raise UnsupportedData('source_unavailable','A required checked source file is unavailable. No replacement or stored result has been substituted.') from exc
        return self.bundle(request.title,request.recipe,source,results)

    def bundle(self, title, recipe, sources, results):
        manifest,_ = self.cases.require(recipe.case_id)
        raw_recipe=recipe.model_dump(mode='json')
        result_sha=fingerprint(results)
        recipe_sha=fingerprint(dict(recipe=raw_recipe,sources=sources))
        recipe_times={recipe.time_index} if recipe.mode=='ocean' else {recipe.settings.time_index, *([recipe.baseline.settings.time_index] if recipe.baseline else [])} if recipe.mode=='comparison' else {recipe.query.time_index} if recipe.mode=='features' else set()
        if recipe.mode == 'expedition':
            recipe_times = {0, *([2, 4, 6] if recipe.experiment else []), *([recipe.survey.time_index] if recipe.survey else [])}
        if recipe.mode == 'drift':
            # Both point interpolation and swept-cell support need source brackets.
            recipe_times = set(range(len(manifest.coordinates.times)))
        if recipe.mode == 'heat':
            recipe_times = {recipe.query.model_time_index} if results[0]['output']['depth_profile'] else set()
        if recipe.mode == 'climate':
            recipe_times = {m-9 for m in results[0]['output']['period']['months']}
        if recipe.mode == 'evolution':
            recipe_times = {frame['time_index'] for frame in results[0]['output']['frames']}
        if recipe.mode == 'blackout':
            # Coverage also reports source-backed alternative eligible times.
            recipe_times = set(range(len(manifest.coordinates.times)))
        # Read-only source instructions and checksums, never credentials or local absolute paths.
        references=[s.model_dump(mode='json') for s in manifest.sources]
        selected_times = {manifest.coordinates.times[t] for t in recipe_times}
        references[0]['files'] = [record for record in references[0]['files']
                                  if record.get('time') in selected_times or
                                  (recipe.mode == 'blackout' and selected_times.intersection(record.get('timestamps', [])))]
        if recipe.mode == 'heat':
            heat_manifest, heat_sha = self.heats.manifest()
            references.append(dict(**heat_manifest['source'], heat_manifest_sha256=heat_sha,
                                   selected_location=self.heats.location(recipe.case_id, recipe.query.location_id),
                                   source_files=heat_manifest.get('source_files', []),
                                   instructions='The investigation retains the complete baseline curves, declared methods, selected-year daily values and event boundaries. The checked SST pack and acquisition scripts reproduce the full baseline.'))
        if recipe.mode == 'climate':
            fields=self.climates.source('field-manifest.json');indices=self.climates.source('indices.json')
            references.append(dict(title='Pinned climate fields and seasonal baseline',source_url=fields['source'].get('source_url',''),
                                   climate_manifest_sha256=self.climates.manifest()[1],source=fields['source'],
                                   baseline=fields['baseline'],source_files=fields.get('source_files',[]),
                                   instructions='The recorded acquisition and preparation scripts reproduce these monthly fields and the 30-year baseline. Retain original source values, masks and calendar windows.'))
            references.append(dict(title='Pinned official ENSO and IOD indices',source_url='https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/',
                                   snapshot_id=indices['snapshot_id'],sources=indices['sources'],definitions=indices['definitions'],
                                   selected_events=results[0]['output']['events']))
        observation_ids={recipe.profile_id} if recipe.mode in {'comparison','instrument'} else set()
        if recipe.mode=='comparison' and recipe.baseline: observation_ids.add(recipe.baseline.profile_id)
        if recipe.mode=='heat': observation_ids.update(p['id'] for p in results[0]['output']['observations'])
        if recipe.mode=='climate': observation_ids.update(p['id'] for group in results[0]['output']['observations'] for p in group['profiles'])
        if recipe.mode in {'evolution', 'blackout'}:
            observation_ids.update(p['id'] for p in self.instruments.catalog(recipe.case_id)['profiles'])
        for profile_id in sorted(observation_ids):
            p=self.instruments.read(profile_id)
            profile_case=recipe.case_id
            if recipe.mode=='climate':
                profile_case=next(group['case_id'] for group in results[0]['output']['observations'] if any(item['id']==profile_id for item in group['profiles']))
            references.append(dict(title=p.title,source_url=p.source_url,source_file=p.source_file,sha256=p.source_sha256,
                                   library_sources=self.instruments.index(profile_case).get('sources',[])))
        exchange=self.cases.root/'standards'/('manifest.json' if recipe.case_id=='bay-bengal-2024-01' else recipe.case_id+'.json')
        if exchange.exists():
            metadata=json.loads(exchange.read_text(encoding='utf-8'))
            references.append(dict(title='Native CF exchange download',source_url='https://depth-atlas-seifuku.vercel.app/data/'+metadata['file'],
                                   sha256=metadata['sha256'],bytes=metadata['bytes'],
                                   instructions='Download the native file through Use the data. Check this SHA-256 before reuse. Exact analytical REST values are available through /api/cases/'+recipe.case_id+'/subset; retain the recipe variable, time and coordinates.',
                                   licence='The original HYCOM source terms and attribution above apply.'))
        descriptor=dict(schema_version='1',title=title,recipe=raw_recipe,sources=sources,expected_result_sha256=result_sha,expected_recipe_sha256=recipe_sha)
        imported = getattr(self, 'import_source', None)
        if imported:
            descriptor['import_source'] = imported.model_dump(mode='json')
        body=dict(schema_version='1',kind='ocean_investigation',created_at=datetime.now(timezone.utc).isoformat(),case=manifest.case.model_dump(mode='json'),
                  software=dict(app=APP_VERSION,python=platform.python_version(),numpy=np.__version__),
                  replay=descriptor,results=results,result_sha256=result_sha,references=references,
                  limitations=['Historical source data, not current conditions or an operational advisory.',
                    'Exact replay requires the same bundled sources and method versions. Hashes check consistency, not author identity or scientific truth.',
                    'Browser records can be removed by site-data clearing or storage eviction. Download an investigation file for a portable backup.',
                    'Camera orbit, transient animations, unsubmitted drafts and imported observation files are not part of this record.',
                    'Numeric missing values remain null in JSON and empty fields in CSV. Observation quality and exclusion reasons are retained.',
                    'Estimated region geometry and model-observation assimilation caveats remain those of the source modules.'])
        if imported:
            body['imported_profiles'] = [p.model_dump(mode='json') for p in self.instruments.profiles]
            body['limitations'][3] = 'The included original observation file, parser version and column mappings are retained. Camera orbit, transient animations and unsubmitted drafts are not retained.'
            body['limitations'].append('Saving and replay send the included file to the app service for request-only parsing. Share this file only if permitted by its source terms; checksums are not signatures or proof of authenticity.')
        body['document_sha256']=fingerprint(body)
        if imported and len(json.dumps(body, ensure_ascii=True, separators=(',', ':')).encode()) > 4_200_000:
            raise UnsupportedData('file_limits', 'This imported investigation exceeds the 4.2 MB hosted response budget. Use a smaller file or save one profile view without a comparison reference.')
        if len(json.dumps(body,ensure_ascii=True)) > 8_000_000:
            raise UnsupportedData('file_limits','This result exceeds the 8 MB investigation limit. Use a smaller section or simpler query.')
        return body

    def replay(self, request: ReplayRequest):
        if request.import_source is not None and not getattr(self, 'import_source', None):
            from api.imported_store import imported_investigations
            return imported_investigations(self, request.import_source, request.recipe).replay(request)
        # Absent optional source families must not change old record identities.
        expected=request.sources.model_dump(exclude_none=True)
        if fingerprint(dict(recipe=request.recipe.model_dump(mode='json'),sources=expected)) != request.expected_recipe_sha256:
            raise UnsupportedData('recipe_mismatch','The investigation settings or source identities were changed. The saved result cannot be reused.')
        current=self.sources(request.recipe)
        if current['methods'] != expected['methods']:
            raise UnsupportedData('method_mismatch','This investigation uses a different scientific method version. Keep its exported record; automatic migration is not available.')
        if current != expected:
            raise UnsupportedData('source_mismatch','The required source version is unavailable. No replacement source or cached result has been substituted.')
        try:
            results=self.calculate(request.recipe)
        except OSError as exc:
            raise UnsupportedData('source_unavailable','A required checked source file is unavailable. No replacement or stored result has been substituted.') from exc
        if fingerprint(results) != request.expected_result_sha256:
            raise UnsupportedData('result_mismatch','Recalculated values differ from the saved evidence. The workspace has not been restored.')
        return self.bundle(request.title,request.recipe,current,results)


def csv_text(headers, rows):
    buffer=io.StringIO(newline='');writer=csv.writer(buffer);writer.writerow(headers)
    for row in rows:
        # Preserve real negative numeric values; protect only untrusted text cells.
        writer.writerow([("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')) else v) if v is not None else '' for v in row])
    return buffer.getvalue()


def numerical_files(bundle):
    files={}
    for module in bundle['results']:
        name=module['module'];out=module['output']
        if name in {'evolution_analysis', 'blackout_analysis'}:
            from api.p14_exports import tables
            files.update(tables(out, csv_text))
        elif name=='native_profile':
            cols=out['columns'];n=len(cols[0]['depth_m'])
            headers=['model_time_utc','longitude_deg_east','latitude_deg_north','depth_m']+[c['variable']+' ['+c['units']+']' for c in cols]+(['horizontal_speed [m/s]'] if out['horizontal_speed'] is not None else [])
            files['native-profile.csv']=csv_text(headers,[[cols[0]['time'],cols[0]['longitude'][0],cols[0]['latitude'][0],cols[0]['depth_m'][i],*[c['values'][i] for c in cols],*([out['horizontal_speed'][i]] if out['horizontal_speed'] is not None else [])] for i in range(n)])
        elif name in {'comparison','reference_comparison'}:
            headers=['profile_id','variable','units','model_time_utc',*out['rows'][0].keys()] if out['rows'] else ['profile_id']
            files['paired-values.csv' if name=='comparison' else 'reference-paired-values.csv']=csv_text(headers,[[out['profile']['id'],out['settings']['variable'],out['units'],out['model_time'],*r.values()] for r in out['rows']])
        elif name=='regions':
            files['regions.csv']=csv_text(['region_id','variable','units','model_time_utc','native_cells','estimated_volume_km3','depth_min_m','depth_max_m','min','max','mean','volume_weighted_mean','eligible_samples','eligible_profiles','membership_sha256'],[[r['id'],out['query']['variable'],out['units'],out['model_time'],r['cell_count'],r['estimated_volume_km3'],r['center_bounds']['depth_min_m'],r['center_bounds']['depth_max_m'],r['min'],r['max'],r['mean'],r['volume_weighted_mean'],r['eligible_samples'],r['eligible_profiles'],r['membership_sha256']] for r in out['regions']])
        elif name=='section':
            nx=out['shape'][1]
            files['section.csv']=csv_text(['model_time_utc','variable','units','station_index','distance_km','requested_longitude','requested_latitude','model_longitude','model_latitude','offset_km','depth_m','value','region_id'],[[out['model_time'],out['query']['variable'],out['units'],i%nx,s['distance_km'],s['longitude'],s['latitude'],s['model_longitude'],s['model_latitude'],s['offset_km'],out['depth_m'][i//nx],v,out['region_ids'][i]] for i,v in enumerate(out['values']) for s in [out['stations'][i%nx]]])
        elif name=='observation_profile':
            var=module['parameters']['variable'];p=out['parameters'][var]
            files['observation-profile.csv']=csv_text(['profile_id','variable','units','source_index','time_utc','longitude','latitude','depth_m','value','accepted','qc','exclusion_reason'],[[out['id'],var,p['units'],r['index'],r['time'],r['longitude'],r['latitude'],r['depth_m'],r['readings'][var]['value'],r['readings'][var]['accepted'],r['readings'][var]['qc'],r['readings'][var].get('reason','')] for r in out['levels']])
        elif name == 'climate_analysis':
            metadata=['method_version','climate_manifest_sha256','event_id','reference_event_id','period','baseline_start_year','baseline_end_year']
            meta=[out['method_version'],out['climate_manifest_sha256'],out['query']['event_id'],out['query']['reference_event_id'],out['query']['period'],out['baseline']['start_year'],out['baseline']['end_year']]
            rows=[]
            for panel in out['panels']:
                for basin in ('pacific','indian'):
                    section=panel[basin];nz,nx=section['shape']
                    for z in range(nz):
                        for x in range(nx):
                            i=z*nx+x
                            rows.append([*meta,panel['event']['event_id'],panel['case_id'],panel['period_start'],panel['period_end_exclusive'],basin,section['longitude'][x],section['latitude'],section['depth_m'][z],section['potential_temperature_c'][i],section['baseline_c'][i],section['anomaly_c'][i]])
            files['climate-sections.csv']=csv_text([*metadata,'panel_event_id','case_id','period_start_utc','period_end_exclusive_utc','basin','longitude_deg_east_0_360','latitude_deg_north','depth_m','potential_temperature_c','baseline_potential_temperature_c','anomaly_c'],rows)
            rows=[]
            for basin in ('pacific','indian'):
                section=out['difference'][basin];nz,nx=section['shape']
                rows.extend([*meta,basin,section['longitude'][x],section['latitude'],section['depth_m'][z],section['values_c'][z*nx+x]] for z in range(nz) for x in range(nx))
            files['climate-difference.csv']=csv_text([*metadata,'basin','longitude_deg_east_0_360','latitude_deg_north','depth_m','selected_minus_reference_c'],rows)
            rows=[]
            for panel in out['panels']:
                p=panel['profile']
                rows.extend([*meta,panel['event']['event_id'],p['longitude'],p['latitude'],depth,p['potential_temperature_c'][z],p['baseline_c'][z],p['anomaly_c'][z]] for z,depth in enumerate(p['depth_m']))
            files['climate-profiles.csv']=csv_text([*metadata,'panel_event_id','longitude_deg_east_0_360','latitude_deg_north','depth_m','potential_temperature_c','baseline_potential_temperature_c','anomaly_c'],rows)
            rows=[]
            for event in out['events']:
                for context in event['monthly_context']:
                    rows.append([*meta,event['event_id'],event['enso']['classification'],event['enso']['index_id'],event['enso']['value_c'],event['iod']['classification'],event['iod']['classification_basis'],event['iod']['index_id'],event['iod']['seasonal_dmi_c'],context['month'],context['centered_season'],context['roni_v6_c'],context['oni_v5_c'],context['oni_v6_c'],context['cpc_dmi_v6_c']])
            files['climate-index-context.csv']=csv_text([*metadata,'panel_event_id','enso_classification','enso_index_id','son_enso_index_c','iod_episode_label','iod_label_basis','dmi_index_id','son_dmi_c','center_month','centered_three_month_season','roni_v6_c','oni_v5_c','oni_v6_c','cpc_dmi_v6_c'],rows)
            p=out['selected_point']
            files['climate-selected-point.csv']=csv_text([*metadata,'longitude_deg_east_0_360','latitude_deg_north','depth_m','selected_potential_temperature_c','reference_potential_temperature_c','selected_anomaly_c','reference_anomaly_c','selected_minus_reference_c'],[[*meta,p['longitude'],p['latitude'],p['depth_m'],p['selected']['potential_temperature_c'],p['reference']['potential_temperature_c'],p['selected']['anomaly_c'],p['reference']['anomaly_c'],p['difference_c']]])
        elif name == 'heat_analysis':
            metadata=['method_version','case_id','location_id','longitude_deg_east','latitude_deg_north','heat_manifest_sha256','baseline_start_year','baseline_end_year']
            meta=[out['method_version'],out['case_id'],out['location']['id'],out['location']['longitude'],out['location']['latitude'],out['heat_manifest_sha256'],*out['baseline']['baseline_period']]
            fields=['date','sst_c','seasonal_mean_c','threshold_c','anomaly_c','exceeds_threshold','event_id']
            files['heat-surface-series.csv']=csv_text([*metadata,*fields],[[*meta,*[row[k] for k in fields]] for row in out['series']])
            event_fields=['id','start','end','peak_date','duration_days','exceedance_days','bridged_days','mean_intensity_c','max_intensity_c','cumulative_intensity_c_days','left_boundary_unknown','right_boundary_unknown','complete_boundaries','depth_overlap']
            files['heat-events.csv']=csv_text([*metadata,*event_fields],[[*meta,*[row[k] for k in event_fields]] for row in out['events']])
            files['heat-climatology.csv']=csv_text([*metadata,'leap_calendar_day_1_based','seasonal_mean_c','threshold_c','unsmoothed_pool_count'],[[*meta,i+1,out['baseline']['seasonal_mean_c'][i],out['baseline']['threshold_c'][i],out['baseline']['pool_count'][i]] for i in range(366)])
            profile=out['depth_profile']
            if profile:
                native_headers=['method_version','model_manifest_sha256','model_time_utc','model_longitude_deg_east','model_latitude_deg_north','depth_limit_m']
                native_meta=[out['method_version'],out['model_manifest_sha256'],profile['model_time'],profile['longitude'],profile['latitude'],profile['depth_limit_m']]
                for filename, rows in [('heat-depth-profile.csv',profile['points']),('heat-depth-layers.csv',profile['layers'])]:
                    fields=list(rows[0]) if rows else ['status']
                    files[filename]=csv_text([*native_headers,*fields],[[*native_meta,*[row[k] for k in fields]] for row in rows])
                files['heat-depth-integral.csv']=csv_text([*native_headers,*profile['heat_content'].keys()],[[*native_meta,*profile['heat_content'].values()]])
                fields=list(profile['mixed_layer']['density'])
                files['heat-mixed-layer.csv']=csv_text([*native_headers,'criterion',*fields],[[*native_meta,name,*[value[k] for k in fields]] for name,value in profile['mixed_layer'].items()])
        elif name in {'drift_run','reference_drift_run'}:
            prefix='drift' if name=='drift_run' else 'reference-drift'
            metadata=['module','method_version','manifest_sha256','simulated','case_id','depth_m','start_time_utc','seed']
            meta=[name,out['method_version'],out['manifest_sha256'],True,out['case_id'],out['depth_m'],out['start_time'],out['query']['seed']]
            rows=[]
            for p in out['particles']:
                for point in p['points']:
                    stamp=(datetime.fromisoformat(out['start_time'].replace('Z','+00:00'))+timedelta(seconds=point['elapsed_seconds'])).isoformat().replace('+00:00','Z')
                    rows.append([*meta,p['id'],p['status'],point['elapsed_seconds'],stamp,point['longitude'],point['latitude']])
            files[prefix+'-trajectories.csv']=csv_text([*metadata,'particle_id','final_status','elapsed_seconds','sample_time_utc','longitude','latitude'],rows)
            fields=['id','release_longitude','release_latitude','status','stop_elapsed_seconds','stop_reason','distance_km','arrival_elapsed_seconds']
            files[prefix+'-particles.csv']=csv_text([*metadata,*fields],[[*meta,*[p[k] for k in fields]] for p in out['particles']])
        elif name in {'station_plan', 'virtual_survey', 'sampling_experiment'}:
            source_rows = out['stations'] if name == 'station_plan' else out['samples'] if name == 'virtual_survey' else out['runs']
            fields = list(source_rows[0]) if source_rows else ['status']
            filename = {'station_plan':'stations.csv', 'virtual_survey':'simulated-survey.csv', 'sampling_experiment':'reconstruction-benchmark.csv'}[name]
            files[filename] = csv_text(['module','method_version','manifest_sha256','simulated','case_id','variable','units','depth_m','prior_time','sample_time_utc',*fields],
                [[name,out['method_version'],out['manifest_sha256'],name in {'virtual_survey','sampling_experiment'},out['case_id'],out['variable'],out['units'],out['depth_m'],out['prior_time'],row.get('model_time',out.get('model_time',out['prior_time'])),
                  *[json.dumps(row.get(k),separators=(',',':')) if isinstance(row.get(k),(list,dict)) else row.get(k) for k in fields]] for row in source_rows])
    return files


def report_html(bundle):
    e=lambda v:escape(str(v),quote=True)
    recipe=bundle['replay']['recipe'];sections=[]
    for module in bundle['results']:
        out=module['output'];name=module['module'];summary={}
        if name=='evolution_analysis': summary=dict(method_version=out['method_version'], query=out['query'], **out['summary'])
        elif name=='blackout_analysis': summary=dict(method_version=out['method_version'], model_time=out['baseline']['model_time'], variable=out['query']['settings']['variable'], units=out['units'], original_eligible_samples=out['baseline']['matched_samples'], remaining_eligible_samples=out['modified']['matched_samples'], removed_profiles=out['excluded_profile_ids'], removed_eligible_samples=out['removed_eligible_samples'], original_metrics=out['baseline_metrics'], remaining_metrics=out['modified_metrics'], model_unchanged=out['model_unchanged'])
        elif name=='comparison' or name=='reference_comparison': summary=dict(model_time=out['model_time'],profile=out['profile']['platform'],units=out['units'],eligible_pairs=out['matched_count'],excluded=out['excluded_count'],**out['metrics'])
        elif name=='regions':summary=dict(model_time=out['model_time'],units=out['units'],qualifying_native_cells=out['qualified_cells'],connected_regions=out['total_regions'],returned_regions=out['returned_regions'])
        elif name=='region_boundary':summary=out['region']
        elif name=='section':summary=dict(model_time=out['model_time'],units=out['units'],stations=len(out['stations']),native_depths=len(out['depth_m']),start=out['start'],end=out['end'],eligible_observations=len(out['observations']))
        elif name=='native_profile':summary=dict(model_time=out['columns'][0]['time'],selected_depth_m=out['selected_depth_m'],selected_values=out['selected_values'],variables=[dict(variable=c['variable'],units=c['units']) for c in out['columns']])
        elif name=='observation_profile':summary=dict(profile=out['platform'],source_start=out['time'],source_end=out['time_end'],samples=out['samples'],variable=module['parameters']['variable'])
        elif name=='coverage':summary=dict(eligible_profiles=out['matched_profiles'],eligible_samples=out['matched_samples'],excluded_samples=out['excluded_samples'])
        elif name=='station_plan':summary=dict(prior_time=out['prior_time'],variable=out['variable'],units=out['units'],depth_m=out['depth_m'],candidate_count=out['candidate_count'],requested_budget=out['query']['budget'],selected_stations=len(out['stations']),fulfilled=out['fulfilled'],reason=out['reason'])
        elif name=='virtual_survey':summary=dict(model_time=out['model_time'],simulated=True,variable=out['variable'],units=out['units'],depth_m=out['depth_m'],samples=len(out['samples']),unique_columns=out['unique_columns'],start=out['query']['start'],end=out['query']['end'])
        elif name=='sampling_experiment':summary=dict(prior_time=out['prior_time'],held_out_times=out['held_out_times'],units=out['units'],evaluation_count=out['evaluation_count'],summary=out['summary'],random_seeds=out['random_seeds'])
        elif name in {'drift_run','reference_drift_run'}:summary=dict(simulated=True,start_time=out['start_time'],requested_end_time=out['end_time'],depth_m=out['depth_m'],integration_step_seconds=out['query']['dt_seconds'],**out['summary'])
        elif name=='climate_analysis':summary=dict(events=out['events'],calendar_window=out['period'],baseline=out['baseline'],selected_point=out['selected_point'],field_source=out['field_source'])
        elif name=='heat_analysis':summary=dict(location=out['location'],baseline_period=out['baseline']['baseline_period'],analysis_year=out['query']['year'],selected_event=out['selected_event'],depth_link=out['depth_link'],mixed_layer=out['depth_profile']['mixed_layer'] if out['depth_profile'] else None,column_potential_enthalpy=out['depth_profile']['heat_content'] if out['depth_profile'] else None)
        methods=out.get('methods',[])+out.get('caveats',[])+out.get('limitations',[])
        # Old result modules retain their exact fingerprints. This capability
        # sentence described the earlier UI, not a numerical method or QC rule.
        methods=['This result uses the bundled observation library. Imported files can now be compared in their own selected-file view.' if m.startswith('Comparisons currently use the checked observation library.') else m for m in methods]
        rows=''.join('<tr><th scope="row">'+e(k.replace('_',' ').capitalize())+'</th><td>'+e('Not calculated' if v is None else json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v)+'</td></tr>' for k,v in summary.items())
        sections.append(f'<section><h2>{e(name.replace("_"," ").capitalize())}</h2><table>{rows}</table><ul>'+''.join('<li>'+e(x)+'</li>' for x in methods)+f'</ul><details><summary>Output fingerprint</summary><p class="hash">SHA-256: {e(module["output_sha256"])}</p></details></section>')
    if recipe['mode']=='features':
        q=recipe['query'];condition=f"between {q['threshold']} and {q['upper_threshold']}" if q['operator']=='between' else f"{'at least' if q['operator']=='at_least' else 'at most'} {q['threshold']}"
        question=f"Find connected native samples with {q['variable'].replace('_',' ')} {condition} {q['units']}, from {q['depth_min_m']} to {q['depth_max_m']} metres. Volume is estimated from inferred coordinate bins."
    elif recipe['mode']=='comparison':
        q=recipe['settings'];question=f"Compare {q['variable']} in profile {recipe['profile_id']} with the selected native model snapshot. Matching uses a {q['time_window_hours']}-hour window on either side, a {q['distance_km']}-km column limit and a {q['max_vertical_gap_m']}-metre depth-gap limit. QC policy: {q['qc'].replace('_',' ')}."
    elif recipe['mode']=='ocean':question=f"Inspect {recipe['variable'].replace('_',' ')} at the selected native model point and throughout its depth profile. Display view: {recipe['view']}. Visual exaggeration does not alter the numerical values."
    elif recipe['mode']=='expedition':question='Plan virtual scalar measurements using the first historical snapshot. Simulate a route or compare prior-only sampling strategies on identical withheld grid points. Reconstruction errors do not establish forecast improvement.'
    elif recipe['mode']=='drift':question='Simulate fixed-depth passive tracers under supplied historical currents. Compare declared release settings and simulated target entries. Trajectories and arrival fractions are not observed tracks, navigable routes or real-world probabilities.'
    elif recipe['mode']=='climate':question='Compare selected historical ENSO seasons at the same native Pacific coordinates and calendar window. GODAS potential-temperature anomalies use the declared 1991-2020 baseline. Indian Ocean context and separate IOD episode labels do not establish causal attribution or a new climate forecast.'
    elif recipe['mode']=='heat':question='Detect historical surface marine heatwaves against the declared seasonal baseline at a fixed analysed SST grid point. Inspect available contemporaneous model depth context. A surface event does not establish a subsurface heatwave or explain its cause.'
    elif recipe['mode']=='evolution':question='Follow native threshold regions through available historical frames using an explicit shared-volume overlap rule. Inspect splits, merges, unresolved support and nearby threshold choices. Correspondence is not the transport path of the same water.'
    elif recipe['mode']=='blackout':question='Compare original evidence with the evidence remaining after selected profiles or groups are excluded. Source QC and model fields remain unchanged. The model has not been rerun, and changes in selected residual statistics do not establish forecast impact.'
    else:question=f"Inspect the original {recipe['variable'].replace('_',' ')} readings and quality flags in profile {recipe['profile_id']}. This is a source observation, not a model comparison."
    sources=''.join('<li><strong>'+e(r.get('title','Source record'))+'</strong><p>'+e(r.get('citation',r.get('source_file','')))+'<br>'+e(r.get('source_url',''))+'<br>'+e(r.get('licence','Retain the source attribution and terms in SOURCES.json and source-credits.txt.'))+'</p></li>' for r in bundle['references'])
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>'+e(bundle['replay']['title'])+'</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:920px;margin:32px auto;padding:0 24px;color:#172d36}h1,h2{line-height:1.2}section{border-top:1px solid #b7c8cd;margin-top:24px;padding-top:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f5f5;padding:16px;font-size:13px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #d4dfe1;padding:8px;overflow-wrap:anywhere}th{width:40%;font-weight:500}.hash{overflow-wrap:anywhere;font-size:12px}li{overflow-wrap:anywhere}summary{cursor:pointer}@media print{body{margin:0}section{break-inside:avoid}}</style><body><p>Depth Atlas / Historical investigation</p><h1>'+e(bundle['replay']['title'])+'</h1><p>Generated '+e(bundle['created_at'])+' · App '+e(bundle['software']['app'])+'</p><p>'+e(question)+'</p><p>Use your browser print command to save this report as PDF. The JSON record and CSV files retain exact values; this report is a readable summary.</p><details><summary>Complete applied settings</summary><pre>'+e(json.dumps(recipe,indent=2,ensure_ascii=False))+'</pre></details>'+''.join(sections)+'<section><h2>Sources and reproduction</h2><p>Open Depth Atlas, choose Saved, then Open investigation file. Replaying recalculates against the pinned sources and checks result fingerprints. Unsupported source or method versions stop replay.</p><ul>'+sources+'</ul><details><summary>Retrieval instructions and source checksums</summary><pre>'+e(json.dumps(bundle['references'],indent=2,ensure_ascii=False))+'</pre></details><p class="hash">Result SHA-256: '+e(bundle['result_sha256'])+'</p><h2>Limits</h2><ul>'+''.join('<li>'+e(x)+'</li>' for x in bundle['limitations'])+'</ul></section></body></html>'


def export_bundle(bundle, format):
    files=numerical_files(bundle)
    imported = bundle['replay'].get('import_source')
    if format=='html':return report_html(bundle).encode('utf-8'),'text/html; charset=utf-8','ocean-investigation-report.html'
    if format=='csv':
        primary=next((n for n in ['evolution-regions.csv','blackout-coverage.csv','climate-sections.csv','heat-surface-series.csv','drift-trajectories.csv','reconstruction-benchmark.csv','simulated-survey.csv','stations.csv','paired-values.csv','section.csv','regions.csv','native-profile.csv','observation-profile.csv'] if n in files))
        return files[primary].encode('utf-8'),'text/csv; charset=utf-8',primary
    output=io.BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        archive.writestr('investigation.json',json.dumps(bundle,indent=None if imported else 2,separators=(',', ':') if imported else None,ensure_ascii=False,allow_nan=False))
        archive.writestr('settings.json',json.dumps(bundle['replay'],indent=2,ensure_ascii=False))
        archive.writestr('report.html',report_html(bundle))
        for name,body in files.items():archive.writestr(name,body)
        archive.writestr('SOURCES.json',json.dumps(bundle['references'],indent=2,ensure_ascii=False))
        imported = bundle['replay'].get('import_source')
        if imported:
            from science.imported import ImportedSource
            source = ImportedSource.model_validate(imported)
            archive.writestr('original-observation/' + source.filename, source.original_bytes())
        from pathlib import Path
        credits=Path(__file__).resolve().parents[1]/'web/public/third-party-notices.txt'
        if not credits.exists(): credits=Path(__file__).resolve().parents[1]/'public/third-party-notices.txt'
        try:
            credit_text=credits.read_text(encoding='utf-8')
        except OSError as exc:
            raise UnsupportedData('export_unavailable','The required source credits are unavailable. The evidence ZIP was not created. Try again after the service is restored.') from exc
        archive.writestr('source-credits.txt',credit_text)
        archive.writestr('README.txt','Depth Atlas investigation\nOpen investigation.json through Saved > Open investigation file. settings.json is a replay recipe, not a standalone saved-results record.\nreport.html opens without network or scripts and can be printed to PDF. CSV retains unrounded numerical values; empty numeric fields mean missing or not calculated, never zero. Paired rows include eligibility and exclusion reasons.\n'+('This ZIP includes your original uploaded observation file. Share only where you have permission. The model remains a pinned external dependency; source and parser/method mismatches stop replay.\n' if imported else 'Only selected public-source subsets and computed outputs are included, not private uploads or a complete ocean dataset.\n')+'Retain SOURCES.json and the method limitations when sharing. No scientific endorsement or operational forecast skill is claimed.\n')
    return output.getvalue(),'application/zip','ocean-investigation.zip'

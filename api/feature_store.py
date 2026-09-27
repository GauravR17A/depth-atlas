"""Immutable native results, bounded response geometry and eligible evidence."""
from bisect import bisect_right
from collections import defaultdict
from functools import lru_cache
import numpy as np
from science.contracts import UnsupportedData
from science.evidence_contracts import MatchSettings
from science.feature_contracts import FeatureQuery, METHOD
from science.features import analyze, boundary_faces, sample_section, distances_km, midpoint_edges, METHODS, LIMITATIONS


class FeatureStore:
    def __init__(self,cases,instruments,evidence):
        self.cases,self.instruments,self.evidence = cases,instruments,evidence

    def validate(self,case_id,query):
        manifest,digest = self.cases.require(case_id)
        if query.variable == 'horizontal_kinetic_energy':
            from science.products import PRODUCTS
            units = PRODUCTS.get(query.variable).metadata.units
        else:
            spec = next((v for v in manifest.variables if v.id == query.variable),None)
            if spec is None: raise UnsupportedData('unsupported_variable','This case does not supply the requested variable.')
            units = spec.units
        if query.units != units: raise UnsupportedData('incompatible_units',f'This variable requires units {units}. No automatic unit conversion is applied.')
        if query.time_index >= len(manifest.coordinates.times): raise UnsupportedData('unsupported_time','Choose an available source snapshot.')
        return manifest,digest

    @lru_cache(maxsize=4)
    def accepted_rows(self,case_id,variable,time_index):
        if variable not in {'temperature','salinity'}: return []
        settings = MatchSettings(variable=variable,time_index=time_index)
        accepted = []
        for item in self.instruments.catalog(case_id)['profiles']:
            result = self.evidence.comparison(case_id,item['id'],settings)
            for row in result.rows:
                if row.accepted: accepted.append((result.profile,row))
        return accepted

    def prepared(self,case_id,query):
        self.validate(case_id,query)
        # Ordering is presentation only; avoid redoing native analysis for a sort.
        return self._prepared(case_id,query.model_copy(update={'order':'volume'}).model_dump_json())

    @lru_cache(maxsize=4)
    def _prepared(self,case_id,query_json):
        query = FeatureQuery.model_validate_json(query_json)
        manifest,_ = self.validate(case_id,query)
        coords = manifest.coordinates.model_dump()
        values = np.asarray(self.cases._read_array(case_id,'analytical',query.variable,query.time_index)).reshape(tuple(len(coords[k]) for k in ('depth_m','latitude','longitude')))
        result = analyze(values,coords,query)
        links = defaultdict(lambda: defaultdict(list))
        latindex = {v:i for i,v in enumerate(coords['latitude'])}
        lonindex = {v:i for i,v in enumerate(coords['longitude'])}
        depth_edges = midpoint_edges(coords['depth_m'])
        for profile,row in self.accepted_rows(case_id,query.variable,query.time_index):
            if not query.depth_min_m <= row.depth_m <= query.depth_max_m: continue
            z = min(len(coords['depth_m'])-1,bisect_right(depth_edges,row.depth_m)-1)
            y,x = latindex[row.model_latitude],lonindex[row.model_longitude]
            # Clipped repeated edges cannot assign to excluded source centres.
            if z < 0 or not query.depth_min_m <= coords['depth_m'][z] <= query.depth_max_m: continue
            seed = int(result['labels'][z,y,x])
            if seed >= 0: links[seed][profile.id].append((profile,row))
        for region in result['regions']:
            profiles = links[int(region['id'][1:])]
            region['observations'] = [dict(profile_id=pid,platform=rows[0][0].platform,sample_count=len(rows),sample_indices=[r.sample_index for _,r in rows]) for pid,rows in sorted(profiles.items())]
            region['eligible_profiles'] = len(profiles)
            region['eligible_samples'] = sum(len(rows) for rows in profiles.values())
        return result,values,coords

    def base(self,case_id,query,kind):
        manifest,digest = self.validate(case_id,query)
        result = dict(schema_version='1',kind=kind,method_version=METHOD,case_id=case_id,manifest_sha256=digest,
            observation_library_sha256=self.evidence.library_sha_for(case_id),model_time=manifest.coordinates.times[query.time_index],query=query.model_dump(),units=query.units,methods=METHODS.copy(),limitations=LIMITATIONS.copy())
        temporal=manifest.representations.get('temporal_support')
        if temporal and temporal['kind']=='calendar_month_mean':
            spec=next(v for v in manifest.variables if v.id==query.variable)
            result['quantity']=spec.model_dump(mode='json')
            result['temporal_support']=dict(kind=temporal['kind'],interval=temporal['intervals'][query.time_index],meaning=temporal['meaning'])
            result['methods'].append(spec.definition)
            result['limitations'].append('The timestamp marks a calendar-month mean, not an instantaneous field. Threshold regions describe potential temperature; they are not classified climate events.')
        return result

    def search(self,case_id,query):
        result,values,coords = self.prepared(case_id,query)
        regions = sorted(result['regions'],key=lambda r: ((-r['eligible_samples'], -r['estimated_volume_km3'],int(r['id'][1:])) if query.order == 'observations' else (-r['estimated_volume_km3'],int(r['id'][1:]))))
        labels = result['labels']
        anycell = (labels >= 0).any(axis=0)
        first = np.argmax(labels >= 0,axis=0)
        y,x = np.indices(anycell.shape)
        footprint = np.where(anycell,labels[first,y,x],-1)
        response = self.base(case_id,query,'threshold_regions')
        response.update(shape=list(values.shape),coordinates={k:coords[k] for k in ('depth_m','latitude','longitude')},edges=result['edges'],qualified_cells=result['qualified_cells'],total_regions=len(regions),returned_regions=min(50,len(regions)),regions=regions[:50],footprint=dict(shape=list(anycell.shape),region_ids=[f'r{v}' if v>=0 else None for v in footprint.ravel().tolist()]))
        response['limitations'].append('The plan view shows the shallowest qualifying region in each column. The list returns the first 50 regions in the selected order; totals include all regions.')
        return response

    def region(self,case_id,request):
        result,_,_ = self.prepared(case_id,request.query)
        region = next((r for r in result['regions'] if r['id'] == request.region_id),None)
        if region is None: raise UnsupportedData('region_not_found','This region does not belong to the submitted query. Run the search again.')
        faces = boundary_faces(result['labels'],int(request.region_id[1:]))
        response = self.base(case_id,request.query,'threshold_region')
        response.update(region=region,edges=result['edges'],faces=faces or [],face_count=len(faces) if faces is not None else None,mesh_available=faces is not None,footprint_indices=np.flatnonzero((result['labels']==int(request.region_id[1:])).any(axis=0)).tolist())
        response['methods'].append('Mesh faces follow inferred native cell boundaries. Coplanar rectangles merge without changing the boundary. Display depth is exaggerated; numerical volume is not.')
        if faces is None: response['limitations'].append('This surface exceeds 40,000 merged rectangles. Use the native footprint and section; no simplified mesh is substituted.')
        return response

    def section(self,case_id,request):
        result,values,coords = self.prepared(case_id,request.query)
        data = sample_section(values,coords,result['labels'],request)
        observations = []
        lat,lon = [np.array([s[k] for s in data['stations']]) for k in ('latitude','longitude')]
        for profile,row in self.accepted_rows(case_id,request.query.variable,request.query.time_index):
            if not request.query.depth_min_m <= row.depth_m <= request.query.depth_max_m: continue
            distances = distances_km(row.latitude,row.longitude,lat,lon)
            station = int(np.argmin(distances))
            if distances[station] <= 5:
                observations.append(dict(profile_id=profile.id,platform=profile.platform,sample_index=row.sample_index,depth_m=row.depth_m,observed=row.observed,station_index=station,distance_to_station_km=float(distances[station]),observation_time=row.observation_time))
        response = self.base(case_id,request.query,'native_transect')
        response.update(**data,observations=observations)
        response['methods'].append('Straight line in longitude/latitude with equally spaced stations, including endpoints. Each station selects the nearest native column by great-circle distance; ties use source order. Values remain native levels with no interpolation. Distance is cumulative great-circle distance between requested stations.')
        response['methods'].append('Section evidence must pass the stated P05 gates and lie within 5 km of a requested station, not an inferred continuous corridor. Station count changes this sampled proximity rule.')
        return response

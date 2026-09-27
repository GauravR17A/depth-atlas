"""Integrity-checked daily SST and bounded native-column diagnostic access."""
from datetime import datetime
from functools import lru_cache
import hashlib
import json
from math import isfinite

from science.contracts import UnsupportedData
from science.evidence import nearest_column, REVIEW_SHA
from science.heat import climatology, detect_events, profile_diagnostics, SURFACE_METHODS, DEPTH_METHODS, CAVEATS
from science.heat_contracts import HeatQuery, METHOD


class HeatStore:
    def __init__(self, cases, instruments):
        self.cases, self.instruments = cases, instruments
        self.root = cases.root / 'heat'

    @lru_cache(maxsize=1)
    def manifest(self):
        path = self.root / 'manifest.json'
        if not path.is_file():
            raise UnsupportedData('heat_source_unavailable', 'The checked daily SST pack is unavailable. No substitute surface values are used.')
        body = path.read_bytes()
        data = json.loads(body)
        if data.get('schema_version') != '1' or data.get('baseline_period') != [1982, 2011] or data.get('analysis_years') != [2023, 2024]:
            raise UnsupportedData('case_integrity_error', 'The daily SST pack does not match the declared scientific method.')
        return data, hashlib.sha256(body).hexdigest()

    def location(self, case_id, location_id):
        self.cases.require(case_id)
        manifest, _ = self.manifest()
        location = next((p for p in manifest['locations'] if p['id'] == location_id and p['case_id'] == case_id), None)
        if location is None:
            raise UnsupportedData('unsupported_heat_location', 'Choose one of the checked SST locations in this study case.')
        return location

    @staticmethod
    def public_location(location):
        return {key: location[key] for key in ('id', 'case_id', 'label', 'latitude', 'longitude', 'requested_latitude', 'requested_longitude', 'selection_rule')}

    @lru_cache(maxsize=6)
    def source_series(self, case_id, location_id):
        location = self.location(case_id, location_id)
        path = (self.root / location['path']).resolve()
        if self.root.resolve() not in path.parents:
            raise UnsupportedData('case_integrity_error', 'The checked SST source path is invalid.')
        packed = path.read_bytes()
        if hashlib.sha256(packed).hexdigest() != location['sha256']:
            raise UnsupportedData('case_integrity_error', 'The daily SST data failed its source fingerprint check.')
        data = json.loads(packed)
        dates, values = data['dates'], data['sst_c']
        if len(dates) != len(values) or any(v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or not isfinite(v) or not -3 <= v <= 45) for v in values):
            raise UnsupportedData('case_integrity_error', 'The daily SST source values or dimensions are invalid.')
        return data

    @lru_cache(maxsize=6)
    def surface(self, case_id, location_id):
        data = self.source_series(case_id, location_id)
        clim = climatology(data['dates'], data['sst_c'])
        pairs = [(d, v) for d, v in zip(data['dates'], data['sst_c']) if '2022-01-01' <= d <= '2025-12-31']
        if not pairs or pairs[0][0] != '2022-01-01' or pairs[-1][0] != '2025-12-31':
            raise UnsupportedData('incomplete_heat_context', 'The declared 2022-2025 event context is unavailable.')
        result = detect_events([d for d, _ in pairs], [v for _, v in pairs], clim)
        return clim, result

    def catalog(self, case_id):
        model, model_sha = self.cases.require(case_id)
        data, digest = self.manifest()
        locations = [self.public_location(p) for p in data['locations'] if p['case_id'] == case_id]
        if not locations:
            raise UnsupportedData('heat_source_unavailable', 'No checked surface time series is available for this case.')
        center = next((p for p in locations if p['id'].endswith('-center')), locations[0])
        return dict(schema_version='1', method_version=METHOD, case_id=case_id,
                    model_manifest_sha256=model_sha, heat_manifest_sha256=digest,
                    locations=locations, years=[2023, 2024], baseline_period=[1982, 2011],
                    model_times=model.coordinates.times, depth_limits_m=[100, 300, 700, 1000],
                    default_query=HeatQuery(location_id=center['id']).model_dump(mode='json'),
                    source=data['source'], methods=SURFACE_METHODS+DEPTH_METHODS, caveats=CAVEATS)

    def analyse(self, case_id, query):
        return self._analyse(case_id, query.model_dump_json())

    @lru_cache(maxsize=12)
    def _analyse(self, case_id, query_json):
        query = HeatQuery.model_validate_json(query_json)
        model, model_sha = self.cases.require(case_id)
        if query.model_time_index >= len(model.coordinates.times):
            raise UnsupportedData('unsupported_time', 'Choose an available model timestamp.')
        manifest, digest = self.manifest()
        location = self.location(case_id, query.location_id)
        clim, surface = self.surface(case_id, query.location_id)
        year_start, year_end = f'{query.year}-01-01', f'{query.year}-12-31'
        times = model.coordinates.times
        events = []
        for event in surface['events']:
            if event['start'] <= year_end and event['end'] >= year_start:
                events.append({**event, 'starts_before_year': event['start'] < year_start,
                               'ends_after_year': event['end'] > year_end,
                               'depth_overlap': any(event['start'] <= t[:10] <= event['end'] for t in times)})
        if query.event_id:
            selected = next((event for event in events if event['id'] == query.event_id), None)
            if selected is None:
                raise UnsupportedData('unsupported_heat_event', 'This event is not in the chosen location and year. Reload its event list.')
        else:
            selected = next((event for event in events if event['depth_overlap']), events[0] if events else None)
        applied = query.model_copy(update={'event_id': selected['id'] if selected else None})
        model_time = times[query.model_time_index]
        available = [i for i, value in enumerate(times) if selected and selected['start'] <= value[:10] <= selected['end']]
        status = 'no_event' if not selected else 'outside_model_period' if not available else 'time_outside_event' if query.model_time_index not in available else 'available'
        messages = {
            'no_event': 'No qualifying surface event was detected for this location and year. No event-linked depth claim is made.',
            'outside_model_period': 'This surface event lies outside the supplied 7-10 January 2024 depth case. Depth evidence for its dates is unavailable.',
            'time_outside_event': 'The selected model snapshot is outside this event. Choose one of the available overlapping snapshots.',
            'available': 'This HYCOM snapshot falls on a detected event day at the selected OISST location. It supplies depth context, not a subsurface heatwave diagnosis.',
        }
        profile, observations = None, []
        if status == 'available':
            coords = model.coordinates
            distance, y, x = nearest_column(location['latitude'], location['longitude'], tuple(coords.latitude), tuple(coords.longitude))
            size = len(coords.latitude)*len(coords.longitude)
            offset = y*len(coords.longitude)+x
            native_t = self.cases._read_array(case_id, 'analytical', 'temperature', query.model_time_index)
            native_s = self.cases._read_array(case_id, 'analytical', 'salinity', query.model_time_index)
            t = [native_t[z*size+offset] for z in range(len(coords.depth_m))]
            s = [native_s[z*size+offset] for z in range(len(coords.depth_m))]
            quantities = {p.id: p for p in model.variables}
            if quantities['temperature'].standard_name != 'sea_water_temperature' or quantities['salinity'].standard_name not in {'sea_water_salinity', 'sea_water_practical_salinity'}:
                raise UnsupportedData('unsupported_heat_quantity', 'These depth diagnostics require in-situ temperature and practical salinity.')
            profile = dict(latitude=coords.latitude[y], longitude=coords.longitude[x], requested_latitude=location['latitude'],
                           requested_longitude=location['longitude'], distance_km=distance, model_time=model_time,
                           time_index=query.model_time_index, depth_limit_m=query.depth_limit_m,
                           longitude_index=x, latitude_index=y,
                           **profile_diagnostics(coords.depth_m, t, s, coords.latitude[y], coords.longitude[x], query.depth_limit_m))
            linked_sources = {p.source_sha256: p.source_id for p in model.profiles}
            west, south, east, north = model.case.bounds
            for item in self.instruments.catalog(case_id)['profiles']:
                if item['source_sha256'] not in linked_sources or not selected['start'] <= item['time'][:10] <= selected['end']:
                    continue
                if not (west <= item['longitude'] <= east and south <= item['latitude'] <= north):
                    continue
                original = self.instruments.read(item['id'])
                separation, _, _ = nearest_column(original.latitude, original.longitude, (coords.latitude[y],), (coords.longitude[x],))
                hours = (datetime.fromisoformat(original.time.replace('Z', '+00:00'))-datetime.fromisoformat(model_time.replace('Z', '+00:00'))).total_seconds()/3600
                observations.append(dict(id=original.id, title=original.title, platform=original.platform, time=original.time,
                                         latitude=original.latitude, longitude=original.longitude, distance_km=separation,
                                         time_offset_hours=hours, source_id=linked_sources[original.source_sha256], source_url=original.source_url,
                                         source_sha256=original.source_sha256, provenance_hold=original.source_sha256 == REVIEW_SHA,
                                         note='Event-period observation context. Position and time differ from this model column; inspect source QC before comparing.'))
        return dict(schema_version='1', kind='derived', method_version=METHOD, case_id=case_id,
                    query=applied.model_dump(mode='json'), model_manifest_sha256=model_sha,
                    heat_manifest_sha256=digest, location_sha256=location['sha256'], location=self.public_location(location),
                    source=manifest['source'], baseline=clim,
                    series=[row for row in surface['series'] if row['date'].startswith(str(query.year)+'-')],
                    events=events, selected_event=selected,
                    depth_link=dict(status=status, message=messages[status], available_time_indices=available, model_time=model_time),
                    depth_profile=profile, observations=observations,
                    methods=SURFACE_METHODS+DEPTH_METHODS, caveats=CAVEATS)

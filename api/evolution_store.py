"""Read-only, bounded feature evolution using checked native case packs."""
from copy import deepcopy
from collections import OrderedDict
from concurrent.futures import Future
import hashlib
import json
from math import fsum
from threading import RLock

import numpy as np

from api.instrument_store import InstrumentStore
from science.contracts import UnsupportedData
from science.evolution_contracts import METHOD, NATIVE_CADENCE_HOURS, SUPPORTED_CASES, EvolutionQuery
from science.evolution import (
    LIMITATIONS, METHODS, MAX_FOOTPRINT_INDICES, MAX_REGIONS_PER_FRAME,
    MAX_TOTAL_REGIONS, node_id, region_contacts, region_statistics, summarize, transition,
)
from science.features import geometry


class EvolutionStore:
    def __init__(self, features):
        self.features = features
        self._results = OrderedDict()
        self._inflight = {}
        self._cache_lock = RLock()
        self._cache_limit = 8

    @staticmethod
    def _checked_bytes(path, expected):
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise UnsupportedData('case_integrity_error', 'A required checked source file is unavailable.') from error
        if hashlib.sha256(payload).hexdigest() != expected:
            raise UnsupportedData('case_integrity_error', 'A checked source file changed or failed its integrity check.')
        return payload

    def _sources(self, case_id, query):
        if case_id not in SUPPORTED_CASES:
            raise UnsupportedData('unsupported_evolution_case', 'This 12-hour feature evolution method supports the supplied Bay of Bengal and Arabian Sea cases. Monthly Pacific fields need a separately checked correspondence method.')
        manifest, digest = self.features.cases.require(case_id)
        if query.end_index >= len(manifest.coordinates.times):
            raise UnsupportedData('unsupported_time', 'Choose available source frames.')
        self._checked_bytes(self.features.cases.root/case_id/'manifest.json', digest)
        if manifest.representations.get('temporal_support', {}).get('kind') == 'calendar_month_mean':
            raise UnsupportedData('unsupported_evolution_case', 'Monthly averages cannot use this 12-hour correspondence method.')
        # Validate every requested threshold and source variable before any work.
        self.features.validate(case_id, query.feature_query(query.start_index))
        variables = ['eastward_velocity', 'northward_velocity'] if query.variable == 'horizontal_kinetic_energy' else [query.variable]
        for time_index in query.indices():
            for variable in variables:
                path = f'analytical/{variable}-{time_index}.bin.gz'
                record = next((row for row in manifest.files if row['path'] == path), None)
                if record is None:
                    raise UnsupportedData('unsupported_variable', 'A required native variable is not supplied for every selected frame.')
                self._checked_bytes(self.features.cases.root/case_id/path, record['sha256'])
        # Cached earlier-phase results are immutable. Check on-disk identities
        # against those snapshots rather than modifying their shared caches.
        instruments = self.features.instruments
        fresh = InstrumentStore(instruments.root)
        try:
            index = fresh.index(case_id)
        except (OSError, ValueError) as error:
            raise UnsupportedData('case_integrity_error', 'The checked observation index cannot be read.') from error
        library_sha = hashlib.sha256(json.dumps(index, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if library_sha != self.features.evidence.library_sha_for(case_id):
            raise UnsupportedData('case_integrity_error', 'The observation library changed after it was loaded. Restart with the checked source library.')
        base_ids = {p['id'] for p in fresh.index()['profiles']}
        for profile in index['profiles']:
            name = profile['id']+'.json'
            record = next((row for row in index['files'] if row['name'] == name), None)
            directory = instruments.root if profile['id'] in base_ids else instruments.root.parent/'instruments-arabian-sea'
            if record is None:
                raise UnsupportedData('case_integrity_error', 'An observation profile failed its integrity check.')
            self._checked_bytes(directory/name, record['sha256'])
        return manifest, digest, library_sha

    def _calculate(self, case_id, query, manifest, offset=0.0, detailed=True):
        frames, internal = [], []
        total_regions, footprint_count = 0, 0
        coords = manifest.coordinates.model_dump()
        _, edges, volumes = geometry(coords, query.feature_query(query.start_index, offset))
        depths = np.asarray(coords['depth_m'])
        selected_depths = np.flatnonzero((depths >= query.depth_min_m) & (depths <= query.depth_max_m) & (volumes[:, 0, 0] > 0))
        for time_index in query.indices():
            native, values, _ = self.features.prepared(case_id, query.feature_query(time_index, offset))
            total_regions += len(native['regions'])
            if len(native['regions']) > MAX_REGIONS_PER_FRAME or total_regions > MAX_TOTAL_REGIONS:
                raise UnsupportedData('evolution_too_complex', 'Feature evolution accepts at most 512 regions per frame and 2,048 across selected frames. Narrow the depth or threshold range.')
            finite = np.isfinite(values)
            frame = dict(time_index=time_index, time=coords['times'][time_index], qualified_cells=native['qualified_cells'], total_regions=len(native['regions']),
                         estimated_volume_km3=fsum(float(volumes.ravel()[index]) for index in np.flatnonzero(native['labels'].ravel() >= 0)))
            if detailed:
                regions = []
                for original in sorted(native['regions'], key=lambda r: int(r['id'][1:])):
                    region = deepcopy(original)
                    seed = int(region['id'][1:])
                    indices = native['members'][seed]
                    footprint = np.unique(indices % (values.shape[1]*values.shape[2])).tolist()
                    member_depths = indices // (values.shape[1]*values.shape[2])
                    depth_contacts = []
                    if len(selected_depths):
                        if np.any(member_depths == selected_depths[0]):
                            depth_contacts.append('shallow')
                        if np.any(member_depths == selected_depths[-1]):
                            depth_contacts.append('deep')
                    footprint_count += len(footprint)
                    if footprint_count > MAX_FOOTPRINT_INDICES:
                        raise UnsupportedData('evolution_too_complex', 'These regions create too much footprint geometry. Narrow the depth or threshold range.')
                    region.update(node_id=node_id(time_index, seed), time_index=time_index, footprint_indices=footprint,
                                  selection_depth_contacts=depth_contacts,
                                  **region_statistics(values, volumes, indices),
                                  **region_contacts(indices, values.shape, finite))
                    regions.append(region)
                frame['regions'] = regions
            frames.append(frame)
            internal.append(dict(time_index=time_index, time=frame['time'], labels=native['labels'], members=native['members'], finite=finite))
        transitions = [transition(left, right, volumes, query.minimum_overlap) for left, right in zip(internal, internal[1:])]
        return frames, transitions, dict(zip(('depth_m', 'latitude', 'longitude'), [edge.tolist() for edge in edges]))

    def run(self, case_id, query: EvolutionQuery):
        query = EvolutionQuery.model_validate(query.model_dump(mode='json') if isinstance(query, EvolutionQuery) else query)
        # Integrity checks must run even on a warm hit or a duplicate request.
        manifest, digest, library_sha = self._sources(case_id, query)
        key = (case_id, digest, library_sha, METHOD, query.model_dump_json())
        with self._cache_lock:
            if key in self._results:
                cached = self._results[key]
                self._results.move_to_end(key)
                return deepcopy(cached)
            future = self._inflight.get(key)
            leader = future is None
            if leader:
                future = Future()
                self._inflight[key] = future
        if not leader:
            return deepcopy(future.result())
        try:
            result = self._compute(case_id, query, manifest, digest, library_sha)
            snapshot = deepcopy(result)
        except BaseException as error:
            with self._cache_lock:
                self._inflight.pop(key, None)
                future.set_exception(error)
            raise
        with self._cache_lock:
            self._results[key] = snapshot
            self._results.move_to_end(key)
            while len(self._results) > self._cache_limit:
                self._results.popitem(last=False)
            self._inflight.pop(key, None)
            future.set_result(snapshot)
        return deepcopy(snapshot)

    def _compute(self, case_id, query, manifest, digest, library_sha):
        frames, transitions, edges = self._calculate(case_id, query, manifest)
        offsets = [-query.sensitivity_delta, 0.0, query.sensitivity_delta] if query.sensitivity_delta > 0 else [0.0]
        sensitivity = []
        for offset in offsets:
            if offset == 0:
                trial_frames = [dict(time_index=f['time_index'], time=f['time'], qualified_cells=f['qualified_cells'], total_regions=f['total_regions'],
                                     estimated_volume_km3=f['estimated_volume_km3']) for f in frames]
                trial_transitions = transitions
            else:
                trial_frames, trial_transitions, _ = self._calculate(case_id, query, manifest, offset, detailed=False)
            feature = query.feature_query(query.start_index, offset)
            sensitivity.append(dict(
                offset=offset, threshold=feature.threshold, upper_threshold=feature.upper_threshold,
                summary=summarize(trial_frames, trial_transitions),
                frames=[dict(time_index=f['time_index'], time=f['time'], region_count=f['total_regions'], qualified_cells=f['qualified_cells'], estimated_volume_km3=f['estimated_volume_km3']) for f in trial_frames],
                transitions=[dict(from_time_index=t['from_time_index'], to_time_index=t['to_time_index'], status=t['status'], link_count=len(t['links']),
                                  split_count=t['split_count'], merge_count=t['merge_count'], ambiguous_count=t['ambiguous_count'],
                                  appearance_count=len(t['appeared_node_ids']), disappearance_count=len(t['disappeared_node_ids']),
                                  unresolved_count=len(t['source_unresolved_node_ids'])+len(t['target_unresolved_node_ids'])) for t in trial_transitions],
            ))
        return dict(
            schema_version='1', kind='feature_evolution', method_version=METHOD,
            case_id=case_id, manifest_sha256=digest, observation_library_sha256=library_sha,
            query=query.model_dump(mode='json'), cadence_hours=NATIVE_CADENCE_HOURS,
            coordinates=dict(latitude=manifest.coordinates.latitude, longitude=manifest.coordinates.longitude),
            edges=edges, frames=frames, transitions=transitions,
            summary=summarize(frames, transitions), sensitivity=sensitivity,
            methods=METHODS.copy(), limitations=LIMITATIONS.copy(),
        )

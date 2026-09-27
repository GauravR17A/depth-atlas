"""Bounded library-only comparisons with immutable case and observation identities."""
from collections import Counter
from functools import lru_cache
import hashlib
import json

from science.contracts import UnsupportedData
from science.evidence import CAVEATS, METHODS, compare, epoch
from science.evidence_contracts import Coverage, CoverageProfile, MatchSettings, METHOD_VERSION


class EvidenceStore:
    def __init__(self, cases, instruments):
        self.cases, self.instruments = cases, instruments
        self.library_sha = hashlib.sha256(json.dumps(instruments.index(), sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def case_caveats(self,case_id):
        manifest,_=self.cases.require(case_id)
        if manifest.representations.get('temporal_support',{}).get('kind')=='calendar_month_mean':
            return ['GODAS is an assimilative monthly analysis. Its potential temperature is not interchangeable with instantaneous in-situ instrument temperature; this comparator excludes those incompatible quantities.',
                    'The model timestamp is the beginning of its averaging month, not an instantaneous sample. No monthly potential-temperature residual is calculated by this comparison method.',
                    *CAVEATS[1:4],CAVEATS[5]]
        return CAVEATS

    @lru_cache(maxsize=4)
    def library_sha_for(self,case_id):
        return hashlib.sha256(json.dumps(self.instruments.index(case_id),sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def comparison(self, case_id, profile_id, settings):
        manifest, digest = self.cases.require(case_id)
        if settings.variable not in manifest.case.variables:
            raise UnsupportedData('unsupported_variable','This case does not supply the requested comparison variable.')
        if settings.time_index >= len(manifest.coordinates.times):
            raise UnsupportedData('unsupported_time', 'Choose an available model timestamp.')
        if profile_id not in {p['id'] for p in self.instruments.catalog(case_id)['profiles']}:
            raise UnsupportedData('profile_not_found','This profile is not in the selected case observation library.')
        return self._comparison(case_id, profile_id, settings.model_dump_json(), digest, self.library_sha_for(case_id), METHOD_VERSION)

    @lru_cache(maxsize=20)
    def _comparison(self, case_id, profile_id, settings_json, manifest_sha, library_sha, method):
        settings = MatchSettings.model_validate_json(settings_json)
        profile = self.instruments.read(profile_id)
        values = self.cases._read_array(case_id, 'analytical', settings.variable, settings.time_index)
        result=compare(self.cases.require(case_id)[0], manifest_sha, library_sha, profile, settings, values)
        return result.model_copy(update={'caveats':self.case_caveats(case_id)})

    def coverage(self, case_id, settings):
        manifest, digest = self.cases.require(case_id)
        return self._coverage(case_id, settings.model_dump_json(), digest, self.library_sha_for(case_id), METHOD_VERSION)

    @lru_cache(maxsize=4)
    def _coverage(self, case_id, settings_json, manifest_sha, library_sha, method):
        settings = MatchSettings.model_validate_json(settings_json)
        manifest = self.cases.require(case_id)[0]
        profiles, reasons = [], Counter()
        for item in self.instruments.catalog(case_id)['profiles']:
            result = self.comparison(case_id, item['id'], settings)
            accepted = [r for r in result.rows if r.accepted]
            distances = [r.distance_km for r in accepted if r.distance_km is not None]
            # Eligible coverage uses eligible samples only. Empty profiles retain
            # source time offsets to explain why no samples qualify.
            offsets = [r.time_offset_hours for r in (accepted or result.rows)]
            suggested, suggested_count = None, 0
            suggested_offset, suggested_distance = None, None
            # Only time-excluded samples can benefit from changing the snapshot.
            # Rank suggestions by time separation, then index. Never apply one here.
            if not accepted and 'time_window' in result.exclusion_counts:
                candidates = []
                for i, timestamp in enumerate(manifest.coordinates.times):
                    if i == settings.time_index:
                        continue
                    # Per-sample timestamps matter for moving/long casts. Only
                    # snapshots capable of rescuing a time-excluded row need IO.
                    if not any(r.reason == 'time_window' and abs(epoch(timestamp)-epoch(r.observation_time))/3600 <= settings.time_window_hours for r in result.rows):
                        continue
                    alternate = self.comparison(case_id, item['id'], settings.model_copy(update={'time_index': i}))
                    if alternate.matched_count:
                        alternate_rows = [r for r in alternate.rows if r.accepted]
                        candidates.append((min(abs(r.time_offset_hours) for r in alternate_rows), min(r.distance_km for r in alternate_rows), i, alternate.matched_count))
                if candidates:
                    suggested_offset, suggested_distance, suggested, suggested_count = min(candidates)
            profiles.append(CoverageProfile(profile=result.profile, total_samples=result.total_samples,
                matched_count=result.matched_count, excluded_count=result.excluded_count, exclusion_counts=result.exclusion_counts,
                eligible_depths_m=[r.depth_m for r in accepted], time_offset_hours_min=min(offsets), time_offset_hours_max=max(offsets),
                minimum_abs_time_offset_hours=min(abs(r.time_offset_hours) for r in accepted) if accepted else None,
                distance_km_min=min(distances) if distances else None, distance_km_max=max(distances) if distances else None,
                metrics=result.metrics, suggested_time_index=suggested, suggested_matched_count=suggested_count,
                suggested_time_offset_hours=suggested_offset, suggested_distance_km=suggested_distance))
            reasons.update(result.exclusion_counts)
        return Coverage(case_id=case_id, manifest_sha256=manifest_sha, observation_library_sha256=library_sha,
            model_time=manifest.coordinates.times[settings.time_index], settings=settings,
            total_profiles=len(profiles), matched_profiles=sum(p.matched_count>0 for p in profiles),
            total_samples=sum(p.total_samples for p in profiles), matched_samples=sum(p.matched_count for p in profiles),
            excluded_samples=sum(p.excluded_count for p in profiles), exclusion_counts=dict(reasons), profiles=profiles,
            methods=METHODS, caveats=self.case_caveats(case_id))

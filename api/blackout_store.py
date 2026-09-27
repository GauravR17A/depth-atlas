"""Bounded checked-library blackout access without mutable result caching."""
import hashlib
import json

from api.instrument_store import InstrumentStore
from science.blackout import CAVEATS, METHODS, analyze_blackout, resolve_exclusions
from science.blackout_contracts import BlackoutQuery, METHOD
from science.contracts import UnsupportedData
from science.instruments import InstrumentSummary

MAX_PROFILES = 128
MAX_SAMPLES = 100_000


class BlackoutStore:
    def __init__(self, evidence):
        self.evidence = evidence

    def _verify_sources(self, case_id, query, manifest, digest):
        """Check disk identities even when the original evidence caches are warm."""
        try:
            root = self.evidence.cases.root / case_id
            if hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest() != digest:
                raise UnsupportedData('case_integrity_error', 'The model manifest changed after it was loaded. Restart with a checked case pack.')
            # Coverage includes suggested alternate matching times, so all
            # snapshots of this variable contribute to the original evidence.
            for time_index in range(len(manifest.coordinates.times)):
                relative = f'analytical/{query.settings.variable}-{time_index}.bin.gz'
                record = next((item for item in manifest.files if item['path'] == relative), None)
                if record is None or hashlib.sha256((root / relative).read_bytes()).hexdigest() != record['sha256']:
                    raise UnsupportedData('case_integrity_error', 'A native source frame failed its integrity check.')
            fresh = InstrumentStore(self.evidence.instruments.root)
            index = fresh.index(case_id)
            digest = hashlib.sha256(json.dumps(index, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            if digest != self.evidence.library_sha_for(case_id):
                raise UnsupportedData('case_integrity_error', 'The observation library changed after it was loaded. Restart with the checked source library.')
            for item in index['profiles']:
                # A fresh store rereads each payload and validates its declared
                # hash. It does not clear or mutate shared instrument caches.
                fresh.read(item['id'])
        except UnsupportedData:
            raise
        except (OSError, ValueError, KeyError) as error:
            raise UnsupportedData('case_integrity_error', 'A required checked source file is missing or invalid.') from error

    def catalog(self, case_id):
        manifest, digest = self.evidence.cases.require(case_id)
        profiles = self.evidence.instruments.catalog(case_id)['profiles']
        groups = {}
        for field in ('instrument', 'platform', 'collection'):
            names = sorted({profile.get(field, 'Imported file' if field == 'collection' else '') for profile in profiles})
            groups[field] = [dict(id=name, profile_ids=sorted(profile['id'] for profile in profiles
                                    if profile.get(field, 'Imported file' if field == 'collection' else '') == name))
                             for name in names]
        return dict(schema_version='1', method_version=METHOD, case_id=case_id,
                    manifest_sha256=digest, observation_library_sha256=self.evidence.library_sha_for(case_id),
                    profiles=profiles, groups=groups, model_times=manifest.coordinates.times,
                    variables=[name for name in ('temperature', 'salinity') if name in manifest.case.variables],
                    default_query=BlackoutQuery().model_dump(mode='json'), methods=METHODS.copy(),
                    caveats=[*CAVEATS, *self.evidence.case_caveats(case_id)])

    def run(self, case_id, query):
        # Revalidation protects callers that constructed models with model_copy.
        query = BlackoutQuery.model_validate(query.model_dump(mode='json') if isinstance(query, BlackoutQuery) else query)
        manifest, digest = self.evidence.cases.require(case_id)
        if query.settings.variable not in manifest.case.variables:
            raise UnsupportedData('unsupported_variable', 'This case does not supply the requested comparison variable.')
        if query.settings.time_index >= len(manifest.coordinates.times):
            raise UnsupportedData('unsupported_time', 'Choose an available model timestamp.')
        profiles = [InstrumentSummary.model_validate(item) for item in self.evidence.instruments.catalog(case_id)['profiles']]
        if len(profiles) > MAX_PROFILES or sum(profile.samples for profile in profiles) > MAX_SAMPLES:
            raise UnsupportedData('blackout_budget_exceeded', 'This library exceeds the bounded observation blackout budget.')
        resolve_exclusions(profiles, query)
        self._verify_sources(case_id, query, manifest, digest)
        baseline = self.evidence.coverage(case_id, query.settings)
        comparisons = [self.evidence.comparison(case_id, profile.id, query.settings) for profile in profiles]
        if sum(item.total_samples for item in comparisons) > MAX_SAMPLES:
            raise UnsupportedData('blackout_budget_exceeded', 'This library exceeds the bounded observation blackout budget.')
        return analyze_blackout(baseline, comparisons, query).model_dump(mode='json')

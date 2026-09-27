"""Bounded, request-scoped observation support. Imported originals are not cached."""
import json
from api.imported_store import ImportedEvidenceStore, ImportedInstrumentStore
from science.contracts import UnsupportedData
from science.support import METHOD, associate


class SupportStore:
    def __init__(self, features):
        self.features = features

    def run(self, case_id, request):
        features = self.features
        manifest, digest = features.validate(case_id, request.query)
        if manifest.representations.get('science_compatibility', {}).get('direct_observation_residual') is False:
            raise UnsupportedData('incompatible_quantity', 'Monthly potential temperature cannot be paired with instantaneous in-situ readings.')
        prepared, _, coordinates = features.prepared(case_id, request.query)
        evidence = features.evidence
        if request.import_source:
            evidence = ImportedEvidenceStore(features.cases, ImportedInstrumentStore(request.import_source, features.instruments))
        profiles = evidence.instruments.catalog(case_id)['profiles']
        if len(profiles) > 128 or sum(p['samples'] for p in profiles) > 100_000:
            raise UnsupportedData('file_limits', 'This collection exceeds the bounded support calculation.')
        comparisons = [evidence.comparison(case_id, p['id'], request.settings) for p in profiles]
        response = dict(schema_version='1', kind='structure_observation_support', method_version=METHOD,
                        case_id=case_id, manifest_sha256=digest,
                        observation_library_sha256=evidence.library_sha_for(case_id),
                        source_scope=request.import_source.filename if request.import_source else 'Bundled observation library',
                        model_time=manifest.coordinates.times[request.query.time_index],
                        query=request.query.model_dump(mode='json'), region_id=request.region_id,
                        settings=request.settings.model_dump(mode='json'), units=request.query.units,
                        **associate(prepared['labels'], coordinates, request.query, request.region_id, comparisons),
                        limitations=[
                            'Support counts distinct native cells containing eligible pairs, assigned by depth midpoint bins in the matched column. It is not confidence or a volume fraction.',
                            'Residuals use native-depth interpolation, not the midpoint-bin centre value. Observed values need not meet the model threshold.',
                            'Gaps mean no eligible sample in this selected collection under these rules, not absence of all observations.',
                            'Plan-view support collapses depth. A supported column can still have unobserved depths.',
                            'Agreement with an assimilating model is not independent validation.',
                        ])
        if request.import_source:
            response['import_identity'] = dict(source_sha256=request.import_source.source_sha256, parser_version=request.import_source.parser_version, context_sha256=evidence.instruments.context_sha, profiles_sha256=evidence.instruments.profiles_sha)
        if len(json.dumps(response, separators=(',', ':'), ensure_ascii=False).encode()) > 4_200_000:
            raise UnsupportedData('file_limits', 'Support exceeds the hosted response budget. Use a smaller region or observation file.')
        return response

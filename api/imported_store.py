"""Request-scoped input reparsing; never put private uploads in global caches."""
from adapters.import_preview import inspect_import, PARSER_VERSION
from api.evidence_store import EvidenceStore
from science.contracts import UnsupportedData
from science.evidence import summary, REVIEW_SHA
from science.imported import IMPORT_METHOD
from science.instruments import InstrumentProfile
from science.investigations import fingerprint


class ImportedInstrumentStore:
    def __init__(self, source, library):
        if source.parser_version != PARSER_VERSION:
            raise UnsupportedData('method_mismatch', 'This import requires a different parser version. Keep the original file; automatic migration is not available.')
        self.source = source
        mapping = None if source.mapping is None else {key: None if value is None else value.model_dump(exclude_none=True) for key, value in source.mapping.items()}
        source_url = next((e['source_url'] for e in library.catalog()['examples'] if e['sha256'] == source.source_sha256), '')
        review = inspect_import(source.original_bytes(), source.filename, mapping, source_url)
        if not review['result']:
            raise UnsupportedData('invalid_mapping', review['issue'] or 'The imported source cannot be parsed with these settings.')
        self.profiles = []
        for raw in review['result']['profiles']:
            profile = InstrumentProfile.model_validate(raw)
            profile.metadata = {**profile.metadata, 'original_profile_id': profile.id}
            profile.id = 'import-' + profile.id
            profile.collection = 'Imported · ' + source.filename
            self.profiles.append(profile)
        self.context_sha = fingerprint(source.model_dump(mode='json', exclude={'content_base64'}))
        self.profiles_sha = fingerprint([p.model_dump(mode='json') for p in self.profiles])

    def index(self, case_id=None):
        return dict(schema_version='2', profiles=[summary(p).model_dump(mode='json') for p in self.profiles],
                    import_context_sha256=self.context_sha,
                    sources=[dict(title='User-supplied original observation file', source_file=self.source.filename,
                                  sha256=self.source.source_sha256, parser_version=PARSER_VERSION,
                                  licence='Uploader must have permission to use and share this file. Source terms still apply.')])

    def catalog(self, case_id=None):
        return self.index(case_id)

    def read(self, profile_id):
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        raise UnsupportedData('profile_not_found', 'This profile is absent from the included original file. No library profile has been substituted.')


class ImportedEvidenceStore(EvidenceStore):
    # The ordinary library uses bounded process-wide LRU caches. Imported data
    # must be collectible when this request ends, including these cache keys.
    def library_sha_for(self, case_id):
        return self.library_sha

    def _comparison(self, *args):
        return EvidenceStore._comparison.__wrapped__(self, *args)

    def _coverage(self, *args):
        return EvidenceStore._coverage.__wrapped__(self, *args)

    def case_caveats(self, case_id):
        base = [c for c in super().case_caveats(case_id)[:-1] if not c.startswith('One source file is held') or self.instruments.source.source_sha256 == REVIEW_SHA]
        return [*base,
                'This comparison reparses a user-supplied file. Source QC is preserved; uploader-declared CSV metadata is not independently certified.',
                'Coverage includes profiles from this imported file only. It does not include the bundled observation library or other open files.']


def imported_investigations(base, source, recipe):
    if recipe.mode not in {'instrument', 'comparison'}:
        raise UnsupportedData('invalid_request', 'Imported sources can be saved with observation profiles or model comparisons only.')
    from copy import copy
    scoped = copy(base)
    scoped.instruments = ImportedInstrumentStore(source, base.instruments)
    scoped.evidence = ImportedEvidenceStore(base.cases, scoped.instruments)
    scoped.import_source = source
    return scoped

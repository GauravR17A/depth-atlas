"""Phase 14 bounded HTTP acceptance and exact cross-platform replay.

Local calculations are transport consistency references, not independent
scientific validation. The hand-computable scientific fixtures run in pytest.
No automatic retries or widened fingerprint tolerances are used.
"""
import argparse
from copy import deepcopy
import io
import json
from pathlib import Path
from zipfile import ZipFile

from api.case_store import CaseStore
from api.instrument_store import InstrumentStore
from api.evidence_store import EvidenceStore
from api.feature_store import FeatureStore
from api.evolution_store import EvolutionStore
from api.blackout_store import BlackoutStore
from api.investigation_store import numerical_files
from science.evolution_contracts import EvolutionQuery, METHOD as EVOLUTION_METHOD
from science.blackout_contracts import BlackoutQuery
from science.evidence_contracts import MatchSettings
from science.verify_p10_public import validate_bundle
from science.verify_p11_public import read_records
from science.verify_p13_public import Audit, exact

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--records-output', type=Path)
    parser.add_argument('--replay-records', type=Path, action='append', default=[])
    parser.add_argument('--replay-only', action='store_true')
    parser.add_argument('--expected-version', default='0.14.1')
    parser.add_argument('--timeout-seconds', type=float, default=45)
    parser.add_argument('--max-runtime-seconds', type=float, default=1200)
    args = parser.parse_args()
    if args.replay_only and not args.replay_records:
        parser.error('--replay-only requires at least one nonempty --replay-records file.')
    for path in args.replay_records:
        if not read_records(path):
            parser.error(f'Replay records are empty: {path}')
    audit = Audit(args)
    audit.report.update(method=__doc__, method_version=[EVOLUTION_METHOD, 'p14-blackout-v1'])
    records = []

    def health():
        result = audit.json('/api/health')
        assert result['status'] == 'ok' and result['version'] == args.expected_version and result['case_count'] == 5
        return result

    def archive_check(record):
        raw, _ = audit.request('/api/investigations/export', dict(replay=record['replay'], format='zip'))
        expected = numerical_files(record)
        with ZipFile(io.BytesIO(raw)) as archive:
            assert set(expected) | {'settings.json', 'SOURCES.json', 'README.txt', 'source-credits.txt', 'report.html', 'investigation.json'} <= set(archive.namelist())
            for name, content in expected.items():
                assert archive.read(name).decode('utf-8') == content, name + ' differs'
            saved = json.loads(archive.read('investigation.json'))
            validate_bundle(saved, args.expected_version)
            exact(saved['results'], record['results'])
            exact(saved['replay'], record['replay'])
            exact(json.loads(archive.read('settings.json')), record['replay'])
            exact(json.loads(archive.read('SOURCES.json')), record['references'])
            assert '<script' not in archive.read('report.html').decode().lower()
        return dict(tables=list(expected), result_sha256=record['result_sha256'])

    def replay(record):
        result = audit.json('/api/investigations/replay', record['replay'])
        validate_bundle(result, args.expected_version)
        exact(result['results'], record['results'])
        exact(result['replay'], record['replay'])
        return dict(mode=record['replay']['recipe']['mode'], result_sha256=result['result_sha256'])

    audit.check('public health and version', health)
    if not args.replay_only:
        cases = CaseStore(ROOT / 'casepacks')
        instruments = InstrumentStore(ROOT / 'casepacks/instruments')
        evidence = EvidenceStore(cases, instruments)
        features = FeatureStore(cases, instruments, evidence)
        evolution, blackout = EvolutionStore(features), BlackoutStore(evidence)
        bay, arabian = 'bay-bengal-2024-01', 'arabian-sea-2024-01'
        baseline = blackout.run(bay, BlackoutQuery())
        profile = next(row['profile']['id'] for row in baseline['baseline']['profiles'] if row['matched_count'])
        variants = [
            ('Bay evolution', 'evolution', bay, EvolutionQuery()),
            ('Arabian branching', 'evolution', arabian, EvolutionQuery()),
            ('Explicit skipped-frame gap', 'evolution', arabian, EvolutionQuery(frame_step=2)),
            ('Salinity evolution', 'evolution', bay, EvolutionQuery(variable='salinity', units='psu', threshold=34, sensitivity_delta=.1)),
            ('Original evidence', 'blackout', bay, BlackoutQuery()),
            ('One eligible profile excluded', 'blackout', bay, BlackoutQuery(excluded_profile_ids=[profile])),
            ('All profiles excluded', 'blackout', bay, BlackoutQuery(excluded_profile_ids=[p['profile']['id'] for p in baseline['baseline']['profiles']])),
            ('Arabian Argo exclusion', 'blackout', arabian, BlackoutQuery(settings=MatchSettings(time_index=3), excluded_instruments=['argo'])),
            ('Pacific monthly incompatibility', 'blackout', 'pacific-godas-2015-son', BlackoutQuery()),
        ]
        for label, mode, case_id, query in variants:
            def check_case(label=label, mode=mode, case_id=case_id, query=query):
                local = (evolution if mode == 'evolution' else blackout).run(case_id, query)
                served = audit.json(f'/api/cases/{case_id}/{mode}/run', query.model_dump(mode='json'))
                exact(served, local)
                recipe = dict(mode=mode, case_id=case_id, query=served['query'])
                if mode == 'evolution':
                    recipe['selected_node'] = next((n['node_id'] for f in served['frames'] for n in f['regions']), None)
                record = audit.json('/api/investigations/capture', dict(title=label, recipe=recipe,
                                    expected_model_sha256=served['manifest_sha256'], expected_observation_library_sha256=served['observation_library_sha256']))
                validate_bundle(record, args.expected_version)
                exact(record['results'][0]['output'], served)
                if case_id == 'pacific-godas-2015-son':
                    assert served['baseline']['matched_samples'] == 0
                    assert served['baseline']['exclusion_counts']['incompatible_variable'] > 0
                    manifest, _ = cases.require(case_id)
                    exact(record['references'][0]['files'], manifest.sources[0].model_dump(mode='json')['files'])
                records.append(record)
                if args.records_output:
                    args.records_output.parent.mkdir(parents=True, exist_ok=True)
                    args.records_output.write_text(json.dumps(dict(base_url=args.base_url, records=records), indent=2, allow_nan=False), encoding='utf-8')
                replay(record)
                archive_check(record)
                return dict(mode=mode, case_id=case_id, result_sha256=record['result_sha256'])
            audit.check(label + ': exact API, capture, replay and exports', check_case)

        def invalid_exclusion():
            query = BlackoutQuery(excluded_profile_ids=['not-a-real-profile']).model_dump(mode='json')
            result = audit.json(f'/api/cases/{bay}/blackout/run', query, status=422)
            assert result['error']['code'] == 'unknown_blackout_selection'
            return result['error']['code']
        audit.check('unknown exclusion rejected', invalid_exclusion)

        def monthly_unsupported():
            result = audit.json('/api/cases/pacific-godas-2015-son/evolution/run', EvolutionQuery().model_dump(mode='json'), status=422)
            assert result['error']['code'] == 'unsupported_evolution_case'
            return result['error']['code']
        audit.check('monthly fields are not 12-hour evolution', monthly_unsupported)

        if records:
            def tampered_result():
                request = deepcopy(records[0]['replay'])
                request['expected_result_sha256'] = '0' * 64
                result = audit.json('/api/investigations/replay', request, status=422)
                assert result['error']['code'] == 'result_mismatch'
                return result['error']['code']
            audit.check('changed numerical fingerprint rejected', tampered_result)

    for path in args.replay_records:
        for index, record in enumerate(read_records(path)):
            label = f'{path.name} #{index + 1} {record["replay"]["recipe"]["mode"]}'
            audit.check('exact retained replay ' + label, lambda record=record: replay(record))
            if record['replay']['recipe']['mode'] in {'evolution', 'blackout'}:
                audit.check('exact retained exports ' + label, lambda record=record: archive_check(record))
    return audit.finish()


if __name__ == '__main__':
    raise SystemExit(main())

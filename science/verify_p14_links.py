"""Independent native-set checks of P14 link arithmetic and depth contact labels.

This checker obtains existing P07 memberships and midpoint-bin volume weights,
then uses Python set intersections to recompute every emitted Arabian link. It
does not use the P14 transition function for expected overlaps, but it does reuse
the existing geometry helper. This is a correspondence-rule check, not an
independent validation of provider geometry, ocean evolution or water transport.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from math import fsum
from pathlib import Path

from api.case_store import CaseStore
from api.evidence_store import EvidenceStore
from api.evolution_store import EvolutionStore
from api.feature_store import FeatureStore
from api.instrument_store import InstrumentStore
from science.evolution_contracts import EvolutionQuery
from science.features import geometry
from science.investigations import fingerprint

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/evidence/p14-independent-links.json')
    args = parser.parse_args()
    cases = CaseStore(ROOT / 'casepacks')
    instruments = InstrumentStore(ROOT / 'casepacks/instruments')
    evidence = EvidenceStore(cases, instruments)
    features = FeatureStore(cases, instruments, evidence)
    evolution = EvolutionStore(features)
    query = EvolutionQuery(sensitivity_delta=0)
    case_id = 'arabian-sea-2024-01'
    result = evolution.run(case_id, query)
    coords = cases.require(case_id)[0].coordinates.model_dump()
    weights = geometry(coords, query.feature_query(0))[2].ravel()
    checks = []

    def check(name, action):
        try:
            detail = action()
            checks.append(dict(name=name, passed=True, detail=detail))
        except Exception as error:
            checks.append(dict(name=name, passed=False, error=f'{type(error).__name__}: {error}'))

    for step in result['transitions']:
        source = features.prepared(case_id, query.feature_query(step['from_time_index']))[0]
        target = features.prepared(case_id, query.feature_query(step['to_time_index']))[0]
        for link in step['links']:
            def compare_link(link=link, source=source, target=target):
                source_seed = int(link['source_node_id'].split(':r')[1])
                target_seed = int(link['target_node_id'].split(':r')[1])
                left = set(source['members'][source_seed].tolist())
                right = set(target['members'][target_seed].tolist())
                common = left & right
                shared = fsum(float(weights[index]) for index in sorted(common))
                left_volume = fsum(float(weights[index]) for index in sorted(left))
                right_volume = fsum(float(weights[index]) for index in sorted(right))
                expected = dict(shared_cells=len(common), estimated_overlap_volume_km3=shared,
                                source_fraction=shared / left_volume, target_fraction=shared / right_volume,
                                overlap_coefficient=shared / min(left_volume, right_volume))
                for key, value in expected.items():
                    assert link[key] == value, f'{key}: {link[key]} != {value}'
                assert query.minimum_overlap <= expected['overlap_coefficient'] <= 1
                return expected
            check(f"Native set intersection {link['source_node_id']} to {link['target_node_id']}", compare_link)

    boundary_query = EvolutionQuery(start_index=0, end_index=1, sensitivity_delta=0,
                                    threshold=0, depth_min_m=100, depth_max_m=300)
    boundary = evolution.run('bay-bengal-2024-01', boundary_query)
    for frame in boundary['frames']:
        def contacts(frame=frame):
            assert len(frame['regions']) == 1
            node = frame['regions'][0]
            assert node['cell_bounds']['depth_min_m'] == 100
            assert node['cell_bounds']['depth_max_m'] == 300
            assert node['selection_depth_contacts'] == ['shallow', 'deep']
            assert 'shallow' not in node['boundary_contacts'] and 'deep' not in node['boundary_contacts']
            return dict(node_id=node['node_id'], cell_bounds=node['cell_bounds'],
                        native_boundary_contacts=node['boundary_contacts'],
                        selection_depth_contacts=node['selection_depth_contacts'])
        check(f"Requested depth contacts differ from native domain at frame {frame['time_index']}", contacts)

    paths = ('science/evolution.py', 'science/evolution_contracts.py', 'api/evolution_store.py',
             'science/features.py', 'science/verify_p14_links.py')
    report = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(), method=__doc__, method_version=result['method_version'],
                  case_id=case_id, query=query.model_dump(mode='json'),
                  model_manifest_sha256=result['manifest_sha256'],
                  observation_library_sha256=result['observation_library_sha256'],
                  result_sha256=fingerprint(result),
                  implementation_files_sha256={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths},
                  emitted_links_checked=sum(len(step['links']) for step in result['transitions']),
                  comparison_tolerance=0, source_summary=result['summary'],
                  checks=checks, passed_checks=sum(item['passed'] for item in checks),
                  failed_checks=sum(not item['passed'] for item in checks),
                  passed=bool(checks) and all(item['passed'] for item in checks),
                  limitations=[
                      'Expected links are recomputed from existing native memberships and geometry weights, not from an independent ocean dataset.',
                      'This check evaluates emitted link arithmetic; split/merge/gap/missing-support fixture checks are separate pytest acceptance.',
                      'Provider cell boundaries are unavailable. Reusing the existing geometry helper does not independently validate those volume estimates.',
                      'Agreement is not water-parcel identity, a forecast-skill result, observing-system impact or independent ocean validation.',
                      'UI, browser, HTTP transport, deployment and cross-platform replay are outside this checker.',
                  ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('passed', 'passed_checks', 'failed_checks', 'emitted_links_checked')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

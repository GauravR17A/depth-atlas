"""Original-source oracle acceptance for all 42 frame/threshold combinations.

The fixture is prepared offline with a separate decoder, SciPy components,
Decimal shell integration, set intersections and union-find groups. Expectations
are never taken from production evolution output.
"""
import hashlib
import json
from pathlib import Path

import pytest

from api.case_store import CaseStore
from api.evidence_store import EvidenceStore
from api.evolution_store import EvolutionStore
from api.feature_store import FeatureStore
from api.instrument_store import InstrumentStore
from science.evolution_contracts import EvolutionQuery


ROOT = Path(__file__).resolve().parents[1]
BODY = (ROOT/'tests/fixtures/p14-evolution-source-reference.json').read_bytes()
REFERENCE = json.loads(BODY)


@pytest.fixture(scope='module')
def store():
    cases = CaseStore(ROOT/'casepacks')
    instruments = InstrumentStore(ROOT/'casepacks/instruments')
    return EvolutionStore(FeatureStore(cases, instruments, EvidenceStore(cases, instruments)))


def test_independent_fixture_and_original_source_identities():
    assert hashlib.sha256(BODY).hexdigest() == '8d5137cd8e89a9e4966587ad11853607c3aa18c19a96075e3a586dd8dcc9941b'
    assert len(REFERENCE['sources']) == 14 and len(REFERENCE['scenarios']) == 6
    for row in REFERENCE['sources']:
        if not (ROOT/row['path']).is_file():
            pytest.skip("Original source archive is not bundled: " + row['path'])
        assert hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest() == row['sha256']


@pytest.mark.parametrize('expected', REFERENCE['scenarios'], ids=lambda value: f"{value['case_id']}-{value['threshold']}")
def test_all_source_memberships_and_correspondences_match_independent_oracle(store, expected):
    actual = store.run(expected['case_id'], EvolutionQuery(threshold=expected['threshold'], sensitivity_delta=0))
    assert len(actual['frames']) == len(expected['frames']) == 7
    for frame, oracle in zip(actual['frames'], expected['frames']):
        assert frame['time_index'] == oracle['time_index'] and frame['time'] == oracle['time']
        assert [r['node_id'] for r in frame['regions']] == [r['node_id'] for r in oracle['regions']]
        for region, reference in zip(frame['regions'], oracle['regions']):
            assert region['cell_count'] == reference['cell_count']
            assert region['membership_sha256'] == reference['membership_sha256']
            assert region['estimated_volume_km3'] == pytest.approx(reference['estimated_volume_km3'], rel=2e-12, abs=1e-10)
    for transition, oracle in zip(actual['transitions'], expected['transitions']):
        assert transition['status'] == 'compared' and transition['elapsed_hours'] == 12
        for key in ['from_time_index', 'to_time_index', 'disappeared_node_ids', 'appeared_node_ids', 'source_unresolved_node_ids', 'target_unresolved_node_ids']:
            assert transition[key] == oracle[key]
        actual_links = {(link['source_node_id'], link['target_node_id']): link for link in transition['links']}
        reference_links = {(link['source_node_id'], link['target_node_id']): link for link in oracle['links']}
        assert actual_links.keys() == reference_links.keys()
        for key, link in actual_links.items():
            reference = reference_links[key]
            assert link['classification'] == reference['classification']
            assert link['shared_cells'] == reference['shared_cells']
            assert link['estimated_overlap_volume_km3'] == pytest.approx(reference['estimated_overlap_volume_km3'], rel=2e-12, abs=1e-10)
            for field in ['source_fraction', 'target_fraction', 'overlap_coefficient']:
                assert link[field] == pytest.approx(reference[field], rel=2e-12, abs=2e-14)

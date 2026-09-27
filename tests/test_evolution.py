"""Independent set-overlap fixtures and checked-source evolution regressions."""
from copy import deepcopy
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
from threading import Barrier, Event, Lock

import numpy as np
import pytest
from pydantic import ValidationError

from api.case_store import CaseStore
from api.evidence_store import EvidenceStore
from api.evolution_store import EvolutionStore
from api.feature_store import FeatureStore
from api.instrument_store import InstrumentStore
from science.contracts import UnsupportedData
from science.evolution import region_contacts, region_statistics, summarize, transition
from science.evolution_contracts import EvolutionQuery, EvolutionRecipe
from science.investigations import fingerprint


ROOT = Path(__file__).resolve().parents[1]
BAY = 'bay-bengal-2024-01'
ARABIAN = 'arabian-sea-2024-01'


def make_store(root=ROOT/'casepacks'):
    cases = CaseStore(root)
    instruments = InstrumentStore(root/'instruments')
    evidence = EvidenceStore(cases, instruments)
    return EvolutionStore(FeatureStore(cases, instruments, evidence))


@pytest.fixture(scope='module')
def store():
    return make_store()


def frame(labels, index=0, hours=None, finite=None):
    labels = np.asarray(labels, dtype=np.int32)
    labels = labels.reshape((1,)*(3-labels.ndim) + labels.shape)
    members = {int(seed): np.flatnonzero(labels.ravel() == seed) for seed in np.unique(labels) if seed >= 0}
    timestamp = datetime(2024, 1, 7, tzinfo=timezone.utc) + timedelta(hours=12*index if hours is None else hours)
    return dict(time_index=index, time=timestamp.isoformat().replace('+00:00', 'Z'),
                labels=labels, members=members,
                finite=np.ones(labels.shape, dtype=bool) if finite is None else np.asarray(finite, dtype=bool).reshape(labels.shape))


def run(left, right, minimum=0.1, weights=None):
    weights = np.ones(left['labels'].shape) if weights is None else np.asarray(weights).reshape(left['labels'].shape)
    return transition(left, right, weights, minimum)


@pytest.mark.parametrize('change', [
    {'start_index': 2, 'end_index': 2}, {'start_index': 3, 'end_index': 2},
    {'start_index': -1}, {'end_index': 7}, {'start_index': True},
    {'frame_step': 0}, {'frame_step': 4}, {'minimum_overlap': 0},
    {'minimum_overlap': 1.01}, {'sensitivity_delta': -0.1},
    {'threshold': float('nan')}, {'sensitivity_delta': float('inf')},
    {'operator': 'between'}, {'operator': 'between', 'upper_threshold': 25},
    {'upper_threshold': 30}, {'depth_min_m': 300}, {'extra': 'ignored'},
])
def test_invalid_requests_rejected(change):
    with pytest.raises(ValidationError):
        EvolutionQuery(**change)


def test_shifted_between_interval_preserves_width_and_native_depths():
    query = EvolutionQuery(operator='between', threshold=26, upper_threshold=28, sensitivity_delta=0.25)
    for offset, expected in [(-0.25, (25.75, 27.75)), (0, (26, 28)), (0.25, (26.25, 28.25))]:
        q = query.feature_query(3, offset)
        assert (q.threshold, q.upper_threshold) == expected
        assert q.time_index == 3 and (q.depth_min_m, q.depth_max_m) == (0, 300)


def test_recipe_selection_must_belong_to_selected_frames():
    recipe = EvolutionRecipe(case_id=BAY, query=EvolutionQuery(frame_step=2), selected_node='t2:r10')
    assert recipe.selected_node == 't2:r10'
    with pytest.raises(ValidationError):
        EvolutionRecipe(case_id=BAY, query=EvolutionQuery(frame_step=2), selected_node='t1:r10')


def test_one_to_one_does_not_rely_on_same_region_id():
    out = run(frame([0, 0, -1]), frame([-1, 1, 1], 1))
    assert len(out['links']) == 1
    link = out['links'][0]
    assert (link['source_node_id'], link['target_node_id']) == ('t0:r0', 't1:r1')
    assert link['classification'] == 'continuation'
    assert link['source_fraction'] == link['target_fraction'] == link['overlap_coefficient'] == 0.5
    assert link['shared_cells'] == 1


def test_identical_frame_local_ids_do_not_create_false_correspondence():
    # Same smallest-cell seed, but only one third of either region overlaps.
    out = run(frame([[0, 0, 0], [-1, -1, -1], [-1, -1, -1]]),
              frame([[0, -1, -1], [0, -1, -1], [0, -1, -1]], 1), minimum=0.5)
    assert out['links'] == []
    assert out['disappeared_node_ids'] == ['t0:r0']
    assert out['appeared_node_ids'] == ['t1:r0']


def test_overlap_uses_estimated_volume_not_number_of_cells():
    # Two two-cell regions share the weight-1 cell: coefficient=1/min(10,5).
    out = run(frame([0, 0, -1]), frame([-1, 1, 1], 1), minimum=0.2, weights=[9, 1, 4])
    link = out['links'][0]
    assert link['shared_cells'] == 1 and link['estimated_overlap_volume_km3'] == 1
    assert link['source_fraction'] == 0.1 and link['target_fraction'] == link['overlap_coefficient'] == 0.2
    assert run(frame([0, 0, -1]), frame([-1, 1, 1], 1), minimum=np.nextafter(0.2, 1), weights=[9, 1, 4])['links'] == []


def test_split_and_merge_keep_every_branch():
    whole, parts = frame([0, 0, 0, 0, 0]), frame([0, 0, -1, 3, 3], 1)
    split = run(whole, parts)
    assert len(split['links']) == 2
    assert {link['classification'] for link in split['links']} == {'split'}
    assert split['split_count'] == 1 and split['merge_count'] == 0
    assert [link['source_fraction'] for link in split['links']] == [0.4, 0.4]
    assert [link['target_fraction'] for link in split['links']] == [1.0, 1.0]
    merged = run(frame([0, 0, -1, 3, 3]), frame([0, 0, 0, 0, 0], 1))
    assert len(merged['links']) == 2 and merged['merge_count'] == 1
    assert {link['classification'] for link in merged['links']} == {'merge'}


def test_many_to_many_component_remains_ambiguous_instead_of_greedy_track():
    # Two disconnected horizontal rows become two disconnected vertical
    # columns. All four corner intersections qualify, with equal 1/3 shares.
    out = run(frame([[0, 0, 0], [-1, -1, -1], [6, 6, 6]]),
              frame([[0, -1, 2], [0, -1, 2], [0, -1, 2]], 1))
    assert len(out['links']) == 4 and out['ambiguous_count'] == 1
    assert all(link['classification'] == 'ambiguous' for link in out['links'])
    assert set(out['ambiguous_node_ids']) == {'t0:r0', 't0:r6', 't1:r0', 't1:r2'}
    assert out['split_count'] == out['merge_count'] == 0


@pytest.mark.parametrize('index,hours', [(2, 24), (1, 24), (1, 6)])
def test_skipped_or_irregular_times_are_gaps_not_disappearances(index, hours):
    out = run(frame([0, 0]), frame([0, 0], index, hours=hours))
    assert out['status'] == 'gap' and out['links'] == []
    assert out['appeared_node_ids'] == out['disappeared_node_ids'] == []
    assert out['source_unresolved_node_ids'] == ['t0:r0']
    assert out['target_unresolved_node_ids'] == [f't{index}:r0']


@pytest.mark.parametrize('hours', [0, -12])
def test_non_increasing_source_times_rejected(hours):
    with pytest.raises(UnsupportedData, match='strictly increasing'):
        run(frame([0]), frame([0], 1, hours=hours))


def test_source_loss_is_unresolved_instead_of_disappearance():
    out = run(frame([0, 0, -1]), frame([-1, -1, -1], 1, finite=[False, True, True]))
    assert out['disappeared_node_ids'] == []
    assert out['source_unresolved_node_ids'] == out['ambiguous_node_ids'] == ['t0:r0']
    assert out['unmatched_details'] == [dict(node_id='t0:r0', relation='no_successor', reason='incomplete_support', missing_counterpart_cells=1)]


def test_new_support_is_unresolved_instead_of_appearance():
    out = run(frame([-1, -1], finite=[True, False]), frame([0, 0], 1))
    assert out['appeared_node_ids'] == []
    assert out['target_unresolved_node_ids'] == ['t1:r0']


def test_empty_fields_produce_truthful_empty_graph():
    out = run(frame([-1, -1]), frame([-1, -1], 1))
    assert out['status'] == 'compared'
    assert out['links'] == out['appeared_node_ids'] == out['disappeared_node_ids'] == []


def test_overlap_does_not_mutate_inputs_and_is_deterministic_after_json_roundtrip():
    left = frame([[0, 0, 0], [-1, -1, -1], [6, 6, 6]])
    right = frame([[0, -1, 2], [0, -1, 2], [0, -1, 2]], 1)
    before_left, before_right = deepcopy(left), deepcopy(right)
    weights = [1e-9, 1, 1e-5, 10000, 1, 2, 3, 4, 5]
    result = run(left, right, weights=weights)
    assert fingerprint(result) == fingerprint(json.loads(json.dumps(result)))
    assert result == run(left, right, weights=weights)
    for original, saved in ((left, before_left), (right, before_right)):
        assert np.array_equal(original['labels'], saved['labels'])
        assert np.array_equal(original['finite'], saved['finite'])
        assert all(np.array_equal(original['members'][k], v) for k, v in saved['members'].items())


def test_more_than_fifty_regions_are_compared_without_truncation():
    labels = np.full(119, -1)
    labels[::2] = np.arange(0, 119, 2)
    result = run(frame(labels), frame(labels, 1))
    assert len(result['links']) == 60
    assert result['links'][-1]['source_node_id'] == 't0:r118'


def test_boundary_and_missing_neighbour_contacts_are_explicit():
    finite = np.ones((3, 3, 3), dtype=bool)
    finite[1, 1, 2] = False
    interior = region_contacts(np.array([13]), finite.shape, finite)
    assert interior == dict(boundary_contacts=[], touches_domain_boundary=False, touches_missing_values=True)
    boundary = region_contacts(np.array([0]), finite.shape, finite)
    assert boundary['boundary_contacts'] == ['shallow', 'south', 'west']


def test_ordered_region_volume_recovers_low_bits_lost_by_numpy_reduction():
    # Arithmetic fixture only. Two unit cells must survive beside the large
    # cell after compensated summation, without rounding the final output.
    weights = np.array([1e16, 1.0, 1.0])
    expected = 10000000000000002.0
    assert float(np.sum(weights)) != expected
    result = region_statistics(np.ones(3), weights, np.array([0, 1, 2]))
    assert result['estimated_volume_km3'] == expected
    assert result['mean'] == result['volume_weighted_mean'] == 1.0


def test_ordered_region_means_preserve_cancelled_small_value_and_membership_order():
    values, weights = np.array([1e16, 1.0, -1e16]), np.ones(3)
    assert float(np.mean(values)) == 0.0
    forward = region_statistics(values, weights, np.array([0, 1, 2]))
    reverse = region_statistics(values, weights, np.array([2, 1, 0]))
    assert forward == reverse
    assert forward == dict(estimated_volume_km3=3.0, mean=1/3, volume_weighted_mean=1/3)
    assert np.array_equal(values, np.array([1e16, 1.0, -1e16]))
    assert np.array_equal(weights, np.ones(3))


def test_ordered_region_statistics_uses_native_cells_only_and_rejects_empty_membership():
    result = region_statistics(np.array([10., 999., 20.]), np.array([1., 99., 3.]), np.array([0, 2]))
    assert result == dict(estimated_volume_km3=4.0, mean=15.0, volume_weighted_mean=17.5)
    with pytest.raises(UnsupportedData, match='at least one'):
        region_statistics(np.ones(1), np.ones(1), np.array([], dtype=int))


@pytest.fixture(scope='module')
def real_arabian(store):
    return store.run(ARABIAN, EvolutionQuery())


def test_actual_source_frames_and_membership_are_exact_p07_reuse(store, real_arabian):
    result = real_arabian
    assert [f['total_regions'] for f in result['frames']] == [2, 1, 7, 1, 5, 3, 2]
    assert [f['qualified_cells'] for f in result['frames']] == [66722, 70174, 68749, 69672, 68118, 68694, 67739]
    for frame_data in result['frames']:
        native, values, _ = store.features.prepared(ARABIAN, EvolutionQuery().feature_query(frame_data['time_index']))
        expected = {r['id']: r for r in native['regions']}
        for region in frame_data['regions']:
            for key, value in expected[region['id']].items():
                if key in {'estimated_volume_km3', 'mean', 'volume_weighted_mean'}:
                    # P14 v2 owns its reduction arithmetic; the same native
                    # cells still agree numerically with the unchanged P07.
                    assert region[key] == pytest.approx(value, rel=2e-12, abs=1e-10)
                else:
                    assert region[key] == value
            indices = native['members'][int(region['id'][1:])]
            assert region['membership_sha256'] == hashlib.sha256(indices.astype('<i8').tobytes()).hexdigest()
            assert region['footprint_indices'] == sorted({int(i) % (76*63) for i in indices})
    assert result['summary']['split_count'] == result['summary']['merge_count'] == 2
    assert result['summary']['disappearance_count'] == 3
    assert result['summary']['link_count'] == 26


def test_actual_threshold_sensitivity_is_recomputed_not_styled(real_arabian):
    assert [run['threshold'] for run in real_arabian['sensitivity']] == [25.75, 26, 26.25]
    assert [run['summary']['node_count'] for run in real_arabian['sensitivity']] == [10, 21, 15]
    base = real_arabian['sensitivity'][1]
    assert base['summary'] == real_arabian['summary']
    assert [f['estimated_volume_km3'] for f in base['frames']] == [f['estimated_volume_km3'] for f in real_arabian['frames']]


def test_source_library_and_model_fingerprints_are_complete(store, real_arabian):
    assert real_arabian['manifest_sha256'] == store.features.cases.require(ARABIAN)[1]
    assert real_arabian['observation_library_sha256'] == store.features.evidence.library_sha_for(ARABIAN)
    assert real_arabian['method_version'] == 'p14-native-overlap-v2'
    assert fingerprint(real_arabian) == fingerprint(json.loads(json.dumps(real_arabian)))


def test_source_gap_selection_does_not_bridge_and_sensitivity_can_be_disabled(store):
    result = store.run(BAY, EvolutionQuery(frame_step=2, sensitivity_delta=0))
    assert [f['time_index'] for f in result['frames']] == [0, 2, 4, 6]
    assert result['summary']['gap_count'] == 3 and result['summary']['link_count'] == 0
    assert len(result['sensitivity']) == 1 and result['sensitivity'][0]['offset'] == 0


@pytest.mark.parametrize('case_id,query,code', [
    ('pacific-godas-2015-son', {}, 'unsupported_evolution_case'),
    ('../other', {}, 'unsupported_evolution_case'),
    (BAY, {'units': 'K'}, 'incompatible_units'),
])
def test_unsupported_source_or_scientific_request_rejected(store, case_id, query, code):
    with pytest.raises(UnsupportedData) as caught:
        store.run(case_id, EvolutionQuery(**query))
    assert caught.value.code == code


def test_requested_depth_contacts_differ_from_original_source_boundaries(store):
    query = EvolutionQuery(threshold=0, depth_min_m=100, depth_max_m=300, start_index=0, end_index=1, sensitivity_delta=0)
    result = store.run(BAY, query)
    for frame_data in result['frames']:
        region = frame_data['regions'][0]
        assert region['selection_depth_contacts'] == ['shallow', 'deep']
        assert 'shallow' not in region['boundary_contacts'] and 'deep' not in region['boundary_contacts']
        assert region['cell_bounds']['depth_min_m'] == 100
        assert region['cell_bounds']['depth_max_m'] == 300
        native = store.features.prepared(BAY, query.feature_query(frame_data['time_index']))[0]['regions'][0]
        assert region['cell_count'] == native['cell_count']
        assert region['membership_sha256'] == native['membership_sha256']
        assert region['estimated_volume_km3'] == pytest.approx(native['estimated_volume_km3'], rel=2e-12, abs=1e-10)


def test_stored_feature_cache_is_not_mutated_by_enrichment(store):
    query = EvolutionQuery(start_index=0, end_index=1, sensitivity_delta=0)
    before = deepcopy(store.features.prepared(BAY, query.feature_query(0))[0]['regions'])
    store.run(BAY, query)
    after = store.features.prepared(BAY, query.feature_query(0))[0]['regions']
    assert before == after and 'node_id' not in after[0]


def test_repeated_real_query_reuses_calculation_but_revalidates_sources(monkeypatch):
    local = make_store()
    computations, validations = [], []
    compute, sources = local._compute, local._sources
    def counted_compute(*arguments):
        computations.append(1)
        return compute(*arguments)
    def counted_sources(*arguments):
        validations.append(1)
        return sources(*arguments)
    monkeypatch.setattr(local, '_compute', counted_compute)
    monkeypatch.setattr(local, '_sources', counted_sources)
    query = EvolutionQuery(start_index=0, end_index=1, sensitivity_delta=0)
    # Run/capture/replay/export each call the same run operation.
    expected = local.run(BAY, query)
    changed = local.run(BAY, query)
    changed['frames'][0]['regions'][0]['observations'].append({'changed': True})
    changed['query']['threshold'] = -100
    assert local.run(BAY, query) == expected
    assert local.run(BAY, query) == expected
    assert len(computations) == 1 and len(validations) == 4
    assert len(local._results) == 1 and local._inflight == {}


def test_duplicate_concurrent_requests_share_one_calculation_and_isolated_results(monkeypatch):
    local = EvolutionStore(None)
    barrier, waiting, release = Barrier(6), Event(), Event()
    guard = Lock()
    counts = dict(sources=0, calculations=0, waiters=0)
    class ObservedFuture(Future):
        def result(self, timeout=None):
            with guard:
                counts['waiters'] += 1
                if counts['waiters'] == 5:
                    waiting.set()
            return super().result(timeout)
    def source(*_):
        with guard:
            counts['sources'] += 1
        barrier.wait(timeout=10)
        return None, 'model-sha', 'library-sha'
    def compute(*_):
        with guard:
            counts['calculations'] += 1
        assert release.wait(timeout=10)
        return {'nested': {'members': [1, 2, 3]}}
    monkeypatch.setattr('api.evolution_store.Future', ObservedFuture)
    monkeypatch.setattr(local, '_sources', source)
    monkeypatch.setattr(local, '_compute', compute)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(local.run, BAY, EvolutionQuery()) for _ in range(6)]
        try:
            assert waiting.wait(timeout=10)
        finally:
            release.set()
        outputs = [future.result(timeout=10) for future in futures]
    assert counts == dict(sources=6, calculations=1, waiters=5)
    assert all(output == outputs[0] for output in outputs)
    outputs[0]['nested']['members'].append(99)
    assert all(output['nested']['members'] == [1, 2, 3] for output in outputs[1:])
    assert local._inflight == {} and len(local._results) == 1


def test_result_cache_is_lru_bounded_and_source_identity_is_part_of_key(monkeypatch):
    local = EvolutionStore(None)
    identity = ['model-1', 'library-1']
    calls = []
    monkeypatch.setattr(local, '_sources', lambda *_: (None, *identity))
    def compute(case_id, query, manifest, model_sha, library_sha):
        calls.append((query.threshold, model_sha, library_sha))
        return dict(threshold=query.threshold, model_sha=model_sha, library_sha=library_sha)
    monkeypatch.setattr(local, '_compute', compute)
    for threshold in range(26, 34):
        local.run(BAY, EvolutionQuery(threshold=threshold))
    assert len(calls) == len(local._results) == 8
    local.run(BAY, EvolutionQuery(threshold=26))  # Refresh the original LRU entry.
    local.run(BAY, EvolutionQuery(threshold=34))
    local.run(BAY, EvolutionQuery(threshold=26))
    assert len(calls) == 9 and len(local._results) == 8
    local.run(BAY, EvolutionQuery(threshold=27))  # The least-used entry was evicted.
    assert len(calls) == 10 and len(local._results) == 8
    identity[1] = 'library-2'
    local.run(BAY, EvolutionQuery(threshold=27))
    identity[0] = 'model-2'
    local.run(BAY, EvolutionQuery(threshold=27))
    assert len(calls) == 12 and len(local._results) == 8


def test_failed_calculation_is_not_cached_and_duplicate_state_is_released(monkeypatch):
    local = EvolutionStore(None)
    calls = []
    monkeypatch.setattr(local, '_sources', lambda *_: (None, 'model', 'library'))
    def compute(*_):
        calls.append(1)
        if len(calls) == 1:
            raise UnsupportedData('test_failure', 'Explicit arithmetic test failure')
        return {'recovered': True}
    monkeypatch.setattr(local, '_compute', compute)
    with pytest.raises(UnsupportedData, match='arithmetic test failure'):
        local.run(BAY, EvolutionQuery())
    assert local._inflight == {} and len(local._results) == 0
    assert local.run(BAY, EvolutionQuery()) == {'recovered': True}
    assert len(calls) == 2 and local._inflight == {}


def test_copied_query_cannot_bypass_revalidation(store):
    invalid = EvolutionQuery().model_copy(update={'minimum_overlap': 0})
    with pytest.raises(ValidationError):
        store.run(BAY, invalid)


@pytest.mark.parametrize('target', ['manifest', 'array', 'profile', 'index', 'missing_array'])
def test_cached_sources_cannot_hide_on_disk_tampering(tmp_path, target):
    root = tmp_path/'casepacks'
    shutil.copytree(ROOT/'casepacks'/BAY, root/BAY)
    source = ROOT/'casepacks'/'instruments'
    destination = root/'instruments'
    destination.mkdir()
    index = json.loads((source/'index.json').read_text(encoding='utf8'))
    for filename in ['index.json', *[p['id']+'.json' for p in index['profiles']]]:
        shutil.copy2(source/filename, destination/filename)
    local = make_store(root)
    query = EvolutionQuery(start_index=0, end_index=1, sensitivity_delta=0)
    local.run(BAY, query)
    path = {
        'manifest': root/BAY/'manifest.json',
        'array': root/BAY/'analytical/temperature-0.bin.gz',
        'missing_array': root/BAY/'analytical/temperature-0.bin.gz',
        'profile': destination/(index['profiles'][0]['id']+'.json'),
        'index': destination/'index.json',
    }[target]
    if target == 'missing_array':
        path.unlink()
    elif target == 'index':
        changed = json.loads(path.read_text(encoding='utf8'))
        changed['profiles'][0]['title'] += ' changed'
        path.write_text(json.dumps(changed), encoding='utf8')
    else:
        path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(UnsupportedData) as caught:
        local.run(BAY, query)
    assert caught.value.code == 'case_integrity_error'

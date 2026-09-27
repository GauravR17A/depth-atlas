"""Independent counting fixtures and real-library immutability for P14.

Small invented comparison rows below are arithmetic test inputs, never app data.
Real counts/statistics come from P05's independently checked original-source cases.
"""
from collections import Counter
from math import sqrt
from pathlib import Path
import json
import shutil

import pytest
from pydantic import ValidationError

from api.blackout_store import BlackoutStore
from api.case_store import CASE_ID, CaseStore
from api.evidence_store import EvidenceStore
from api.instrument_store import InstrumentStore
from science.blackout import analyze_blackout, resolve_exclusions
from science.blackout_contracts import BlackoutQuery, BlackoutRecipe
from science.contracts import UnsupportedData
from science.evidence_contracts import Comparison, Coverage, CoverageProfile, MatchRow, MatchSettings, SampleMetrics
from science.instruments import InstrumentSummary
from science.investigations import fingerprint

ROOT = Path(__file__).resolve().parents[1]


def fixture_metrics(residuals):
    """Independent hand-small arithmetic, not the production metrics helper."""
    return SampleMetrics(count=len(residuals), bias=sum(residuals) / len(residuals) if residuals else None,
                         rmse=sqrt(sum(value ** 2 for value in residuals) / len(residuals)) if residuals else None,
                         mae=sum(abs(value) for value in residuals) / len(residuals) if residuals else None,
                         maximum_abs_residual=max(map(abs, residuals)) if residuals else None)


@pytest.fixture
def arithmetic():
    settings = MatchSettings()
    comparisons, coverage_profiles = [], []
    for identity, instrument, platform, collection, row_values in [
        ('test-a', 'argo', 'float-a', 'Test floats', [(11, -1), (22, None), (37, 3)]),
        ('test-b', 'argo', 'float-b', 'Test floats', [(8, -2), (9, None)]),
        ('test-c', 'ctd', 'ship-c', 'Test ships', [(0, None), (6, None)]),
    ]:
        profile = InstrumentSummary(id=identity, instrument=instrument, platform=platform, collection=collection,
                                    title='Synthetic arithmetic test, never deployed', time='2024-01-07T12:00:00Z',
                                    time_end='2024-01-07T12:00:00Z', latitude=15, longitude=85,
                                    samples=len(row_values), depth_range_m=(10, 30), parameters={},
                                    source_url='https://example.invalid/fixture', source_file='fixture', source_sha256='c' * 64)
        rows = [MatchRow(sample_index=index, observation_time=profile.time, latitude=15, longitude=85,
                         depth_m=10, observed=20, model=20 + residual if residual is not None else None,
                         residual=residual, accepted=residual is not None,
                         reason='accepted' if residual is not None else 'observation_qc',
                         qc='1' if residual is not None else '4', mode='D', time_offset_hours=0)
                for index, residual in row_values]
        residuals = [residual for _, residual in row_values if residual is not None]
        stats = fixture_metrics(residuals)
        counts = {'observation_qc': len(rows) - len(residuals)}
        comparisons.append(Comparison(case_id='synthetic-test-only', manifest_sha256='a' * 64,
                                      observation_library_sha256='b' * 64, model_time=profile.time,
                                      profile=profile, settings=settings, units='°C', total_samples=len(rows),
                                      matched_count=len(residuals), excluded_count=len(rows) - len(residuals),
                                      exclusion_counts=counts, metrics=stats, rows=rows, methods=[], caveats=[]))
        coverage_profiles.append(CoverageProfile(profile=profile, total_samples=len(rows), matched_count=len(residuals),
                                  excluded_count=len(rows) - len(residuals), exclusion_counts=counts,
                                  eligible_depths_m=[10] * len(residuals), time_offset_hours_min=0, time_offset_hours_max=0,
                                  minimum_abs_time_offset_hours=0 if residuals else None, distance_km_min=0 if residuals else None,
                                  distance_km_max=0 if residuals else None, metrics=stats, suggested_time_index=None,
                                  suggested_matched_count=0, suggested_time_offset_hours=None, suggested_distance_km=None))
    baseline = Coverage(case_id='synthetic-test-only', manifest_sha256='a' * 64, observation_library_sha256='b' * 64,
                        model_time='2024-01-07T12:00:00Z', settings=settings, total_profiles=3, matched_profiles=2,
                        total_samples=7, matched_samples=3, excluded_samples=4, exclusion_counts={'observation_qc': 4},
                        profiles=coverage_profiles, methods=[], caveats=[])
    return baseline, comparisons


@pytest.fixture(scope='module')
def store():
    return BlackoutStore(EvidenceStore(CaseStore(ROOT / 'casepacks'), InstrumentStore(ROOT / 'casepacks/instruments')))


def run_fixture(arithmetic, **selections):
    return analyze_blackout(*arithmetic, BlackoutQuery(**selections))


def test_empty_selection_reproduces_original_and_independent_statistics(arithmetic):
    result = run_fixture(arithmetic)
    assert result.baseline == result.modified == arithmetic[0]
    assert result.removed_profiles == result.removed_eligible_samples == result.removed_samples == 0
    assert result.baseline_metrics.count == 3
    assert result.baseline_metrics.bias == 0
    assert result.baseline_metrics.rmse == sqrt(14 / 3)
    assert result.baseline_metrics.mae == 2
    assert result.baseline_metrics == result.modified_metrics
    assert not any(statement.changed for statement in result.statements)


def test_remove_profile_recomputes_counts_statistics_and_exact_source_indices(arithmetic):
    result = run_fixture(arithmetic, excluded_profile_ids=['test-a'])
    assert result.removed_profiles == result.removed_eligible_profiles == 1
    assert result.removed_samples == 3
    assert result.removed_eligible_samples == 2
    assert result.modified.total_profiles == 2
    assert result.modified.total_samples == 4
    assert result.modified.matched_profiles == result.modified.matched_samples == 1
    assert result.modified.excluded_samples == 3
    assert result.modified.exclusion_counts == {'observation_qc': 3}
    assert result.modified_metrics == fixture_metrics([-2])
    effect = result.profile_effects[0]
    assert effect.removed_sample_indices == [11, 37]
    assert effect.selected_by == ['profile:test-a']
    assert effect.original_metrics == fixture_metrics([-1, 3])
    changed = {statement.id for statement in result.statements if statement.changed}
    assert changed == {'eligible_profiles', 'eligible_samples', 'residual_statistics'}


def test_ineligible_profile_removal_leaves_scientific_evidence_identical(arithmetic):
    result = run_fixture(arithmetic, excluded_profile_ids=['test-c'])
    assert result.removed_profiles == 1 and result.removed_samples == 2
    assert result.removed_eligible_profiles == result.removed_eligible_samples == 0
    assert result.modified_metrics == result.baseline_metrics
    assert result.modified.matched_profiles == result.baseline.matched_profiles
    assert result.modified.matched_samples == result.baseline.matched_samples
    assert not any(statement.changed for statement in result.statements)
    assert result.profile_effects[2].removed_sample_indices == []


@pytest.mark.parametrize('selection', [
    {'excluded_profile_ids': ['test-a', 'test-b']},
    {'excluded_instruments': ['argo']},
    {'excluded_platforms': ['float-a', 'float-b']},
    {'excluded_collections': ['Test floats']},
    {'excluded_profile_ids': ['test-a'], 'excluded_instruments': ['argo'], 'excluded_platforms': ['float-a']},
])
def test_groups_resolve_the_same_union_without_double_counting(arithmetic, selection):
    result = run_fixture(arithmetic, **selection)
    assert result.excluded_profile_ids == ['test-a', 'test-b']
    assert result.removed_profiles == result.removed_eligible_profiles == 2
    assert result.removed_eligible_samples == 3
    assert result.modified.matched_samples == 0
    assert result.modified.total_profiles == 1
    assert result.modified_metrics == fixture_metrics([])


def test_remove_all_keeps_source_gate_rejections_separate_from_user_removal(arithmetic):
    result = run_fixture(arithmetic, excluded_instruments=['ctd', 'argo'])
    assert result.modified.profiles == []
    assert result.modified.total_samples == result.modified.matched_samples == result.modified.excluded_samples == 0
    assert result.modified.exclusion_counts == {}
    assert result.removed_samples == 7 and result.removed_eligible_samples == 3
    assert result.baseline.exclusion_counts == {'observation_qc': 4}
    assert result.model_unchanged and result.source_qc_unchanged
    assert all(effect.excluded_by_user for effect in result.profile_effects)


@pytest.mark.parametrize('selection', [
    {'excluded_profile_ids': ['missing']}, {'excluded_instruments': ['glider']},
    {'excluded_platforms': ['missing']}, {'excluded_collections': ['missing']},
])
def test_unknown_group_is_rejected_not_silently_ignored(arithmetic, selection):
    with pytest.raises(UnsupportedData) as error:
        run_fixture(arithmetic, **selection)
    assert error.value.code == 'unknown_blackout_selection'


def test_selection_order_and_duplicates_have_one_normalized_recipe():
    first = BlackoutQuery(excluded_profile_ids=['b', 'a', 'a'], excluded_instruments=['ctd', 'argo', 'argo'],
                         excluded_platforms=['c', 'b', 'c'], excluded_collections=['two', 'one', 'two'])
    second = BlackoutQuery(excluded_profile_ids=['a', 'b'], excluded_instruments=['argo', 'ctd'],
                          excluded_platforms=['b', 'c'], excluded_collections=['one', 'two'])
    assert first == second
    assert fingerprint(BlackoutRecipe(case_id=CASE_ID, query=first).model_dump(mode='json')) == fingerprint(
        BlackoutRecipe(case_id=CASE_ID, query=second).model_dump(mode='json'))


@pytest.mark.parametrize('arguments', [
    {'excluded_profile_ids': ['']}, {'excluded_profile_ids': ['x' * 257]},
    {'excluded_profile_ids': [str(n) for n in range(129)]}, {'excluded_platforms': [str(n) for n in range(129)]},
    {'excluded_collections': [str(n) for n in range(65)]}, {'excluded_instruments': ['unknown']},
    {'settings': {'time_index': 7}}, {'unknown': True},
])
def test_malformed_or_unbounded_queries_rejected(arguments):
    with pytest.raises(ValidationError):
        BlackoutQuery(**arguments)


def test_pure_results_do_not_share_mutable_source_or_result_state(arithmetic):
    coverage_json = arithmetic[0].model_dump_json()
    comparison_json = [item.model_dump_json() for item in arithmetic[1]]
    result = run_fixture(arithmetic, excluded_profile_ids=['test-a'])
    result.baseline.profiles[1].profile.title = 'Changed output only'
    result.baseline.profiles[1].metrics.bias = 999
    result.profile_effects[1].original_metrics.bias = 999
    result.modified.profiles[0].profile.parameters['new'] = None
    assert arithmetic[0].model_dump_json() == coverage_json
    assert [item.model_dump_json() for item in arithmetic[1]] == comparison_json
    rerun = run_fixture(arithmetic, excluded_profile_ids=['test-a'])
    assert rerun.modified_metrics.bias == -2
    assert rerun.modified.profiles[0].profile.title != 'Changed output only'


@pytest.mark.parametrize('mutation', ['missing_profile', 'duplicate_profile', 'settings', 'source', 'counts'])
def test_inconsistent_evidence_is_rejected(arithmetic, mutation):
    baseline, comparisons = arithmetic
    if mutation == 'missing_profile':
        comparisons.pop()
    elif mutation == 'duplicate_profile':
        comparisons.append(comparisons[0])
    elif mutation == 'settings':
        baseline.settings = MatchSettings(time_index=0)
    elif mutation == 'source':
        comparisons[0].manifest_sha256 = 'z' * 64
    else:
        comparisons[0].matched_count = 100
    with pytest.raises(UnsupportedData) as error:
        run_fixture((baseline, comparisons))
    assert error.value.code == 'blackout_integrity_error'


def test_real_source_counts_and_retained_profile_statistics(store):
    result = store.run(CASE_ID, BlackoutQuery(excluded_platforms=['1902669']))
    assert result['baseline']['matched_profiles'] == 2
    assert result['baseline']['matched_samples'] == 206
    assert result['modified']['matched_profiles'] == 1
    assert result['modified']['matched_samples'] == 103
    assert result['modified_metrics']['bias'] == pytest.approx(0.22138630145783464, abs=1e-11)
    assert result['modified_metrics']['rmse'] == pytest.approx(0.6969605907674252, abs=1e-11)
    assert result['modified_metrics']['mae'] == pytest.approx(0.4611977603130188, abs=1e-11)
    effect = next(item for item in result['profile_effects'] if item['excluded_by_user'])
    assert len(effect['removed_sample_indices']) == 103
    reference = store.evidence.comparison(CASE_ID, effect['profile_id'], MatchSettings())
    assert effect['removed_sample_indices'] == [row.sample_index for row in reference.rows if row.accepted]


@pytest.mark.parametrize('variable', ['temperature', 'salinity'])
def test_real_model_arrays_qc_and_cached_evidence_are_unchanged(store, variable):
    settings = MatchSettings(variable=variable)
    baseline = store.evidence.coverage(CASE_ID, settings)
    original = baseline.model_dump_json()
    values = store.evidence.cases._read_array(CASE_ID, 'analytical', variable, settings.time_index)
    before_array = values.tobytes() if hasattr(values, 'tobytes') else list(values)
    source_profiles = {item.profile.id: store.evidence.instruments.read(item.profile.id).model_dump_json()
                       for item in baseline.profiles}
    original_comparisons = {item.profile.id: store.evidence.comparison(CASE_ID, item.profile.id, settings).model_dump_json()
                            for item in baseline.profiles}
    result = store.run(CASE_ID, BlackoutQuery(settings=settings, excluded_instruments=['argo']))
    result['baseline']['profiles'][0]['profile']['title'] = 'Output mutation cannot contaminate cache'
    result['modified']['exclusion_counts']['user_removed'] = 999
    assert store.evidence.coverage(CASE_ID, settings).model_dump_json() == original
    after_array = values.tobytes() if hasattr(values, 'tobytes') else list(values)
    assert after_array == before_array
    assert source_profiles == {identity: store.evidence.instruments.read(identity).model_dump_json() for identity in source_profiles}
    assert original_comparisons == {identity: store.evidence.comparison(CASE_ID, identity, settings).model_dump_json()
                                    for identity in original_comparisons}
    rerun = store.run(CASE_ID, BlackoutQuery(settings=settings))
    assert rerun['baseline'] == rerun['modified']


def test_real_ineligible_instrument_removal_changes_no_eligible_evidence(store):
    result = store.run(CASE_ID, BlackoutQuery(excluded_instruments=['glider']))
    assert result['removed_profiles'] == 4
    assert result['removed_eligible_samples'] == result['removed_eligible_profiles'] == 0
    assert result['baseline_metrics'] == result['modified_metrics']
    assert not any(item['changed'] for item in result['statements'])


@pytest.mark.parametrize('case_id', ['pacific-godas-2013-son', 'pacific-godas-2015-son', 'pacific-godas-2022-son'])
def test_monthly_potential_temperature_stays_incompatible_with_instantaneous_observations(store, case_id):
    result = store.run(case_id, BlackoutQuery(excluded_instruments=['argo']))
    assert result['baseline']['matched_samples'] == result['modified']['matched_samples'] == 0
    assert result['removed_eligible_samples'] == 0
    assert result['baseline']['exclusion_counts'].get('incompatible_variable', 0) > 0
    assert result['baseline_metrics']['bias'] is None
    assert any('not interchangeable' in item for item in result['caveats'])


@pytest.mark.parametrize('settings,code', [(MatchSettings(time_index=6), 'unsupported_time'),
                                        (MatchSettings(variable='salinity'), 'unsupported_variable')])
def test_unavailable_pacific_time_or_variable_rejected_before_work(store, settings, code):
    with pytest.raises(UnsupportedData) as error:
        store.run('pacific-godas-2015-son', BlackoutQuery(settings=settings))
    assert error.value.code == code


def test_repeated_runs_and_reordered_queries_have_identical_portable_fingerprints(store):
    query = BlackoutQuery(excluded_instruments=['ctd', 'glider'], excluded_platforms=['1902669'])
    first = store.run(CASE_ID, query)
    second = store.run(CASE_ID, BlackoutQuery(excluded_platforms=['1902669', '1902669'], excluded_instruments=['glider', 'ctd']))
    assert fingerprint(first) == fingerprint(second)
    assert first == second


def test_catalog_exposes_only_exact_selectable_case_groups(store):
    result = store.catalog(CASE_ID)
    known = {item['id']: item for item in result['profiles']}
    assert len(result['model_times']) == 7
    assert result['default_query'] == BlackoutQuery().model_dump(mode='json')
    for field, groups in result['groups'].items():
        assert [group['id'] for group in groups] == sorted(group['id'] for group in groups)
        for group in groups:
            assert group['profile_ids'] == sorted(identity for identity, profile in known.items() if profile[field] == group['id'])


def test_budget_refuses_excessive_library_before_comparison(store, monkeypatch):
    sample = store.evidence.instruments.catalog(CASE_ID)['profiles'][0]
    monkeypatch.setattr(store.evidence.instruments, 'catalog', lambda _: {'profiles': [sample] * 129})
    with pytest.raises(UnsupportedData) as error:
        store.run(CASE_ID, BlackoutQuery())
    assert error.value.code == 'blackout_budget_exceeded'


@pytest.fixture(scope='module')
def disposable_store(tmp_path_factory):
    """Corruption tests use disposable copies, never the deployed source pack."""
    target = tmp_path_factory.mktemp('blackout-source-integrity')
    (target / CASE_ID).mkdir()
    shutil.copy2(ROOT / 'casepacks' / CASE_ID / 'manifest.json', target / CASE_ID / 'manifest.json')
    shutil.copytree(ROOT / 'casepacks' / CASE_ID / 'analytical', target / CASE_ID / 'analytical')
    (target / 'instruments').mkdir()
    for item in (ROOT / 'casepacks/instruments').glob('*.json'):
        shutil.copy2(item, target / 'instruments' / item.name)
    return BlackoutStore(EvidenceStore(CaseStore(target), InstrumentStore(target / 'instruments')))


@pytest.mark.parametrize('relative', [
    f'{CASE_ID}/manifest.json', f'{CASE_ID}/analytical/temperature-1.bin.gz',
    f'{CASE_ID}/analytical/temperature-3.bin.gz', 'instruments/index.json',
    'instruments/argo-1902669-12-0-1c4592fce4.json',
])
def test_warmed_evidence_cache_does_not_hide_changed_source_files(disposable_store, relative):
    original_result = disposable_store.run(CASE_ID, BlackoutQuery())
    path = disposable_store.evidence.cases.root / relative
    original_bytes = path.read_bytes()
    try:
        if relative == 'instruments/index.json':
            changed = json.loads(original_bytes)
            changed['profiles'][0]['title'] = 'Changed source identity'
            path.write_text(json.dumps(changed), encoding='utf-8')
        else:
            path.write_bytes(original_bytes + b' ')
        with pytest.raises(UnsupportedData) as error:
            disposable_store.run(CASE_ID, BlackoutQuery(excluded_instruments=['argo']))
        assert error.value.code == 'case_integrity_error'
    finally:
        path.write_bytes(original_bytes)
    assert disposable_store.run(CASE_ID, BlackoutQuery()) == original_result


def test_warmed_cache_does_not_hide_missing_source(disposable_store):
    disposable_store.run(CASE_ID, BlackoutQuery())
    path = disposable_store.evidence.cases.root / CASE_ID / 'analytical/temperature-1.bin.gz'
    original_bytes = path.read_bytes()
    try:
        path.unlink()
        with pytest.raises(UnsupportedData) as error:
            disposable_store.run(CASE_ID, BlackoutQuery())
        assert error.value.code == 'case_integrity_error'
    finally:
        path.write_bytes(original_bytes)

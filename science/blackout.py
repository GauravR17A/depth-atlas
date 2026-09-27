"""Pure, deterministic evidence subset analysis. No model or QC mutation."""
from collections import Counter

from science.blackout_contracts import BlackoutResult, EvidenceStatement, ProfileEffect
from science.contracts import UnsupportedData
from science.evidence import metrics

METHODS = [
    'Calculate the original evidence using the unchanged source, QC, quantity, time, distance and native-depth comparison rules.',
    'Resolve the union of explicitly selected profile IDs, instrument types, platform IDs and collection names within this case library. Duplicate selections remove a profile once.',
    'Remove whole selected profiles from the available evidence. Original source quality flags, first-failed matching reasons, model cells and residuals for retained samples are unchanged.',
    'Recompute coverage counts and equal-sample residual statistics from the retained eligible comparisons. Source sample indices identify exactly which eligible pairs were removed.',
    'Keep user exclusions separate from source/QC and matching exclusions. Empty selections reproduce the original evidence; excluding an already ineligible profile removes no eligible pair.',
]
CAVEATS = [
    'The ocean model has not been rerun. This exercise removes observations from the evidence view, not from the original data assimilation system.',
    'A change in residual statistics describes the selected remaining samples. It does not measure forecast improvement, observing-system impact or calibrated confidence.',
    'A removed profile may already have no eligible samples under these settings. In that case eligible evidence and its statistics do not change.',
    'Coverage counts are not independent sample counts, ocean-area coverage or evidence about unsampled places.',
]


def resolve_exclusions(profiles, query):
    """Validate all names before resolving a deterministic union of groups."""
    selectors = (
        ('profile', 'id', query.excluded_profile_ids),
        ('instrument', 'instrument', query.excluded_instruments),
        ('platform', 'platform', query.excluded_platforms),
        ('collection', 'collection', query.excluded_collections),
    )
    for label, field, choices in selectors:
        known = {getattr(profile, field) for profile in profiles}
        if not set(choices).issubset(known):
            raise UnsupportedData('unknown_blackout_selection',
                                  f'An excluded {label} is not in the selected case observation library. Refresh the selections.')
    selected = {}
    for profile in profiles:
        matched = [f'{label}:{getattr(profile, field)}' for label, field, choices in selectors
                   if getattr(profile, field) in choices]
        if matched:
            selected[profile.id] = matched
    return selected


def _statements(coverage, stats, units):
    if stats.count:
        residual = (f'Model minus observed: bias {stats.bias:.6g} {units}, RMSE {stats.rmse:.6g} {units}, '
                    f'MAE {stats.mae:.6g} {units}; equal weight per eligible sample.')
    else:
        residual = 'No eligible model-observation pairs remain; residual statistics are unavailable.'
    return {
        'eligible_profiles': f'{coverage.matched_profiles} profiles supply eligible comparisons under the selected matching rules.',
        'eligible_samples': f'{coverage.matched_samples} eligible model-observation pairs are available.',
        'residual_statistics': residual,
        'model_state': 'The original ocean model and observation quality flags are unchanged.',
    }


def analyze_blackout(baseline, comparisons, query):
    """Original and retained results share no mutable nested state with caches."""
    profile_ids = [item.profile.id for item in baseline.profiles]
    by_id = {item.profile.id: item for item in comparisons}
    if len(set(profile_ids)) != len(profile_ids) or len(by_id) != len(comparisons) or set(by_id) != set(profile_ids):
        raise UnsupportedData('blackout_integrity_error', 'Original coverage and profile comparisons do not describe the same library.')
    if baseline.settings != query.settings:
        raise UnsupportedData('blackout_integrity_error', 'Original coverage does not match the requested comparison settings.')
    for item in comparisons:
        if (item.case_id != baseline.case_id or item.settings != query.settings
                or item.manifest_sha256 != baseline.manifest_sha256
                or item.observation_library_sha256 != baseline.observation_library_sha256
                or item.model_time != baseline.model_time):
            raise UnsupportedData('blackout_integrity_error', 'The original evidence source identities or settings differ.')
        coverage_profile = next(profile for profile in baseline.profiles if profile.profile.id == item.profile.id)
        if (coverage_profile.total_samples != item.total_samples or coverage_profile.matched_count != item.matched_count
                or item.matched_count != sum(row.accepted for row in item.rows)):
            raise UnsupportedData('blackout_integrity_error', 'Original coverage and eligible comparison counts differ.')
    selected = resolve_exclusions([item.profile for item in baseline.profiles], query)
    original_rows = [row for profile_id in profile_ids for row in by_id[profile_id].rows if row.accepted]
    remaining_rows = [row for profile_id in profile_ids if profile_id not in selected
                      for row in by_id[profile_id].rows if row.accepted]
    retained = [item.model_copy(deep=True) for item in baseline.profiles if item.profile.id not in selected]
    rejected = Counter()
    for item in retained:
        rejected.update(item.exclusion_counts)
    modified = baseline.model_copy(deep=True, update={
        'total_profiles': len(retained),
        'matched_profiles': sum(item.matched_count > 0 for item in retained),
        'total_samples': sum(item.total_samples for item in retained),
        'matched_samples': sum(item.matched_count for item in retained),
        'excluded_samples': sum(item.excluded_count for item in retained),
        'exclusion_counts': dict(sorted(rejected.items())),
        'profiles': retained,
    })
    baseline_metrics, modified_metrics = metrics(original_rows), metrics(remaining_rows)
    effects = []
    for profile_id in profile_ids:
        original = by_id[profile_id]
        removed = profile_id in selected
        lost_indices = [row.sample_index for row in original.rows if row.accepted] if removed else []
        effects.append(ProfileEffect(
            profile_id=profile_id, excluded_by_user=removed, selected_by=selected.get(profile_id, []),
            baseline_matched_samples=original.matched_count,
            remaining_matched_samples=0 if removed else original.matched_count,
            removed_eligible_samples=len(lost_indices), removed_sample_indices=lost_indices,
            original_metrics=original.metrics.model_copy(deep=True),
        ))
    units = comparisons[0].units if comparisons else ('°C' if query.settings.variable == 'temperature' else 'psu')
    before, after = _statements(baseline, baseline_metrics, units), _statements(modified, modified_metrics, units)
    statements = [EvidenceStatement(id=key, baseline=before[key], modified=after[key],
                                   changed=(baseline_metrics != modified_metrics if key == 'residual_statistics'
                                            else before[key] != after[key]))
                  for key in before]
    return BlackoutResult(
        case_id=baseline.case_id, query=query.model_copy(deep=True),
        manifest_sha256=baseline.manifest_sha256, observation_library_sha256=baseline.observation_library_sha256,
        units=units,
        baseline=baseline.model_copy(deep=True), modified=modified,
        baseline_metrics=baseline_metrics, modified_metrics=modified_metrics, profile_effects=effects,
        excluded_profile_ids=sorted(selected), removed_profiles=len(selected),
        removed_eligible_profiles=baseline.matched_profiles - modified.matched_profiles,
        removed_samples=baseline.total_samples - modified.total_samples,
        removed_eligible_samples=baseline.matched_samples - modified.matched_samples,
        statements=statements, methods=METHODS.copy(), caveats=[*CAVEATS, *baseline.caveats],
    )

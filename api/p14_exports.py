"""Portable Phase 14 numerical tables, preserving exact values and identities."""
import json


def tables(output, csv_text):
    files = {}
    meta = dict(method_version=output['method_version'], case_id=output['case_id'],
                model_manifest_sha256=output['manifest_sha256'],
                observation_library_sha256=output['observation_library_sha256'])

    def table(name, rows, fields):
        def scalar(value):
            return json.dumps(value, separators=(',', ':'), ensure_ascii=True, allow_nan=False) if isinstance(value, (dict, list)) else value
        files[name] = csv_text([*meta, *fields], [[*meta.values(), *[scalar(row.get(key)) for key in fields]] for row in rows])

    if output['kind'] == 'feature_evolution':
        q = output['query']
        nodes = []
        for frame in output['frames']:
            for node in frame['regions']:
                nodes.append(dict(**node, model_time_utc=frame['time'], variable=q['variable'], units=q['units'],
                                  threshold=q['threshold'], upper_threshold=q['upper_threshold'], operator=q['operator']))
        table('evolution-regions.csv', nodes, ['node_id', 'time_index', 'model_time_utc', 'variable', 'units', 'operator', 'threshold',
              'upper_threshold', 'cell_count', 'estimated_volume_km3', 'center_bounds', 'cell_bounds', 'min', 'max', 'mean',
              'volume_weighted_mean', 'membership_sha256', 'eligible_profiles', 'eligible_samples', 'observations',
              'boundary_contacts', 'selection_depth_contacts', 'touches_missing_values'])
        links = [dict(from_time_utc=t['from_time'], to_time_utc=t['to_time'], **link) for t in output['transitions'] for link in t['links']]
        table('evolution-links.csv', links, ['from_time_utc', 'to_time_utc', 'source_node_id', 'target_node_id', 'classification',
              'shared_cells', 'estimated_overlap_volume_km3', 'source_fraction', 'target_fraction', 'overlap_coefficient'])
        table('evolution-transitions.csv', output['transitions'], ['from_time_index', 'to_time_index', 'from_time', 'to_time',
              'elapsed_hours', 'status', 'reason', 'split_count', 'merge_count', 'ambiguous_count', 'appeared_node_ids',
              'disappeared_node_ids', 'ambiguous_node_ids', 'source_unresolved_node_ids', 'target_unresolved_node_ids', 'unmatched_details'])
        trials = [dict(offset=s['offset'], threshold=s['threshold'], upper_threshold=s['upper_threshold'], **f)
                  for s in output['sensitivity'] for f in s['frames']]
        table('evolution-sensitivity-frames.csv', trials, ['offset', 'threshold', 'upper_threshold', 'time_index', 'time',
              'region_count', 'qualified_cells', 'estimated_volume_km3'])
        transitions = [dict(offset=s['offset'], threshold=s['threshold'], upper_threshold=s['upper_threshold'], **t)
                       for s in output['sensitivity'] for t in s['transitions']]
        table('evolution-sensitivity-links.csv', transitions, ['offset', 'threshold', 'upper_threshold', 'from_time_index',
              'to_time_index', 'status', 'link_count', 'split_count', 'merge_count', 'ambiguous_count', 'appearance_count',
              'disappearance_count', 'unresolved_count'])
    else:
        settings = output['query']['settings']
        rows = []
        for name in ['baseline', 'modified']:
            coverage, metrics = output[name], output[name + '_metrics']
            rows.append(dict(state=name, model_time_utc=coverage['model_time'], variable=settings['variable'], units=output['units'],
                             total_profiles=coverage['total_profiles'], eligible_profiles=coverage['matched_profiles'],
                             total_samples=coverage['total_samples'], eligible_samples=coverage['matched_samples'],
                             source_or_matching_excluded_samples=coverage['excluded_samples'], exclusion_counts=coverage['exclusion_counts'],
                             excluded_by_user_profiles=0 if name == 'baseline' else output['removed_profiles'],
                             excluded_by_user_samples=0 if name == 'baseline' else output['removed_samples'], **metrics))
        table('blackout-coverage.csv', rows, ['state', 'model_time_utc', 'variable', 'units', 'total_profiles', 'eligible_profiles',
              'total_samples', 'eligible_samples', 'source_or_matching_excluded_samples', 'excluded_by_user_profiles',
              'excluded_by_user_samples', 'exclusion_counts', 'count', 'bias', 'rmse', 'mae', 'maximum_abs_residual'])
        profiles = {p['profile']['id']: p for p in output['baseline']['profiles']}
        rows = []
        for effect in output['profile_effects']:
            original = profiles[effect['profile_id']]
            rows.append(dict(**effect, platform=original['profile']['platform'], instrument=original['profile']['instrument'],
                             source_start_utc=original['profile']['time'], source_end_utc=original['profile']['time_end'],
                             model_time_utc=output['baseline']['model_time'], variable=settings['variable'], units=output['units'],
                             original_source_or_matching_exclusion_counts=original['exclusion_counts']))
        table('blackout-profiles.csv', rows, ['profile_id', 'platform', 'instrument', 'source_start_utc', 'source_end_utc',
              'model_time_utc', 'variable', 'units', 'excluded_by_user', 'selected_by', 'baseline_matched_samples',
              'remaining_matched_samples', 'removed_eligible_samples', 'removed_sample_indices', 'original_metrics', 'original_source_or_matching_exclusion_counts'])
        lost = [dict(profile_id=effect['profile_id'], source_sample_index=i, model_time_utc=output['baseline']['model_time'],
                     variable=settings['variable'], units=output['units']) for effect in output['profile_effects'] for i in effect['removed_sample_indices']]
        table('blackout-removed-sample-identifiers.csv', lost, ['profile_id', 'source_sample_index', 'model_time_utc', 'variable', 'units'])
        table('blackout-statements.csv', output['statements'], ['id', 'baseline', 'modified', 'changed'])
    return files

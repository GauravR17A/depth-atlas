"""Inspectable overlap graphs on unchanged native grids.

Each graph edge is a rule-based correspondence between threshold-cell sets.
It is never a particle trajectory or a persistent physical identity.
"""
from collections import defaultdict
from datetime import datetime
from math import fsum

import numpy as np

from science.contracts import UnsupportedData
from science.evolution_contracts import NATIVE_CADENCE_HOURS


MAX_REGIONS_PER_FRAME = 512
MAX_TOTAL_REGIONS = 2048
MAX_OVERLAP_PAIRS = 8192
MAX_FOOTPRINT_INDICES = 200000

METHODS = [
    'Every selected frame uses the P07 native float64 threshold-cell method, with unchanged threshold, units and depth interval. All regions enter the calculation, including regions outside the first 50 search results.',
    'A node identifies a region in one frame only. Correspondence requires common native cells. Estimated overlap volume sums their midpoint-bin spherical volumes in native flat-index order using math.fsum.',
    'P14 region volume, arithmetic mean and volume-weighted mean use math.fsum in increasing native flat-index order. Weighted products use separate Python binary64 multiplications before summation. These P14 aggregates replace copied NumPy reductions; P07 memberships, source values, geometry, observations and earlier investigation methods are unchanged.',
    'Overlap coefficient = common estimated volume divided by the smaller region volume. A link is retained when this coefficient is at least the chosen minimum. Both source and target volume fractions are reported. No nearest-region replacement is used.',
    'Connected bipartite correspondence groups are classified as one-to-one continuation, one-to-many split, many-to-one merge, or many-to-many ambiguous. These describe the declared overlap rule, not tracked water or independent physical identity.',
    'Only consecutive available source indices at the native 12-hour cadence are compared. Skipped frames or a different elapsed interval produce a visible gap, no links and unresolved endpoints.',
    'An unmatched node is unresolved when any of its native member cells is missing in the counterpart frame. Otherwise no-predecessor/no-successor records the absence of a qualifying overlap, not physical creation or destruction. Boundary and missing-neighbour contacts remain visible.',
    'Source-grid boundary contacts and selected-depth contacts are separate. Selected-depth contacts mark the first or last retained native depth centre in the requested window; they are sampling limits, not measured physical ocean boundaries.',
    'Threshold sensitivity repeats the entire correspondence calculation at the base threshold and at minus/plus the stated delta. A between interval shifts both endpoints by the same delta. Zero delta explicitly disables extra sensitivity runs.',
    'Observation associations reuse the existing P05 eligibility gates at each actual source timestamp. A profile may support more than one frame; counts across frames must not be interpreted as independent observations.',
]
LIMITATIONS = [
    'Feature evolution is not the transport path of the same water, a current trajectory, an eddy tracker or a forecast.',
    'The two supported Indian Ocean cases contain seven 12-hourly historical frames over three days. No time interpolation or continuity outside that window is inferred.',
    'The selected correspondence threshold is a project setting, not a calibrated physical probability. Weak movement without shared cells can remain unmatched.',
    'Source masks, bounded domains, sampled depths and threshold choices can change connected regions. Apparent splits, merges and disappearance do not establish a physical process by themselves.',
    'Cell volumes use midpoint bounds because provider cell boundaries are unavailable. Overlap and volume remain estimates on the native grid.',
    'Eligible observations provide context for model regions and may already have been assimilated. Coverage and agreement are not independent validation or calibrated confidence.',
    'Pacific calendar-month potential-temperature cases are not supported by this 12-hour correspondence method.',
]


def node_id(time_index, seed):
    return f't{time_index}:r{int(seed)}'


def region_statistics(values, volumes, indices):
    """P14-only ordered reductions without modifying the P07 cached region.

    Fixed membership identifies the same original cells; this function changes
    only reduction arithmetic, not values, masks, geometry or thresholds.
    """
    positions = sorted(int(index) for index in indices)
    if not positions:
        raise UnsupportedData('evolution_integrity_error', 'A region needs at least one native member cell.')
    source, weights = np.asarray(values).ravel(), np.asarray(volumes).ravel()
    samples = [float(source[index]) for index in positions]
    cell_volumes = [float(weights[index]) for index in positions]
    total = fsum(cell_volumes)
    return dict(
        estimated_volume_km3=total,
        mean=fsum(samples)/len(samples),
        volume_weighted_mean=fsum(sample*volume for sample, volume in zip(samples, cell_volumes))/total,
    )


def _epoch(timestamp):
    value = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise UnsupportedData('unsupported_time', 'Feature evolution requires explicit time zones.')
    return value.timestamp()


def region_contacts(indices, shape, finite):
    """Report bounded-grid/missing-neighbour contacts without filling anything."""
    z, y, x = np.unravel_index(indices, shape)
    contacts = []
    for name, axis, end in (
        ('shallow', z, 0), ('deep', z, shape[0]-1),
        ('south', y, 0), ('north', y, shape[1]-1),
        ('west', x, 0), ('east', x, shape[2]-1),
    ):
        if np.any(axis == end):
            contacts.append(name)
    missing = False
    for axis, coord in enumerate((z, y, x)):
        for sign in (-1, 1):
            eligible = (coord + sign >= 0) & (coord + sign < shape[axis])
            if not eligible.any():
                continue
            positions = [a[eligible].copy() for a in (z, y, x)]
            positions[axis] += sign
            if not finite[tuple(positions)].all():
                missing = True
                break
        if missing:
            break
    return dict(boundary_contacts=contacts, touches_domain_boundary=bool(contacts), touches_missing_values=missing)


def _classify_components(links):
    """Classify entire bipartite groups, so many-to-many stays ambiguous."""
    adjacent = defaultdict(set)
    for link in links:
        source, target = ('s', link['source_node_id']), ('t', link['target_node_id'])
        adjacent[source].add(target)
        adjacent[target].add(source)
    groups, seen = {}, set()
    counts = dict(split_count=0, merge_count=0, ambiguous_count=0)
    ambiguous = set()
    for start in sorted(adjacent):
        if start in seen:
            continue
        pending, component = [start], set()
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            pending.extend(sorted(adjacent[current] - component, reverse=True))
        seen.update(component)
        nsource = sum(role == 's' for role, _ in component)
        ntarget = len(component) - nsource
        kind = 'continuation' if nsource == ntarget == 1 else 'split' if nsource == 1 else 'merge' if ntarget == 1 else 'ambiguous'
        if kind != 'continuation':
            counts[f'{kind}_count'] += 1
        if kind == 'ambiguous':
            ambiguous.update(value for _, value in component)
        for key in component:
            groups[key] = kind
    for link in links:
        link['classification'] = groups[('s', link['source_node_id'])]
    return sorted(ambiguous), counts


def transition(source, target, volumes, minimum_overlap, cadence_hours=NATIVE_CADENCE_HOURS):
    """Pure, deterministic comparison of two prepared frame dictionaries.

    Inputs include original labels/members and finite-value masks. They are never
    mutated, and no membership is constructed from truncated API presentation.
    """
    source_index, target_index = source['time_index'], target['time_index']
    elapsed = (_epoch(target['time']) - _epoch(source['time'])) / 3600
    if elapsed <= 0:
        raise UnsupportedData('unsupported_time', 'Source timestamps must be strictly increasing.')
    result = dict(
        from_time_index=source_index, to_time_index=target_index,
        from_time=source['time'], to_time=target['time'], elapsed_hours=elapsed,
        status='compared', reason=None, links=[], appeared_node_ids=[],
        disappeared_node_ids=[], ambiguous_node_ids=[],
        source_unresolved_node_ids=[], target_unresolved_node_ids=[],
        unmatched_details=[], split_count=0, merge_count=0, ambiguous_count=0,
    )
    source_members, target_members = source['members'], target['members']
    if target_index != source_index + 1 or elapsed != cadence_hours:
        result.update(
            status='gap', reason='Source frames are skipped or their elapsed interval differs from the supported native 12-hour cadence. No correspondence is inferred across this gap.',
            source_unresolved_node_ids=[node_id(source_index, key) for key in sorted(source_members)],
            target_unresolved_node_ids=[node_id(target_index, key) for key in sorted(target_members)],
        )
        return result
    if source['labels'].shape != target['labels'].shape or source['labels'].shape != np.shape(volumes):
        raise UnsupportedData('unsupported_grid', 'Correspondence needs exactly the same native cell grid in both frames.')
    weights = np.asarray(volumes, dtype=np.float64).ravel()
    if not np.isfinite(weights).all() or np.any(weights < 0):
        raise UnsupportedData('unsupported_grid', 'Native overlap volumes must be finite and nonnegative.')
    left, right = source['labels'].ravel(), target['labels'].ravel()
    pair_indices = defaultdict(list)
    for index in np.flatnonzero((left >= 0) & (right >= 0)).tolist():
        pair_indices[(int(left[index]), int(right[index]))].append(index)
        if len(pair_indices) > MAX_OVERLAP_PAIRS:
            raise UnsupportedData('evolution_too_complex', 'This evolution has too many overlapping region pairs. Narrow the depth or threshold range.')
    source_totals = {seed: fsum(float(weights[i]) for i in indices) for seed, indices in source_members.items()}
    target_totals = {seed: fsum(float(weights[i]) for i in indices) for seed, indices in target_members.items()}
    linked_source, linked_target = set(), set()
    for (source_seed, target_seed), indices in sorted(pair_indices.items()):
        shared = fsum(float(weights[index]) for index in indices)
        source_volume, target_volume = source_totals[source_seed], target_totals[target_seed]
        if not shared > 0 or not min(source_volume, target_volume) > 0:
            continue
        score = shared / min(source_volume, target_volume)
        if score < minimum_overlap:
            continue
        result['links'].append(dict(
            source_node_id=node_id(source_index, source_seed),
            target_node_id=node_id(target_index, target_seed),
            shared_cells=len(indices), estimated_overlap_volume_km3=shared,
            source_fraction=shared/source_volume, target_fraction=shared/target_volume,
            overlap_coefficient=score,
        ))
        linked_source.add(source_seed)
        linked_target.add(target_seed)
    result['ambiguous_node_ids'], counts = _classify_components(result['links'])
    result.update(counts)
    for frame, counterpart, members, linked, relation, result_key, unresolved_key in (
        (source, target, source_members, linked_source, 'no_successor', 'disappeared_node_ids', 'source_unresolved_node_ids'),
        (target, source, target_members, linked_target, 'no_predecessor', 'appeared_node_ids', 'target_unresolved_node_ids'),
    ):
        counterpart_finite = counterpart['finite'].ravel()
        for seed in sorted(set(members) - linked):
            name = node_id(frame['time_index'], seed)
            missing = int((~counterpart_finite[members[seed]]).sum())
            reason = 'incomplete_support' if missing else 'no_qualifying_overlap'
            result[unresolved_key if missing else result_key].append(name)
            if missing:
                result['ambiguous_node_ids'].append(name)
            result['unmatched_details'].append(dict(
                node_id=name, relation=relation, reason=reason,
                missing_counterpart_cells=missing,
            ))
    result['ambiguous_node_ids'] = sorted(set(result['ambiguous_node_ids']))
    return result


def summarize(frames, transitions):
    return dict(
        frame_count=len(frames), transition_count=len(transitions),
        compared_transitions=sum(t['status'] == 'compared' for t in transitions),
        gap_count=sum(t['status'] == 'gap' for t in transitions),
        node_count=sum(f['total_regions'] for f in frames),
        link_count=sum(len(t['links']) for t in transitions),
        appearance_count=sum(len(t['appeared_node_ids']) for t in transitions),
        disappearance_count=sum(len(t['disappeared_node_ids']) for t in transitions),
        split_count=sum(t['split_count'] for t in transitions),
        merge_count=sum(t['merge_count'] for t in transitions),
        ambiguous_count=sum(t['ambiguous_count'] for t in transitions),
        unresolved_count=sum(len(t['source_unresolved_node_ids']) + len(t['target_unresolved_node_ids']) for t in transitions),
    )

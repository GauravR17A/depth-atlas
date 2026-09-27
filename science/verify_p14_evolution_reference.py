"""Offline independent oracle from original packed HYCOM source files.

SciPy labels cells; set intersections and a separate Decimal spherical-shell
integral produce expected overlaps. No production segmentation, store, query,
correspondence, or investigation code is imported. This creates test evidence,
not runtime data. Requires the already available offline SciPy environment.
"""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

import netCDF4
import numpy as np
from scipy import ndimage

from science.verify_p07_reference import decode, geometry


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'tests/fixtures/p14-evolution-source-reference.json'


def graph_groups(pairs):
    # Independent union-find groups rather than the production graph traversal.
    parent = {}
    def find(value):
        parent.setdefault(value, value)
        while parent[value] != value:
            value = parent[value]
        return value
    for left, right in pairs:
        a, b = ('left', left), ('right', right)
        parent[find(b)] = find(a)
    groups = defaultdict(list)
    for value in parent:
        groups[find(value)].append(value)
    kind = {}
    for values in groups.values():
        left = sum(value[0] == 'left' for value in values)
        right = len(values)-left
        classification = {(True, True): 'continuation', (True, False): 'split', (False, True): 'merge', (False, False): 'ambiguous'}[(left == 1, right == 1)]
        for value in values:
            kind[value] = classification
    return kind


def build():
    output = dict(schema_version='1', method='Original packed source decoded independently; SciPy six-face labels; Decimal spherical-shell antiderivative; scalar math.fsum volume integration; Python set intersection and union-find classification.',
                  numerical_tolerance=dict(relative=2e-12, absolute=1e-10, explanation='Independent spherical-volume operation ordering only. Native membership, node links, classifications, masks and times must match exactly. Replay remains exact.'), sources=[], scenarios=[])
    for case_id, raw in [('bay-bengal-2024-01', 'data/raw'), ('arabian-sea-2024-01', 'data/raw/arabian-sea')]:
        acquisition = json.loads((ROOT/raw/'acquisition.json').read_text(encoding='utf8'))
        records = sorted((r for r in acquisition['files'] if r.get('archive_kind') == 'packed_source_subset_reconstructed_as_netcdf'), key=lambda r: r['time'])
        assert len(records) == 7
        fields, axes = [], None
        for record in records:
            path = ROOT/record['path']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
            output['sources'].append(dict(path=record['path'], sha256=record['sha256'], time=record['time']))
            with netCDF4.Dataset(path) as source:
                source.set_auto_maskandscale(False)
                actual = tuple([float(v) for v in source[name][:]] for name in ('depth', 'lat', 'lon'))
                if axes is not None:
                    assert axes == actual
                axes = actual
                time = source['time']
                decoded_time = netCDF4.num2date(time[:], time.units, calendar=getattr(time, 'calendar', 'standard'))[0].strftime('%Y-%m-%dT%H:%M:%SZ')
                assert decoded_time == record['time']
                fields.append(decode(source['water_temp']))
        _, _, _, _, shells, areas = geometry(*axes, 0, 300)
        weights = np.asarray(shells)[:, None, None] * np.asarray(areas)[None, :, :] / 1e9
        eligible_depths = np.asarray([0 <= value <= 300 and shells[i] > 0 for i, value in enumerate(axes[0])])
        for threshold in (25.75, 26.0, 26.25):
            frames, memberships = [], []
            for time_index, values in enumerate(fields):
                labels, count = ndimage.label(np.isfinite(values) & (values >= threshold) & eligible_depths[:, None, None], structure=ndimage.generate_binary_structure(3, 1))
                groups = {}
                rows = []
                for label in range(1, count+1):
                    indices = np.flatnonzero(labels.ravel() == label)
                    seed = int(indices[0])
                    groups[seed] = set(indices.tolist())
                    rows.append(dict(node_id=f't{time_index}:r{seed}', seed=seed, cell_count=len(indices),
                                     membership_sha256=hashlib.sha256(indices.astype('<i8').tobytes()).hexdigest(),
                                     estimated_volume_km3=math.fsum(float(weights.ravel()[i]) for i in indices)))
                frames.append(dict(time_index=time_index, time=records[time_index]['time'], regions=rows))
                memberships.append(groups)
            transitions = []
            for time_index in range(6):
                left, right = memberships[time_index], memberships[time_index+1]
                left_volumes = {row['seed']: row['estimated_volume_km3'] for row in frames[time_index]['regions']}
                right_volumes = {row['seed']: row['estimated_volume_km3'] for row in frames[time_index+1]['regions']}
                pairs = {}
                for source_seed, source_cells in left.items():
                    for target_seed, target_cells in right.items():
                        common = sorted(source_cells & target_cells)
                        shared = math.fsum(float(weights.ravel()[i]) for i in common)
                        if shared <= 0:
                            continue
                        score = shared/min(left_volumes[source_seed], right_volumes[target_seed])
                        if score >= 0.1:
                            pairs[(source_seed, target_seed)] = dict(source_node_id=f't{time_index}:r{source_seed}', target_node_id=f't{time_index+1}:r{target_seed}',
                                shared_cells=len(common), estimated_overlap_volume_km3=shared, source_fraction=shared/left_volumes[source_seed], target_fraction=shared/right_volumes[target_seed], overlap_coefficient=score)
                kinds = graph_groups(pairs)
                for (source_seed, _), link in pairs.items():
                    link['classification'] = kinds[('left', source_seed)]
                observed_left = {a for a, _ in pairs}
                observed_right = {b for _, b in pairs}
                disappeared, appeared = [], []
                unresolved_left, unresolved_right = [], []
                for source_seed in sorted(set(left)-observed_left):
                    node = f't{time_index}:r{source_seed}'
                    (disappeared if all(np.isfinite(fields[time_index+1].ravel()[i]) for i in left[source_seed]) else unresolved_left).append(node)
                for target_seed in sorted(set(right)-observed_right):
                    node = f't{time_index+1}:r{target_seed}'
                    (appeared if all(np.isfinite(fields[time_index].ravel()[i]) for i in right[target_seed]) else unresolved_right).append(node)
                transitions.append(dict(from_time_index=time_index, to_time_index=time_index+1, links=list(pairs.values()),
                    disappeared_node_ids=disappeared, appeared_node_ids=appeared,
                    source_unresolved_node_ids=unresolved_left, target_unresolved_node_ids=unresolved_right))
            output['scenarios'].append(dict(case_id=case_id, threshold=threshold, frames=frames, transitions=transitions))
    return output


if __name__ == '__main__':
    body = (json.dumps(build(), sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(body)
    print(json.dumps(dict(path=OUTPUT.relative_to(ROOT).as_posix(), bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), source_files=14, scenarios=6)))

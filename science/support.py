"""Associate eligible pairs with exact native threshold membership.

This adds a view over P05/P07 results, without modifying their frozen contracts.
"""
from bisect import bisect_right
from collections import Counter

import numpy as np
from pydantic import model_validator

from science.contracts import UnsupportedData
from science.evidence_contracts import MatchSettings
from science.feature_contracts import RegionQuery
from science.features import midpoint_edges
from science.imported import ImportedSource

METHOD = 'p16d-native-support-v1'


class SupportRequest(RegionQuery):
    settings: MatchSettings
    import_source: ImportedSource | None = None

    @model_validator(mode='after')
    def same_selection(self):
        if self.query.variable != self.settings.variable or self.query.time_index != self.settings.time_index:
            raise ValueError('Support must use the structure variable and snapshot.')
        return self


def associate(labels, coordinates, query, region_id, comparisons):
    """One midpoint depth bin per accepted pair; no double-counted cells."""
    seed = int(region_id[1:])
    membership = labels == seed
    if not membership.any():
        raise UnsupportedData('region_not_found', 'Run the structure search and choose a region from that result.')
    edges = midpoint_edges(coordinates['depth_m'])
    lat = {v: i for i, v in enumerate(coordinates['latitude'])}
    lon = {v: i for i, v in enumerate(coordinates['longitude'])}
    rows, touched, excluded = [], set(), Counter()
    accepted_outside = 0
    for comparison in comparisons:
        excluded.update(comparison.exclusion_counts)
        for row in comparison.rows:
            if not row.accepted:
                continue
            z = min(len(coordinates['depth_m']) - 1, bisect_right(edges, row.depth_m) - 1)
            y, x = lat[row.model_latitude], lon[row.model_longitude]
            if z < 0 or not (query.depth_min_m <= row.depth_m <= query.depth_max_m and
                             query.depth_min_m <= coordinates['depth_m'][z] <= query.depth_max_m) or not membership[z, y, x]:
                accepted_outside += 1
                continue
            touched.add((z, y, x))
            rows.append(dict(profile_id=comparison.profile.id, platform=comparison.profile.platform,
                             source_sha256=comparison.profile.source_sha256,
                             cell=[z, y, x], **row.model_dump(mode='json')))
    cells = int(membership.sum())
    footprint = np.flatnonzero(membership.any(axis=0)).tolist()
    supported_columns = sorted({y * labels.shape[2] + x for _, y, x in touched})
    return dict(rows=rows, eligible_samples=len(rows), eligible_profiles=len({r['profile_id'] for r in rows}),
                region_cells=cells, supported_cells=len(touched), unsupported_cells=cells-len(touched),
                footprint_indices=footprint, supported_columns=supported_columns,
                unsupported_columns=len(footprint)-len(supported_columns),
                accepted_outside_region=accepted_outside, excluded_samples=sum(excluded.values()),
                exclusion_counts=dict(sorted(excluded.items())))

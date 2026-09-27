"""Native, face-connected threshold cells and nearest-column line sections.

Grid coordinates are point samples, not supplied cell bounds. Midpoint bins are
an explicit piecewise-constant volume estimate, clipped to the sampled domain.
No display resampling, interpolation, mask filling or eddy identification occurs.
"""
import hashlib
import math
import numpy as np
from science.contracts import UnsupportedData

RADIUS_M = 6371008.8
METHODS = [
    'Native float64 point values; inclusive thresholds and depth-centre selection. Missing values never qualify.',
    'Six-face adjacency only: neighbouring depth, latitude or longitude indices. Diagonal contact does not join regions.',
    'Estimated cell bounds use coordinate midpoints, clipped to first/last sampled coordinates and the requested depth interval.',
    'Estimated volume integrates spherical shells using radius 6371008.8 m. Values are treated as constant in each inferred cell.',
    'Region IDs use the smallest native flat index (depth, latitude, longitude); sorting does not change membership.',
    'Nearby evidence uses eligible P05 comparisons: 6 hours, 5 km, maximum depth bracket 500 m, QC good or probably good. Observation depth must occupy a qualifying inferred cell in its matched model column; exact depth midpoints belong to the deeper bin.',
]
LIMITATIONS = [
    'These are connected threshold cells, not automatically detected eddies or tracked water parcels.',
    'Source cell boundaries and seabed geometry are unavailable. Volume is an estimate, not a supplied model cell volume or measured water mass.',
    'Domain edges and missing samples can truncate or split a region. No claim is made about continuity beyond the selected case.',
    'Nearby eligible observations provide context. Their observed values need not satisfy the model threshold; association is not independent validation.',
    'Observation associations are available for temperature and practical salinity only. No comparable velocity or kinetic-energy profiles are supplied.',
]


def midpoint_edges(axis):
    a = np.asarray(axis, dtype=np.float64)
    if a.ndim != 1 or len(a) < 2 or not np.isfinite(a).all() or not (np.diff(a) > 0).all():
        raise UnsupportedData('unsupported_grid', 'Search needs finite, strictly increasing rectilinear axes with at least two coordinates.')
    return np.concatenate(([a[0]], (a[:-1]+a[1:])/2, [a[-1]]))


def geometry(coords, query):
    depths, lat, lon = [np.asarray(coords[k], dtype=float) for k in ('depth_m', 'latitude', 'longitude')]
    ez, ey, ex = [midpoint_edges(a) for a in (depths, lat, lon)]
    if depths[0] < 0 or depths[-1] >= RADIUS_M or lat[0] < -90 or lat[-1] > 90 or lon[-1]-lon[0] >= 180:
        raise UnsupportedData('unsupported_grid', 'Search supports bounded, non-dateline rectilinear ocean grids.')
    if query.depth_min_m < depths[0] or query.depth_max_m > depths[-1]:
        raise UnsupportedData('outside_coverage', 'Choose a depth interval inside the available source depths.')
    ez = np.clip(ez, query.depth_min_m, query.depth_max_m)
    low, high = ez[:-1], ez[1:]
    # Stable factorization of ((R-low)^3 - (R-high)^3)/3 avoids cancellation.
    shell = (high-low)*(3*RADIUS_M**2-3*RADIUS_M*(low+high)+low*low+low*high+high*high)/3
    volumes = shell[:,None,None]*np.diff(np.sin(np.deg2rad(ey)))[None,:,None]*np.deg2rad(np.diff(ex))[None,None,:]/1e9
    return (depths, lat, lon), (ez, ey, ex), volumes


def analyze(values, coords, query):
    axes, edges, volumes = geometry(coords, query)
    a = np.asarray(values, dtype=np.float64)
    shape = tuple(len(v) for v in axes)
    if a.shape != shape or a.size > 250000:
        raise UnsupportedData('unsupported_grid', 'Search accepts at most 250,000 cells with matching coordinate axes.')
    selected = np.isfinite(a)
    if query.operator == 'at_least': selected &= a >= query.threshold
    elif query.operator == 'at_most': selected &= a <= query.threshold
    else: selected &= (a >= query.threshold) & (a <= query.upper_threshold)
    selected &= ((axes[0] >= query.depth_min_m) & (axes[0] <= query.depth_max_m))[:,None,None]
    selected &= volumes > 0
    nz, ny, nx = shape
    stride = ny*nx
    labels = np.full(a.size, -1, dtype=np.int32)
    mask = selected.ravel()
    members = {}
    for seed in np.flatnonzero(mask).tolist():
        if labels[seed] >= 0: continue
        if len(members) >= 5000:
            raise UnsupportedData('too_many_regions', 'This query creates more than 5,000 regions. Narrow the depth or threshold range.')
        labels[seed] = seed
        pending, found = [seed], []
        while pending:
            cell = pending.pop()
            found.append(cell)
            z, rest = divmod(cell, stride)
            y, x = divmod(rest, nx)
            neighbours = []
            if z: neighbours.append(cell-stride)
            if z+1 < nz: neighbours.append(cell+stride)
            if y: neighbours.append(cell-nx)
            if y+1 < ny: neighbours.append(cell+nx)
            if x: neighbours.append(cell-1)
            if x+1 < nx: neighbours.append(cell+1)
            for other in neighbours:
                if mask[other] and labels[other] == -1:
                    labels[other] = seed
                    pending.append(other)
        members[seed] = np.sort(np.array(found, dtype=np.int64))
    regions = []
    for seed, indices in members.items():
        z, y, x = np.unravel_index(indices, shape)
        samples, weights = a.ravel()[indices], volumes.ravel()[indices]
        total = float(np.sum(weights))
        lo = [int(v.min()) for v in (z,y,x)]
        hi = [int(v.max()) for v in (z,y,x)]
        def bounds(arrays, upper_offset=0):
            return dict(west=float(arrays[2][lo[2]]),south=float(arrays[1][lo[1]]),east=float(arrays[2][hi[2]+upper_offset]),north=float(arrays[1][hi[1]+upper_offset]),depth_min_m=float(arrays[0][lo[0]]),depth_max_m=float(arrays[0][hi[0]+upper_offset]))
        regions.append(dict(id=f'r{seed}', cell_count=len(indices), estimated_volume_km3=total,
            center_bounds=bounds(axes), cell_bounds=bounds(edges,1), min=float(samples.min()), max=float(samples.max()),
            mean=float(np.mean(samples)), volume_weighted_mean=float(np.sum(samples*weights)/total),
            membership_sha256=hashlib.sha256(indices.astype('<i8').tobytes()).hexdigest(),
            eligible_samples=0, eligible_profiles=0, observations=[]))
    return dict(labels=labels.reshape(shape), members=members, regions=regions, edges=dict(zip(('depth_m','latitude','longitude'),[v.tolist() for v in edges])), qualified_cells=int(selected.sum()))


def boundary_faces(labels, seed, limit=40000):
    """Exact exposed native-bin faces, merged into coplanar rectangles only."""
    member = labels == seed
    faces = []
    for axis in range(3):
        padding = [(0,0)]*3
        padding[axis] = (1,1)
        padded = np.pad(member, padding)
        for plane in range(member.shape[axis]+1):
            before, after = np.take(padded, plane, axis=axis), np.take(padded, plane+1, axis=axis)
            for sign, visible in ((-1,after & ~before),(1,before & ~after)):
                work = visible.copy()
                height, width = work.shape
                for row in range(height):
                    for col in np.flatnonzero(work[row]).tolist():
                        if not work[row,col]: continue
                        right = col+1
                        while right < width and work[row,right]: right += 1
                        bottom = row+1
                        while bottom < height and work[bottom,col:right].all(): bottom += 1
                        work[row:bottom,col:right] = False
                        faces.append([axis,plane,row,bottom,col,right,sign])
                        if len(faces) > limit: return None
    return faces


def distances_km(latitude, longitude, latitudes, longitudes):
    lat = np.deg2rad(latitudes)
    a = np.sin((lat-np.deg2rad(latitude))/2)**2 + np.cos(lat)*np.cos(np.deg2rad(latitude))*np.sin(np.deg2rad(np.asarray(longitudes)-longitude)/2)**2
    return 2*(RADIUS_M/1000)*np.arcsin(np.sqrt(np.clip(a,0,1)))


def sample_section(values, coords, labels, request):
    lon, lat = np.asarray(coords['longitude']), np.asarray(coords['latitude'])
    for point in (request.start, request.end):
        if not (lon[0] <= point[0] <= lon[-1] and lat[0] <= point[1] <= lat[-1]):
            raise UnsupportedData('outside_coverage', 'Both section endpoints must lie inside the selected model domain.')
    if request.start == request.end:
        raise UnsupportedData('empty_section', 'Choose two different section endpoints.')
    points = np.linspace(request.start, request.end, request.stations)
    yy, xx = np.meshgrid(lat,lon,indexing='ij')
    stations, indices, distance = [], [], 0.0
    for i, (x,y) in enumerate(points):
        if i: distance += float(distances_km(y,x,points[i-1,1],points[i-1,0]))
        d = distances_km(y,x,yy,xx)
        row, col = np.unravel_index(int(np.argmin(d)), d.shape)
        indices.append((row,col))
        stations.append(dict(longitude=float(x),latitude=float(y),distance_km=distance,model_longitude=float(lon[col]),model_latitude=float(lat[row]),offset_km=float(d[row,col])))
    depths = np.asarray(coords['depth_m'])
    zs = np.flatnonzero((depths >= request.query.depth_min_m) & (depths <= request.query.depth_max_m))
    section_values, region_ids = [], []
    for z in zs:
        for y,x in indices:
            v = values[z,y,x]
            section_values.append(float(v) if math.isfinite(v) else None)
            region_ids.append(f'r{labels[z,y,x]}' if labels[z,y,x] >= 0 else None)
    return dict(start=request.start,end=request.end,stations=stations,depth_m=depths[zs].tolist(),shape=[len(zs),len(points)],values=section_values,region_ids=region_ids)

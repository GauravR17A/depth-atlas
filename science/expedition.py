"""Deterministic prior-only station design and residual reconstruction.

This module cannot load future fields. Evaluation is orchestrated separately only
after all station indices have been frozen.
"""
import numpy as np

EARTH_RADIUS_KM = 6371.0088
METHODS = [
    'Prior: the first native model snapshot only. Candidate lattice: every sixth latitude/longitude index plus the final index, retaining finite prior values at the selected depth.',
    'Evaluation: every finite prior grid point outside the entire candidate lattice. The same target-time finite subset is used for every strategy.',
    'Gradient: native central or one-sided differences per great-circle kilometre; missing neighbours are not filled. Magnitude requires both horizontal derivatives and uses separate binary64 multiply, add and square-root operations: sqrt(dx*dx + dy*dy).',
    'Gradient objective: greedy 0.65 normalized prior gradient plus 0.35 distance to selected stations; first station maximizes gradient. Missing gradients score zero.',
    'Coverage and uniform baseline: greedy farthest-point space-filling, starting nearest the candidate coordinate centre. This approximates uniform coverage, not a regular survey grid.',
    'Minimum spacing is checked before each greedy selection. An incomplete greedy plan is not proof that no feasible plan exists.',
    'Random baselines: five fixed seeded Fisher-Yates permutations using a versioned 32-bit LCG, with the same candidate pool, budget and spacing. No retries selected by evaluation scores.',
    'Reconstruction: frozen prior plus inverse-distance-squared interpolation of simulated station residuals. Great-circle distances; an exact station returns its residual. No tuning on target fields.',
    'Errors are equally weighted over common evaluation points: RMSE, mean absolute error and signed reconstructed-minus-target bias. No area weighting.',
]
LIMITATIONS = [
    'Historical model sampling and reconstruction only. This is not an operational observing-system simulation experiment and does not establish forecast improvement.',
    'One station budget unit means one scalar measurement at one native depth and one snapshot, not a full profile, ship cost or route distance.',
    'No measurement noise is added. Model truth is simulated, not an independent ocean observation. IDW is not physically conserving and supplies no calibrated uncertainty.',
    'IDW uses geographic distance without coastal barriers and may combine stations across intervening land. Missing prior cells are never evaluation targets.',
    'Geographic spread is design coverage, not observational coverage or confidence. Observed model mismatch is not used in station ranking.',
    'Future fields are hidden from planning algorithms, not secret from users. Changing settings after seeing errors is exploratory tuning, not independent validation.',
    'Three later snapshots are correlated examples from the same short historical case, not three independent ocean events. Random ranges are descriptive, not probabilities.',
    'Stations and straight virtual transects are not safe or operational ship/glider routes. Bathymetry, navigation, travel time and deployment feasibility are not planned.',
]


def distances(a, b):
    """Pairwise great-circle km for [..., longitude/latitude] points."""
    a, b = np.deg2rad(np.asarray(a, float)), np.deg2rad(np.asarray(b, float))
    dl = a[:, None, 0] - b[None, :, 0]
    dp = a[:, None, 1] - b[None, :, 1]
    h = np.sin(dp / 2)**2 + np.cos(a[:, None, 1])*np.cos(b[None, :, 1])*np.sin(dl / 2)**2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def gradient(field, lon, lat):
    """Native differences without crossing a missing neighbour."""
    result = []
    for axis in (1, 0):
        derivative = np.full(field.shape, np.nan)
        for y in range(len(lat)):
            for x in range(len(lon)):
                if not np.isfinite(field[y, x]): continue
                low = (y, max(0, x-1)) if axis == 1 else (max(0, y-1), x)
                high = (y, min(len(lon)-1, x+1)) if axis == 1 else (min(len(lat)-1, y+1), x)
                if not np.isfinite(field[low]) or not np.isfinite(field[high]): continue
                distance = distances([[lon[low[1]], lat[low[0]]]], [[lon[high[1]], lat[high[0]]]])[0, 0]
                if distance > 0: derivative[y, x] = (field[high] - field[low]) / distance
        result.append(derivative)
    # Explicit ufunc operations avoid platform-specific hypot implementations.
    # Supported source gradients are bounded, so squaring cannot overflow.
    dx, dy = result
    dx_squared = np.multiply(dx, dx)
    dy_squared = np.multiply(dy, dy)
    squared_sum = np.add(dx_squared, dy_squared)
    return np.sqrt(squared_sum)


def prepare(prior, lon, lat):
    lon, lat = np.asarray(lon), np.asarray(lat)
    xx, yy = np.meshgrid(lon, lat)
    points = np.column_stack([xx.ravel(), yy.ravel()])
    lattice = np.zeros(prior.shape, bool)
    xi = sorted(set(range(0, len(lon), 6)) | {len(lon)-1})
    yi = sorted(set(range(0, len(lat), 6)) | {len(lat)-1})
    lattice[np.ix_(yi, xi)] = True
    candidates = np.flatnonzero((lattice & np.isfinite(prior)).ravel())
    evaluation = np.flatnonzero((~lattice & np.isfinite(prior)).ravel())
    grads = gradient(prior, lon, lat).ravel()[candidates]
    return dict(points=points, candidates=candidates, evaluation=evaluation,
                gradients=grads, prior=prior.ravel(), shape=prior.shape)


def permutation(n, seed):
    values = list(range(n)); state = seed & 0xffffffff
    for i in range(n-1, 0, -1):
        state = (1664525*state + 1013904223) & 0xffffffff
        j = state % (i+1)
        values[i], values[j] = values[j], values[i]
    return values


def select(prepared, budget, spacing, strategy, seed=0):
    indices = prepared['candidates']; points = prepared['points'][indices]
    if len(points) == 0: return []
    pair = distances(points, points)
    selected = []
    grad = np.nan_to_num(prepared['gradients'], nan=0)
    scaled_grad = grad / max(float(grad.max()), 1e-15)
    diameter = max(float(pair.max()), 1e-15)
    centre_distance = distances(points, [points.mean(axis=0)])[:, 0]
    random_order = permutation(len(points), seed)
    for _ in range(budget):
        nearest = pair[:, selected].min(axis=1) if selected else np.full(len(points), np.inf)
        allowed = nearest + 1e-10 >= spacing
        allowed[selected] = False
        if not allowed.any(): break
        if strategy == 'random':
            index = next(i for i in random_order if allowed[i])
        else:
            score = scaled_grad if strategy == 'gradient' and not selected else -centre_distance if not selected else nearest/diameter
            if strategy == 'gradient' and selected: score = 0.65*scaled_grad + 0.35*nearest/diameter
            index = int(np.argmax(np.where(allowed, score, -np.inf)))
        selected.append(index)
    return [int(indices[i]) for i in selected]


def reconstruct(prior, points, station_indices, station_values, evaluation_indices):
    station_indices = np.asarray(station_indices, int)
    evaluation_indices = np.asarray(evaluation_indices, int)
    d = distances(points[evaluation_indices], points[station_indices])
    residuals = np.asarray(station_values) - prior[station_indices]
    # Scale each row by its shortest distance to avoid enormous reciprocal weights.
    nearest = np.maximum(d.min(axis=1), 1e-12)
    weights = (nearest[:, None] / np.maximum(d, 1e-12))**2
    correction = (weights @ residuals) / weights.sum(axis=1)
    exact = (d == 0).any(axis=1)
    correction[exact] = residuals[np.argmin(d[exact], axis=1)]
    return prior[evaluation_indices] + correction


def metrics(prediction, truth):
    delta = np.asarray(prediction) - np.asarray(truth)
    return dict(rmse=float(np.sqrt(np.mean(delta**2))), mae=float(np.mean(np.abs(delta))), bias=float(np.mean(delta)))

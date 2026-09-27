"""OceanParcels 3.1.4 AdvectionRK4, adapted for bounded array execution.

Copyright (c) 2016, OceanParcels contributors. MIT license, see PARCELS_LICENSE.txt.
Upstream: https://github.com/OceanParcels/parcels/blob/v3.1.4/parcels/application_kernels/advection.py
Upstream file SHA256: be2cc9b24bda0fab5d21655c6693effb37d842302bb2bc852c47daab5469b458
Adaptations: vectorized coordinates, explicit return value/status, last-valid-step
boundary policy and endpoint/segment validation. This is not the full framework.
"""
import numpy as np

def rk4_step(field, time, points, dt):
    k1, s1 = field.sample(time, points)
    k2, s2 = field.sample(time + .5 * dt, points + k1 * .5 * dt)
    k3, s3 = field.sample(time + .5 * dt, points + k2 * .5 * dt)
    k4, s4 = field.sample(time + dt, points + k3 * dt)
    proposed = points + (k1 + 2*k2 + 2*k3 + k4) / 6.0 * dt
    _, se = field.sample(time + dt, proposed)
    # First failed stage defines the stop reason. Never commit part of a step.
    status = np.zeros(len(points), dtype=np.int8)
    for stage in (s1, s2, s3, s4, se):
        status = np.where(status == 0, stage, status)
    segment = field.segment_status(time, time + dt, points, proposed)
    status = np.where(status == 0, segment, status)
    return np.where((status == 0)[:, None], proposed, points), status

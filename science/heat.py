"""Declared Hobday-style seasonal events and TEOS-10 column diagnostics.

The event implementation is independent application code. The separately
acquired Oliver reference is used only by offline verification.
"""
from datetime import date, timedelta
from math import isfinite
import numpy as np
import gsw
from science.contracts import UnsupportedData

CP0 = 3991.86795711963
BASELINE_START, BASELINE_END = 1982, 2011

SURFACE_METHODS = [
    'Use NOAA OISST daily analysed SST at a declared fixed grid point. This blended/interpolated analysis is not a raw instrument measurement or a basin average.',
    'Fixed 1982-2011 baseline. For each calendar day except 29 February, pool the actual five preceding and five following days around every occurrence inside the baseline. Clip windows at the baseline edges; do not use data from other years.',
    'Require every baseline daily value. Seasonal mean uses explicit sequential binary64 addition. The 90th percentile uses sorted values and linear interpolation at index (n-1)*0.9.',
    'Set the 29 February climatological mean and threshold to the average of 28 February and 1 March before applying a centred 31-day circular moving average to both 366-day curves.',
    'An event requires at least five consecutive daily values strictly above the seasonal threshold. Merge already-qualified events separated by at most two observed days. Missing days split detection and are never filled or bridged.',
    'Detect over the supplied 2022-2025 context, then show events intersecting the selected 2023 or 2024 year with their full detected boundaries. Flag boundaries next to unavailable context; do not claim a complete duration there.',
    'Intensity is SST minus the seasonal mean, not SST minus the threshold. Mean and cumulative intensity include observed cool days inside merged events. Durations include both endpoints; cumulative intensity is a sum of daily anomalies in degree-Celsius days.',
]
DEPTH_METHODS = [
    'Sample temperature and practical salinity at the nearest native HYCOM column to the selected SST grid point. Keep its coordinates, distance and actual model time; no horizontal or time interpolation, no replacement wet column.',
    'Convert native depth to sea pressure with GSW p_from_z(-depth, latitude), practical salinity to Absolute Salinity with SA_from_SP and in-situ temperature to Conservative Temperature with CT_from_t. Potential temperature is referenced to 0 dbar using pt0_from_t.',
    'Use GSW sigma0 for potential-density anomaly referenced to 0 dbar and rho for in-situ density. Values outside the GSW 75-term validity funnel are not used for these density diagnostics.',
    'Mixed-layer depth is derived by the declared threshold method, not a supplied provider MLD field: first downward crossing of sigma0 increase 0.03 kg/m3, or absolute potential-temperature change 0.2 degrees Celsius, relative to 10 m. Interpolate only within the first valid crossing interval; missing support stops the search.',
    'Temperature gradient is the adjacent native-level temperature difference divided by its actual depth difference. N-squared uses GSW Nsquared for adjacent valid levels; negative values remain visible. No smoothing or masked-gap bridging.',
    'Column potential-enthalpy content relative to Conservative Temperature 0 degrees Celsius is the trapezoidal depth integral of in-situ density times cp0 times CT, with cp0=3991.86795711963 J/(kg K). Require complete support from 0 m to the selected native integration limit. This is not heatwave excess, a climatological anomaly, or tropical-cyclone heat potential.',
]
CAVEATS = [
    'These are historical source analyses and derived diagnostics, not live conditions or operational advisories.',
    'A surface marine heatwave does not establish a marine heatwave throughout the water column. Subsurface anomalies need their own long-term depth baseline, which is not supplied here.',
    'OISST and HYCOM are different analyses with different resolutions and methods. The depth link supplies contemporaneous context, not an identical measurement or causal explanation.',
    'HYCOM assimilates observations, including Argo. Nearby model-observation agreement does not establish independent validation.',
    'Mixed-layer depth depends on its declared reference level and threshold. The two criteria can disagree, and no crossing within the supported column is a bound rather than a measured layer depth.',
]


def ordered_sum(values):
    total = 0.0
    for value in values:
        total = total + float(value)
    return total


def finite(value):
    return value is not None and isfinite(float(value))


def daily_dates(dates):
    parsed = [date.fromisoformat(d) if isinstance(d, str) else d for d in dates]
    if not parsed or any(b-a != timedelta(days=1) for a, b in zip(parsed, parsed[1:])):
        raise UnsupportedData('unsupported_heat_series', 'A strictly consecutive daily source series is required.')
    return parsed


def calendar_index(day):
    return (date(2000, day.month, day.day)-date(2000, 1, 1)).days


def percentile90(values):
    ordered = sorted(float(v) for v in values)
    position = (len(ordered)-1)*0.9
    lower = int(position)
    upper = min(lower+1, len(ordered)-1)
    return ordered[lower] + (ordered[upper]-ordered[lower])*(position-lower)


def climatology(dates, values, baseline_start=BASELINE_START, baseline_end=BASELINE_END):
    days = daily_dates(dates)
    if len(days) != len(values):
        raise UnsupportedData('unsupported_heat_series', 'Daily dates and source values have different lengths.')
    pairs = [(d, v) for d, v in zip(days, values) if baseline_start <= d.year <= baseline_end]
    first, last = date(baseline_start, 1, 1), date(baseline_end, 12, 31)
    if not pairs or pairs[0][0] != first or pairs[-1][0] != last or len(pairs) != (last-first).days+1 or any(not finite(v) for _, v in pairs):
        raise UnsupportedData('incomplete_heat_baseline', 'This method requires a complete daily baseline; missing baseline values are not filled.')
    indices = [calendar_index(d) for d, _ in pairs]
    temperatures = [float(v) for _, v in pairs]
    means, thresholds, counts = [0.0]*366, [0.0]*366, [0]*366
    for doy in range(366):
        if doy == 59:
            continue
        centres = [i for i, value in enumerate(indices) if value == doy]
        pool = [temperatures[i+offset] for offset in range(-5, 6) for i in centres if 0 <= i+offset < len(temperatures)]
        if not pool:
            raise UnsupportedData('incomplete_heat_baseline', 'A calendar-day baseline pool is unavailable.')
        means[doy], thresholds[doy], counts[doy] = ordered_sum(pool)/len(pool), percentile90(pool), len(pool)
    means[59] = (means[58]+means[60])*0.5
    thresholds[59] = (thresholds[58]+thresholds[60])*0.5
    def smooth(curve):
        return [ordered_sum(curve[(i+j) % 366] for j in range(-15, 16))/31.0 for i in range(366)]
    return dict(seasonal_mean_c=smooth(means), threshold_c=smooth(thresholds), pool_count=counts,
                baseline_period=[baseline_start, baseline_end], percentile=90, window_days=11,
                smooth_days=31, feb29='Interpolate the unsmoothed 28 February and 1 March curves.',
                missing_policy='Reject incomplete baseline; never fill analysis missing days.')


def detect_events(dates, values, clim):
    days = daily_dates(dates)
    if len(days) != len(values):
        raise UnsupportedData('unsupported_heat_series', 'Daily dates and source values have different lengths.')
    seasonal = [clim['seasonal_mean_c'][calendar_index(d)] for d in days]
    thresholds = [clim['threshold_c'][calendar_index(d)] for d in days]
    valid = [finite(v) for v in values]
    above = [ok and float(v) > threshold for v, threshold, ok in zip(values, thresholds, valid)]
    runs, start = [], None
    for i, qualifies in enumerate(above+[False]):
        if qualifies and start is None:
            start = i
        elif not qualifies and start is not None:
            if i-start >= 5:
                runs.append([start, i-1])
            start = None
    merged = []
    for lo, hi in runs:
        if merged and lo-merged[-1][1]-1 <= 2 and all(valid[merged[-1][1]+1:lo]):
            merged[-1][1] = hi
        else:
            merged.append([lo, hi])
    events, memberships = [], [None]*len(days)
    for lo, hi in merged:
        anomalies = [float(values[i])-seasonal[i] for i in range(lo, hi+1)]
        peak = max(anomalies)
        event_id = f'mhw-{days[lo].isoformat()}-{days[hi].isoformat()}'
        left_unknown = lo == 0 or not valid[lo-1]
        right_unknown = hi == len(days)-1 or not valid[hi+1]
        exceedances = sum(1 for value in above[lo:hi+1] if value)
        events.append(dict(id=event_id, start=days[lo].isoformat(), end=days[hi].isoformat(),
                           peak_date=days[lo+anomalies.index(peak)].isoformat(), duration_days=hi-lo+1,
                           exceedance_days=exceedances, bridged_days=hi-lo+1-exceedances,
                           mean_intensity_c=ordered_sum(anomalies)/(hi-lo+1), max_intensity_c=peak,
                           cumulative_intensity_c_days=ordered_sum(anomalies),
                           left_boundary_unknown=left_unknown, right_boundary_unknown=right_unknown,
                           complete_boundaries=not (left_unknown or right_unknown)))
        for i in range(lo, hi+1):
            memberships[i] = event_id
    series = [dict(date=d.isoformat(), sst_c=float(v) if ok else None,
                   seasonal_mean_c=mean, threshold_c=threshold,
                   anomaly_c=float(v)-mean if ok else None,
                   exceeds_threshold=bool(exceed) if ok else None, event_id=event_id)
              for d, v, ok, mean, threshold, exceed, event_id in zip(days, values, valid, seasonal, thresholds, above, memberships)]
    return dict(events=events, series=series)


def mixed_layer(points, field, threshold, absolute=False):
    reference = next((p for p in points if p['depth_m'] == 10), None)
    base = reference.get(field) if reference else None
    result = dict(depth_m=None, status='reference_unavailable', reference_depth_m=10,
                  reference_value=base, threshold=threshold, supported_to_m=None)
    if base is None:
        return result
    previous, difference = reference, 0.0
    for point in (p for p in points if p['depth_m'] > 10):
        value = point.get(field)
        if value is None:
            return {**result, 'status': 'missing_support', 'supported_to_m': previous['depth_m']}
        signed = value-base
        current = abs(signed) if absolute else signed
        if current >= threshold:
            previous_signed = previous[field]-base
            target = (-threshold if signed < 0 else threshold) if absolute else threshold
            weight = (target-previous_signed)/(signed-previous_signed)
            return {**result, 'status': 'crossing', 'depth_m': previous['depth_m']+(point['depth_m']-previous['depth_m'])*weight,
                    'supported_to_m': point['depth_m']}
        previous, difference = point, current
    return {**result, 'status': 'no_crossing', 'supported_to_m': previous['depth_m']}


def profile_diagnostics(depths, temperature, salinity, latitude, longitude, depth_limit_m=300):
    """Native source column only. All output missingness is explicit JSON null."""
    if len(depths) != len(temperature) or len(depths) != len(salinity) or not depths or any(b <= a for a, b in zip(depths, depths[1:])):
        raise UnsupportedData('unsupported_depth_profile', 'Depth coordinates must be strictly increasing and match the source variables.')
    if depth_limit_m not in depths or depths[0] != 0:
        raise UnsupportedData('unsupported_depth_profile', 'The integration limits must be native source levels beginning at 0 m.')
    points = []
    for index, (depth, t, sp) in enumerate(zip(depths, temperature, salinity)):
        if depth > depth_limit_m:
            break
        point = dict(index=index, depth_m=float(depth), in_situ_temperature_c=float(t) if finite(t) else None,
                     practical_salinity=float(sp) if finite(sp) else None, pressure_dbar=None,
                     absolute_salinity_g_kg=None, conservative_temperature_c=None,
                     potential_temperature_c=None, sigma0_kg_m3=None, density_kg_m3=None, status='missing_source')
        if finite(t) and finite(sp) and 0 <= sp <= 50 and -3 <= t <= 45:
            pressure = float(gsw.p_from_z(-float(depth), latitude))
            sa = float(gsw.SA_from_SP(float(sp), pressure, longitude, latitude))
            ct = float(gsw.CT_from_t(sa, float(t), pressure))
            theta = float(gsw.pt0_from_t(sa, float(t), pressure))
            if all(isfinite(x) for x in (pressure, sa, ct, theta)):
                point.update(pressure_dbar=pressure, absolute_salinity_g_kg=sa,
                             conservative_temperature_c=ct, potential_temperature_c=theta, status='outside_gsw_funnel')
                if bool(gsw.infunnel(sa, ct, pressure)):
                    point.update(sigma0_kg_m3=float(gsw.sigma0(sa, ct)), density_kg_m3=float(gsw.rho(sa, ct, pressure)), status='valid')
        elif finite(t) and finite(sp):
            point['status'] = 'unsupported_source_range'
        points.append(point)
    layers = []
    for lower, upper in zip(points, points[1:]):
        z0, z1 = lower['depth_m'], upper['depth_m']
        t0, t1 = lower['in_situ_temperature_c'], upper['in_situ_temperature_c']
        gradient = (t1-t0)/(z1-z0) if t0 is not None and t1 is not None else None
        n2, pressure_mid = None, None
        if lower['status'] == upper['status'] == 'valid':
            squared, pressure = gsw.Nsquared([lower['absolute_salinity_g_kg'], upper['absolute_salinity_g_kg']],
                                            [lower['conservative_temperature_c'], upper['conservative_temperature_c']],
                                            [lower['pressure_dbar'], upper['pressure_dbar']], lat=latitude)
            if isfinite(float(squared[0])):
                n2, pressure_mid = float(squared[0]), float(pressure[0])
        layers.append(dict(top_depth_m=z0, bottom_depth_m=z1, midpoint_depth_m=(z0+z1)*0.5,
                           temperature_gradient_c_per_m=gradient, n_squared_s2=n2,
                           pressure_mid_dbar=pressure_mid,
                           n_squared_depth_m=float(-gsw.z_from_p(pressure_mid, latitude)) if pressure_mid is not None else None))
    heat = dict(value_j_m2=None, value_gj_m2=None, status='missing_support', top_depth_m=0,
                bottom_depth_m=depth_limit_m, reference_conservative_temperature_c=0, cp0_j_kg_k=CP0,
                name='Column potential-enthalpy content relative to CT = 0 degrees Celsius')
    if all(p['status'] == 'valid' for p in points) and points[-1]['depth_m'] == depth_limit_m:
        density_enthalpy = [p['density_kg_m3']*CP0*p['conservative_temperature_c'] for p in points]
        contributions = [(a+b)*0.5*(p1['depth_m']-p0['depth_m']) for a, b, p0, p1 in zip(density_enthalpy, density_enthalpy[1:], points, points[1:])]
        value = ordered_sum(contributions)
        heat.update(value_j_m2=value, value_gj_m2=value/1e9, status='available')
    return dict(points=points, layers=layers,
                mixed_layer=dict(density=mixed_layer(points, 'sigma0_kg_m3', 0.03),
                                 temperature=mixed_layer(points, 'potential_temperature_c', 0.2, absolute=True)),
                heat_content=heat)

"""Deterministic native-column comparisons. Display fields never enter this module."""
from bisect import bisect_left
from collections import Counter
from datetime import datetime
from functools import lru_cache
from math import asin, cos, fsum, isfinite, radians, sin, sqrt

from science.evidence_contracts import Comparison, MatchRow, MatchSettings, SampleMetrics
from science.instruments import InstrumentProfile, InstrumentSummary

REVIEW_SHA = '17f3e33d95003693c24b7fc5737b1dbe9369334b6ffce679964288b5f96483dd'
METHODS = [
    'Compare each original sample with one explicitly selected model snapshot. Signed time offset is observation time minus model time. The tolerance applies on either side of that snapshot, including collection endpoints. No model value is inferred at the observation time.',
    'Require coordinates inside the native subset. Select the nearest native column by great-circle distance on a sphere of radius 6371.0088 km; equal distances use the first native grid index. No search for a replacement wet column.',
    'Interpolate linearly between the immediately adjacent finite native depth levels at the observation depth. Exact native levels use that cell only. No extrapolation, masked-gap bridging or display-grid sampling.',
    'Retain original sample order and per-variable QC. Good-only narrows Argo and declared flags to 1; QARTOD 1 and WOCE 2 retain their source meanings. Pressure, position and time eligibility remain required.',
    'Temperature is in-situ Celsius; salinity is practical salinity. No potential-temperature, conservative-temperature or absolute-salinity substitution. Pressure-to-depth conversion is documented on the observation.',
    'Residual = model minus observed. Bias, RMSE and MAE use only accepted source samples with equal sample weights. Each excluded sample has one first-failed reason in gate order.',
]
CAVEATS = [
    'This historical HYCOM analysis assimilates observations including Argo. Agreement is not independent validation or evidence of forecast improvement.',
    'Coverage describes the actual eligible observation samples under these settings. It is not a confidence field or an estimate of unsampled ocean conditions.',
    'Samples within a profile are not independent and are not weighted by depth interval or ocean area. Statistics describe this selected profile, variable, snapshot and matching policy only.',
    'The default 6-hour, 5-km and 500-m bracket limits are project settings, not universal scientific standards. A narrow time window can legitimately return no pairs.',
    'One source file is held for provenance review because its calibration text mentions a verification run. The source QC flags remain unchanged; this is not a provider QC rejection.',
    'Comparisons currently use the checked observation library. Imported files remain available for profile inspection only.',
]


def epoch(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


@lru_cache(maxsize=512)
def nearest_column(latitude, longitude, latitudes, longitudes):
    """Full native-grid search, cached only by complete immutable coordinates."""
    lat_r = radians(latitude)
    best = (float('inf'), 0, 0)
    for y, lat in enumerate(latitudes):
        for x, lon in enumerate(longitudes):
            a = sin(radians(lat-latitude)/2)**2 + cos(lat_r)*cos(radians(lat))*sin(radians(lon-longitude)/2)**2
            distance = 2*6371.0088*asin(sqrt(min(1.0, max(0.0, a))))
            if distance < best[0]:
                best = (distance, y, x)
    return best


def summary(profile: InstrumentProfile):
    return InstrumentSummary.model_validate(profile.model_dump(include=set(InstrumentSummary.model_fields)))


def metrics(rows):
    residuals = [row.residual for row in rows if row.accepted]
    n = len(residuals)
    return SampleMetrics(count=n, bias=fsum(residuals)/n if n else None,
                         rmse=sqrt(fsum(r*r for r in residuals)/n) if n else None,
                         mae=fsum(abs(r) for r in residuals)/n if n else None,
                         maximum_abs_residual=max(map(abs, residuals)) if n else None)


def strict_coordinate_qc(level):
    scheme = level.coordinate_qc.get('scheme')
    if scheme in {'argo', 'declared'}:
        return all(level.coordinate_qc.get(k) == '1' for k in ('pressure', 'position', 'time'))
    # Other supported schemes are already narrowed by the P04 source adapter.
    return True


def compatible(parameter, spec, variable):
    if not parameter:
        return False
    if variable == 'temperature':
        return parameter.definition == 'In-situ sea-water temperature' and parameter.units == '°C' and spec.standard_name == 'sea_water_temperature' and spec.units == '°C'
    return parameter.definition == 'Practical salinity, PSS-78; not absolute salinity' and parameter.units == 'psu' and spec.standard_name in {'sea_water_salinity', 'sea_water_practical_salinity'} and spec.units == 'psu'


def compare(manifest, manifest_sha, library_sha, profile, settings: MatchSettings, values):
    """Pure comparison over checked native values; no IO or mutation."""
    coords = manifest.coordinates
    latitudes, longitudes, depths = tuple(coords.latitude), tuple(coords.longitude), coords.depth_m
    model_time = coords.times[settings.time_index]
    model_epoch = epoch(model_time)
    spec = next(v for v in manifest.variables if v.id == settings.variable)
    parameter = profile.parameters.get(settings.variable)
    compatible_variable = compatible(parameter, spec, settings.variable)
    if profile.instrument == 'ctd' and settings.variable == 'temperature':
        # This checked CTD Exchange source does not establish its temperature scale.
        # A future adapter must verify that metadata before quantitative temperature use.
        compatible_variable = compatible_variable and profile.metadata.get('temperature_scale') == 'ITS-90'
    rows = []
    for level in profile.levels:
        reading = level.readings.get(settings.variable)
        row = MatchRow(sample_index=level.index, observation_time=level.time,
                       latitude=level.latitude, longitude=level.longitude, depth_m=level.depth_m,
                       observed=reading.value if reading else None, reason='accepted',
                       qc=reading.qc if reading else '', mode=parameter.mode if parameter else '',
                       time_offset_hours=(epoch(level.time)-model_epoch)/3600)
        reason = None
        if profile.source_sha256 == REVIEW_SHA:
            reason = 'source_review'
        elif not parameter or not reading:
            reason = 'variable_unavailable'
        elif not compatible_variable:
            reason = 'incompatible_variable'
        elif not level.coordinate_eligible or (settings.qc == 'good' and not strict_coordinate_qc(level)):
            reason = 'coordinate_qc'
        elif reading.value is None:
            reason = 'missing_value'
        elif not reading.accepted or (settings.qc == 'good' and parameter.qc_scheme in {'argo', 'declared'} and reading.qc != '1'):
            reason = 'observation_qc'
        elif level.depth_m is None or level.depth_m < 0:
            reason = 'invalid_depth'
        elif not (latitudes[0] <= level.latitude <= latitudes[-1] and longitudes[0] <= level.longitude <= longitudes[-1]):
            reason = 'outside_domain'
        elif abs(row.time_offset_hours) > settings.time_window_hours:
            reason = 'time_window'
        else:
            distance, y, x = nearest_column(level.latitude, level.longitude, latitudes, longitudes)
            row.distance_km, row.model_latitude, row.model_longitude = distance, latitudes[y], longitudes[x]
            z = level.depth_m
            if distance > settings.distance_km:
                reason = 'distance'
            elif z < depths[0] or z > depths[-1]:
                reason = 'depth_outside'
            else:
                upper = bisect_left(depths, z)
                lower = upper if depths[upper] == z else upper-1
                row.lower_depth_m, row.upper_depth_m = depths[lower], depths[upper]
                lo = values[(lower*len(latitudes)+y)*len(longitudes)+x]
                hi = values[(upper*len(latitudes)+y)*len(longitudes)+x]
                row.model_lower_value = lo if isfinite(lo) else None
                row.model_upper_value = hi if isfinite(hi) else None
                if not isfinite(lo) or not isfinite(hi):
                    reason = 'masked_bracket'
                elif depths[upper]-depths[lower] > settings.max_vertical_gap_m:
                    reason = 'vertical_gap'
                else:
                    row.upper_weight = 0.0 if lower == upper else (z-depths[lower])/(depths[upper]-depths[lower])
                    row.model = lo + (hi-lo)*row.upper_weight
                    row.residual = row.model - reading.value
                    row.accepted = True
        row.reason = reason or 'accepted'
        rows.append(row)
    counts = dict(Counter(row.reason for row in rows if not row.accepted))
    stats = metrics(rows)
    return Comparison(case_id=manifest.case.id, manifest_sha256=manifest_sha,
                      observation_library_sha256=library_sha, model_time=model_time, profile=summary(profile),
                      settings=settings, units=spec.units, total_samples=len(rows), matched_count=stats.count,
                      excluded_count=len(rows)-stats.count, exclusion_counts=counts, metrics=stats,
                      rows=rows, methods=METHODS, caveats=CAVEATS)

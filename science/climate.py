"""Explicit monthly/seasonal field arithmetic on one checked native grid."""
import numpy as np
from science.contracts import UnsupportedData

METHODS = [
    'Historical event labels use the pinned official index snapshot and its declared definition. RONI, ONI and IOD are separate quantities.',
    'GODAS supplies monthly mean potential temperature referenced to the surface, converted from kelvin by subtracting 273.15 in float64. It is not HYCOM in-situ temperature or a direct instrument measurement.',
    'The fixed 1991-2020 baseline uses the same calendar month at each native cell. Every one of the 30 source years is required; an incomplete cell remains missing.',
    'SON is the equal-weight mean of September, October and November monthly means, using fixed month order. All three months must be finite. This is not a day-weighted seasonal mean.',
    'Anomaly is the selected monthly or SON potential temperature minus its matching GODAS 1991-2020 baseline. Difference is selected event minus reference event at the same source coordinates and calendar window.',
    'The section uses the native latitude nearest the equator, with no equatorial interpolation. Profiles and selected values use exact source longitude and depth indices. No missing cells are filled.',
    'Pacific source longitudes stay on a continuous 0-360 degree axis. Display labels may use east/west notation; crossing 180 degrees does not reorder or interpolate source cells.',
    'Indian Ocean context uses the same product, calendar window, grid depths and baseline. Selected-year differences do not establish an ENSO-to-IOD or local-weather causal relationship.',
]
CAVEATS = [
    'These are selected historical monthly analyses, not live conditions, an event-strength simulation or a new climate forecast.',
    'The surface ENSO/IOD indices and subsurface GODAS potential-temperature anomalies use different datasets and definitions. A similar-looking pattern does not make them the same measurement.',
    'An IOD episode documented by an agency may have different dates from the displayed three-month index window. The numerical value is not silently converted into an episode label.',
    'Nearby Argo profiles retain their actual dates, locations and original quality flags. Monthly potential temperature is not directly compared with instantaneous in-situ temperature.',
    'Assimilated observations may contribute to GODAS. Their presence or agreement would not establish independent model validation.',
    'The supplied upper-ocean grid, three historical seasons and selected profiles do not provide complete ocean or climate-event coverage.',
]


def ordered_mean(arrays):
    """Complete support only; fixed additions avoid Python sum version changes."""
    if not arrays:
        raise UnsupportedData('incomplete_climate_window', 'No source months are available for this calendar window.')
    arrays = [np.asarray(a, dtype=np.float64) for a in arrays]
    if len({a.shape for a in arrays}) != 1:
        raise UnsupportedData('incompatible_grid', 'Climate fields must share exactly the same native coordinates.')
    total = np.zeros_like(arrays[0], dtype=np.float64)
    valid = np.ones(arrays[0].shape, dtype=bool)
    for a in arrays:
        valid &= np.isfinite(a)
        total = total + np.where(np.isfinite(a), a, 0.0)
    return np.where(valid, total / len(arrays), np.nan)


def finite_list(values):
    return [float(v) if np.isfinite(v) else None for v in np.asarray(values).ravel()]


def signed_difference(a, b):
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        raise UnsupportedData('incompatible_grid', 'Both climate fields must have matching dimensions.')
    return np.where(np.isfinite(a) & np.isfinite(b), a-b, np.nan)


def section_result(values, baseline, latitudes, longitudes, depths, west, east):
    expected = (len(depths), len(latitudes), len(longitudes))
    if values.shape != expected or baseline.shape != expected:
        raise UnsupportedData('case_integrity_error', 'Climate array shape does not match its original coordinate axes.')
    y = min(range(len(latitudes)), key=lambda i: (abs(latitudes[i]), i))
    xi = [i for i, lon in enumerate(longitudes) if west <= lon <= east]
    if not xi:
        raise UnsupportedData('outside_coverage', 'The selected section is outside the prepared climate grid.')
    a = values[:, y, xi]
    b = baseline[:, y, xi]
    anomaly = signed_difference(a, b)
    return dict(latitude=float(latitudes[y]), latitude_index=y,
                longitude=[float(longitudes[i]) for i in xi], longitude_source_indices=xi,
                depth_m=list(depths), shape=list(a.shape), dimensions=['depth', 'longitude'],
                potential_temperature_c=finite_list(a), baseline_c=finite_list(b),
                anomaly_c=finite_list(anomaly), missing_value=None,
                baseline_required_year_count=30,
                note='Native latitude nearest 0 degrees. Connecting colour cells does not add measurements between source coordinates.')


def common_scale(sections, key, symmetric=False):
    values = [v for s in sections for v in s[key] if v is not None]
    if not values:
        return dict(min=None, max=None, units='degrees_Celsius', symmetric=symmetric)
    if symmetric:
        extent = max(abs(min(values)), abs(max(values)))
        return dict(min=-extent, max=extent, units='degrees_Celsius', symmetric=True)
    return dict(min=min(values), max=max(values), units='degrees_Celsius', symmetric=False)


def profile_from_section(section, longitude_index):
    nz, nx = section['shape']
    if not 0 <= longitude_index < nx:
        raise UnsupportedData('invalid_selection', 'Choose a supplied native Pacific longitude.')
    return dict(latitude=section['latitude'], longitude=section['longitude'][longitude_index],
                longitude_index=longitude_index, depth_m=section['depth_m'],
                **{key:[section[key][z*nx+longitude_index] for z in range(nz)]
                   for key in ('potential_temperature_c', 'baseline_c', 'anomaly_c')})

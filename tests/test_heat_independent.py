"""Independent P12 scientific acceptance.

Expected events come from pinned upstream code, not production event helpers.
Source profiles are decoded from original packed provider NetCDF. Published
TEOS-10 examples check the installed library; they are not field validation.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import types
import warnings

import gsw
import numpy as np
import pytest

from science.contracts import UnsupportedData
from science.heat import climatology, detect_events, mixed_layer, profile_diagnostics

ROOT = Path(__file__).resolve().parents[1]
CASES = ('bay-bengal-2024-01', 'arabian-sea-2024-01')
SURFACE_LOCATIONS = ('bay-west', 'bay-center', 'bay-east', 'arabian-west', 'arabian-center', 'arabian-east')
REFERENCE_SHA = '3f47a51382f68894f34deaf6b466c944cf4f88f92a09a7f00f6d6acd609a0db8'
CP0 = 3991.86795711963
NCEI_PRIMARY_SHA = {
    '19820101': 'ef52b866b5ba5b079198bc20b5fb960f719a0bf6df458665428b459dabd64581',
    '19960701': 'f1752024ed7ebb111bb95767f4bac31de53e5c3d40c2a1b80cb2df71264745bc',
    '20240107': '898a3453dd05712027170b5619e84f488ba7dd5035821635b18d44efffd87ce8',
}


@lru_cache(maxsize=1)
def reference():
    path = ROOT / 'data/reference/p12/marineHeatWaves.py'
    if not path.exists():
        pytest.skip('Pinned offline reference absent; run python -m science.acquire_heat_reference.')
    body = path.read_bytes()
    assert hashlib.sha256(body).hexdigest() == REFERENCE_SHA
    module = types.ModuleType('p12_oliver_reference')
    # Compatibility spelling only; no numerical or event logic is altered.
    source = body.decode('utf-8').replace('np.NaN', 'np.nan')
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def days(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return [first + timedelta(days=i) for i in range((last-first).days+1)]


@lru_cache(maxsize=14)
def original_fields(case_id, time_index):
    """Provider decoding intentionally does not call CaseStore or adapters."""
    import netCDF4
    manifest = json.loads((ROOT / 'casepacks' / case_id / 'manifest.json').read_text(encoding='utf-8'))
    record = manifest['sources'][0]['files'][time_index]
    path = ROOT / record['path']
    if not path.exists():
        pytest.skip('Original packed provider archive is absent; acquire this case to run its source check.')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
    with netCDF4.Dataset(path) as source:
        values = {}
        for name, standard_name, units in (
            ('water_temp', 'sea_water_temperature', 'degC'),
            ('salinity', 'sea_water_salinity', 'psu'),
        ):
            variable = source[name]
            assert variable.standard_name == standard_name
            assert variable.units == units
            assert variable.dimensions == ('time', 'depth', 'lat', 'lon')
            if name == 'water_temp':
                assert variable.comment == 'in-situ temperature'
            variable.set_auto_maskandscale(False)
            packed = np.asarray(variable[0])
            decoded = packed.astype(np.float64) * float(variable.scale_factor) + float(variable.add_offset)
            decoded[packed == variable._FillValue] = np.nan
            values[name] = decoded
        coords = {name: np.asarray(source[name][:], dtype=np.float64) for name in ('depth', 'lat', 'lon')}
    return coords, values


SA_EXAMPLE = np.array([34.7118, 34.8915, 35.0256, 34.8472, 34.7366, 34.7324])
CT_EXAMPLE = np.array([28.8099, 28.4392, 22.7862, 10.2262, 6.8272, 4.3236])
P_EXAMPLE = np.array([10., 50., 125., 250., 600., 1000.])
T_EXAMPLE = np.array([28.7856, 28.4329, 22.8103, 10.2600, 6.8863, 4.4036])


def test_published_teos10_pressure_example():
    # https://www.teos-10.org/pubs/gsw/html/gsw_p_from_z.html
    expected = [10.055726724518, 50.283543374874, 125.731858435610,
                251.540299593468, 604.210012340727, 1007.990337692001]
    np.testing.assert_allclose(gsw.p_from_z(-P_EXAMPLE, 4), expected, rtol=0, atol=1e-9)


def test_published_teos10_absolute_salinity_example():
    # The official 2015 web example differs from the pinned 3.6.20 release.
    # Use its version-matched upstream check cast, not relaxed tolerances.
    path = ROOT / 'data/reference/p12/gsw_cv_v3_0.npz'
    if not path.exists():
        pytest.skip('Pinned GSW reference absent; run python -m science.acquire_heat_reference.')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '402d9aa4aced457b53402839708a40ebd9f7af2f7c02604a4af4ce57f7daa1ee'
    with np.load(path) as cast:
        actual = gsw.SA_from_SP(cast['SP_chck_cast'], cast['p_chck_cast'], cast['long_chck_cast'], cast['lat_chck_cast'])
        np.testing.assert_allclose(actual, cast['SA_from_SP'], rtol=0, atol=float(cast['SA_from_SP_ca']), equal_nan=True)


def test_published_teos10_conservative_temperature_example():
    # https://www.teos-10.org/pubs/gsw/html/gsw_CT_from_t.html
    expected = [28.809919826700281, 28.439227816091140, 22.786176893078498,
                10.226189266620782, 6.827213633479988, 4.323575748610455]
    np.testing.assert_allclose(gsw.CT_from_t(SA_EXAMPLE, T_EXAMPLE, P_EXAMPLE), expected, rtol=0, atol=1e-11)


def test_published_teos10_potential_temperature_example():
    # https://www.teos-10.org/pubs/gsw/html/gsw_pt0_from_t.html
    expected = [28.783196819670632, 28.420983342398962, 22.784930399117108,
                10.230523661095731, 6.829230224409661, 4.324510571845719]
    np.testing.assert_allclose(gsw.pt0_from_t(SA_EXAMPLE, T_EXAMPLE, P_EXAMPLE), expected, rtol=0, atol=1e-11)


def test_published_teos10_sigma0_example():
    # https://www.teos-10.org/pubs/gsw/html/gsw_sigma0.html
    expected = [21.797900819337656, 22.052215404397316, 23.892985307893923,
                26.667608665972011, 27.107380455119710, 27.409748977090885]
    np.testing.assert_allclose(gsw.sigma0(SA_EXAMPLE, CT_EXAMPLE), expected, rtol=0, atol=1e-10)


def test_published_teos10_density_example():
    # https://www.teos-10.org/pubs/gsw/html/gsw_rho.html
    expected = [1021.839935738108, 1022.262457966867, 1024.427195413316,
                1027.790152759127, 1029.837779000189, 1032.002453224572]
    np.testing.assert_allclose(gsw.rho(SA_EXAMPLE, CT_EXAMPLE, P_EXAMPLE), expected, rtol=0, atol=1e-9)


def test_published_teos10_stratification_example():
    # https://www.teos-10.org/pubs/gsw/html/gsw_Nsquared.html
    expected = np.array([.060843209693499, .235723066151305, .216599928330380,
                         .012941204313372, .008434782795209]) * .001
    n2, p_middle = gsw.Nsquared(SA_EXAMPLE, CT_EXAMPLE, P_EXAMPLE, lat=4)
    np.testing.assert_allclose(n2, expected, rtol=0, atol=1e-14)
    np.testing.assert_array_equal(p_middle, [30., 87.5, 187.5, 425., 800.])


@pytest.mark.parametrize('case_id', CASES)
def test_checked_source_temperature_is_in_situ_and_depths_are_irregular(case_id):
    coords, fields = original_fields(case_id, 0)
    assert coords['depth'][0] == 0
    assert len(set(np.diff(coords['depth']))) > 5
    assert np.isfinite(fields['water_temp']).any()
    assert np.isfinite(fields['salinity']).any()


def test_offline_reference_identity():
    assert callable(reference().detect)


@lru_cache(maxsize=1)
def synthetic_baseline():
    calendar = days('1982-01-01', '2011-12-31')
    # Fixed ordinary arithmetic series with leap days and a baseline trend.
    temperature = [24 + 3*np.sin((d.timetuple().tm_yday-30)*2*np.pi/365.25)
                   + .017*(d.year-1982) + .12*np.cos(i*.37)
                   for i, d in enumerate(calendar)]
    return calendar, np.array(temperature)


def upstream_analysis(calendar, values, baseline_dates, baseline_values):
    with warnings.catch_warnings():
        # Pinned upstream uses one-element arrays as scalars. The initial run
        # retains these warnings; silence their repeated copies, not failures.
        warnings.filterwarnings('ignore', message='Conversion of an array with ndim > 0 to a scalar is deprecated', category=DeprecationWarning)
        return reference().detect(
            np.array([d.toordinal() for d in calendar]), np.array(values, dtype=float).copy(),
            climatologyPeriod=[1982, 2011], pctile=90, windowHalfWidth=5,
            smoothPercentile=True, smoothPercentileWidth=31, minDuration=5,
            joinAcrossGaps=True, maxGap=2, maxPadLength=False,
            alternateClimatology=[np.array([d.toordinal() for d in baseline_dates]),
                                  np.array(baseline_values, dtype=float)],
        )


def test_seasonal_mean_and_threshold_match_pinned_complete_reference():
    baseline_dates, baseline_values = synthetic_baseline()
    calendar = days('2024-01-01', '2024-12-31')
    _, expected = upstream_analysis(calendar, np.full(366, 20.), baseline_dates, baseline_values)
    actual = climatology(baseline_dates, baseline_values)
    np.testing.assert_allclose(actual['seasonal_mean_c'], expected['seas'], rtol=0, atol=1e-10)
    np.testing.assert_allclose(actual['threshold_c'], expected['thresh'], rtol=0, atol=1e-10)
    assert actual['pool_count'][0] == 325
    assert actual['pool_count'][-1] == 325
    assert actual['pool_count'][59] == 0  # Feb 29 is interpolated, never independently pooled.
    assert actual['pool_count'][60] == 330


@pytest.mark.parametrize('year', [2023, 2024])
def test_complete_synthetic_events_match_reference_dates_and_metrics(year):
    baseline_dates, baseline_values = synthetic_baseline()
    calendar = days(f'{year}-01-01', f'{year}-12-31')
    # A varying full year exercises leap-day and seasonal threshold handling.
    values = np.array([24.45 + 3*np.sin((d.timetuple().tm_yday-30)*2*np.pi/365.25)
                       + .35*np.sin(i*.091) + .8*((i//27) % 4 == 0)
                       for i, d in enumerate(calendar)])
    expected, _ = upstream_analysis(calendar, values, baseline_dates, baseline_values)
    actual = detect_events(calendar, values, climatology(baseline_dates, baseline_values))['events']
    assert len(actual) == expected['n_events'] > 0
    for i, event in enumerate(actual):
        assert event['start'] == date.fromordinal(int(expected['time_start'][i])).isoformat()
        assert event['end'] == date.fromordinal(int(expected['time_end'][i])).isoformat()
        assert event['duration_days'] == expected['duration'][i]
        assert event['peak_date'] == date.fromordinal(int(expected['time_peak'][i])).isoformat()
        assert event['mean_intensity_c'] == pytest.approx(expected['intensity_mean'][i], abs=1e-10)
        assert event['max_intensity_c'] == pytest.approx(expected['intensity_max'][i], abs=1e-10)
        assert event['cumulative_intensity_c_days'] == pytest.approx(expected['intensity_cumulative'][i], abs=1e-8)


def test_baseline_does_not_leak_outside_years():
    base_dates, base = synthetic_baseline()
    calendar = days('1981-01-01', '2012-12-31')
    values = [-100000. if d.year == 1981 else 100000. if d.year == 2012
              else float(base[(d-base_dates[0]).days]) for d in calendar]
    assert climatology(calendar, values) == climatology(base_dates, base)


@pytest.mark.parametrize('bad', [None, float('nan'), float('inf')])
def test_missing_baseline_is_rejected_without_filling(bad):
    calendar, values = synthetic_baseline()
    broken = values.tolist()
    broken[2345] = bad
    with pytest.raises(UnsupportedData, match='complete daily baseline'):
        climatology(calendar, broken)


@pytest.mark.parametrize('which', ['gap', 'reversed', 'duplicate'])
def test_irregular_daily_calendar_is_rejected(which):
    calendar = days('2024-01-01', '2024-01-20')
    if which == 'gap':
        calendar.pop(8)
    elif which == 'reversed':
        calendar.reverse()
    else:
        calendar[9] = calendar[8]
    with pytest.raises(UnsupportedData, match='consecutive daily'):
        detect_events(calendar, [30.]*len(calendar), flat_climatology())


def flat_climatology(mean=20., threshold=25.):
    return {'seasonal_mean_c': [mean]*366, 'threshold_c': [threshold]*366}


def fixture_events(values, start='2024-01-01'):
    calendar = [date.fromisoformat(start)+timedelta(days=i) for i in range(len(values))]
    return detect_events(calendar, values, flat_climatology())


@pytest.mark.parametrize('duration, expected', [(4, 0), (5, 1), (6, 1)])
def test_five_day_minimum_and_strict_equality(duration, expected):
    actual = fixture_events([25.]*2+[26.]*duration+[25.]*2)
    assert len(actual['events']) == expected
    assert not actual['series'][0]['exceeds_threshold']
    if expected:
        assert actual['events'][0]['duration_days'] == duration
        assert actual['events'][0]['complete_boundaries']


@pytest.mark.parametrize('gap, expected_events', [(1, 1), (2, 1), (3, 2)])
def test_only_short_observed_gaps_join_and_count_in_metrics(gap, expected_events):
    result = fixture_events([24.]+[26.]*5+[23.]*gap+[27.]*5+[24.])
    assert len(result['events']) == expected_events
    if expected_events == 1:
        event = result['events'][0]
        assert event['duration_days'] == 10+gap
        assert event['exceedance_days'] == 10
        assert event['bridged_days'] == gap
        assert event['cumulative_intensity_c_days'] == 65+3*gap
        assert event['mean_intensity_c'] == (65+3*gap)/(10+gap)


def test_unqualified_short_run_is_not_promoted_by_gap_join():
    events = fixture_events([24.]+[26.]*4+[24.]+[27.]*5+[24.])['events']
    assert len(events) == 1
    assert events[0]['start'] == '2024-01-07'
    assert events[0]['duration_days'] == 5


@pytest.mark.parametrize('missing', [None, float('nan'), float('inf')])
def test_missing_analysis_value_splits_and_flags_both_boundaries(missing):
    result = fixture_events([24.]+[26.]*5+[missing]+[27.]*5+[24.])
    assert len(result['events']) == 2
    assert result['series'][6]['sst_c'] is None
    assert result['series'][6]['exceeds_threshold'] is None
    assert result['events'][0]['right_boundary_unknown']
    assert result['events'][1]['left_boundary_unknown']
    assert not result['events'][0]['complete_boundaries']


def test_event_crosses_year_with_original_bounds():
    event = fixture_events([24.]+[26.]*10+[24.], '2023-12-26')['events'][0]
    assert event['start'] == '2023-12-27'
    assert event['end'] == '2024-01-05'
    assert event['duration_days'] == 10


def test_context_edges_are_declared_incomplete():
    event = fixture_events([26.]*5)['events'][0]
    assert event['left_boundary_unknown'] and event['right_boundary_unknown']
    assert not event['complete_boundaries']


@pytest.mark.parametrize('case_id', CASES)
@pytest.mark.parametrize('time_index', [0, 6])
@pytest.mark.parametrize('column', [0, 1])
def test_original_model_columns_and_independent_integral(case_id, time_index, column):
    from scipy.integrate import trapezoid
    coords, fields = original_fields(case_id, time_index)
    z = coords['depth']
    wet = np.argwhere(np.isfinite(fields['water_temp'][np.flatnonzero(z == 1000)[0]])
                      & np.isfinite(fields['salinity'][np.flatnonzero(z == 1000)[0]]))
    row, col = wet[len(wet)//(column+2)]
    latitude, longitude = float(coords['lat'][row]), float(coords['lon'][col])
    t, sp = fields['water_temp'][:, row, col], fields['salinity'][:, row, col]
    actual = profile_diagnostics(z.tolist(), t.tolist(), sp.tolist(), latitude, longitude, 1000)
    use = z <= 1000
    p = gsw.p_from_z(-z[use], latitude)
    sa = gsw.SA_from_SP(sp[use], p, longitude, latitude)
    ct = gsw.CT_from_t(sa, t[use], p)
    theta = gsw.pt0_from_t(sa, t[use], p)
    rho = gsw.rho(sa, ct, p)
    sigma0 = gsw.sigma0(sa, ct)
    for key, expected in [('in_situ_temperature_c', t[use]), ('practical_salinity', sp[use]),
                          ('pressure_dbar', p), ('absolute_salinity_g_kg', sa),
                          ('conservative_temperature_c', ct), ('potential_temperature_c', theta),
                          ('density_kg_m3', rho), ('sigma0_kg_m3', sigma0)]:
        np.testing.assert_allclose([x[key] for x in actual['points']], expected, rtol=0, atol=1e-10)
    n2, pmid = gsw.Nsquared(sa, ct, p, lat=latitude)
    np.testing.assert_allclose([x['n_squared_s2'] for x in actual['layers']], n2, rtol=0, atol=1e-14)
    np.testing.assert_allclose([x['pressure_mid_dbar'] for x in actual['layers']], pmid, rtol=0, atol=1e-10)
    np.testing.assert_allclose([x['temperature_gradient_c_per_m'] for x in actual['layers']], np.diff(t[use])/np.diff(z[use]), rtol=0, atol=1e-12)
    expected_heat = float(trapezoid(rho*CP0*ct, x=z[use]))
    assert actual['heat_content']['status'] == 'available'
    assert actual['heat_content']['value_j_m2'] == pytest.approx(expected_heat, rel=2e-15)


def test_irregular_actual_depth_gradient_is_signed_and_not_index_based():
    depths = [0., 3., 10., 25., 60., 100.]
    t = [27-.05*z for z in depths]
    result = profile_diagnostics(depths, t, [35.]*len(depths), 13., 87., 100)
    np.testing.assert_allclose([x['temperature_gradient_c_per_m'] for x in result['layers']], -.05, rtol=0, atol=1e-14)


def test_linear_potential_enthalpy_density_has_closed_form_integral():
    from scipy.optimize import brentq
    depths = [0., 3., 10., 25., 60., 100.]
    # Select t(z) independently so rho*cp0*CT is an exactly linear target.
    # The expected integral is analytical, not another production trapezoid.
    a, b = 1.1e8, -1.5e5
    temperatures = []
    for z in depths:
        p = float(gsw.p_from_z(-z, 13.))
        sa = float(gsw.SA_from_SP(35., p, 87., 13.))
        def residual(t):
            ct = float(gsw.CT_from_t(sa, t, p))
            return float(gsw.rho(sa, ct, p))*CP0*ct-(a+b*z)
        temperatures.append(brentq(residual, 5, 40, xtol=1e-13))
    result = profile_diagnostics(depths, temperatures, [35.]*len(depths), 13., 87., 100)
    expected = a*100+b*100**2/2
    assert result['heat_content']['value_j_m2'] == pytest.approx(expected, rel=5e-14)


def test_missing_source_never_bridges_gradient_stratification_or_integral():
    result = profile_diagnostics([0, 10, 20, 50, 100], [27, 27, None, 22, 20], [35]*5, 13, 87, 100)
    assert result['layers'][1]['temperature_gradient_c_per_m'] is None
    assert result['layers'][2]['temperature_gradient_c_per_m'] is None
    assert result['layers'][1]['n_squared_s2'] is None
    assert result['layers'][2]['n_squared_s2'] is None
    assert result['mixed_layer']['temperature']['status'] == 'missing_support'
    assert result['mixed_layer']['density']['status'] == 'missing_support'
    assert result['heat_content']['value_j_m2'] is None


def test_statically_unstable_negative_n2_remains_visible():
    result = profile_diagnostics([0, 10, 30, 100], [20, 21, 24, 28], [35]*4, 13, 87, 100)
    assert all(x['n_squared_s2'] < 0 for x in result['layers'])


def test_density_crossing_is_interpolated_at_first_threshold():
    points = [dict(depth_m=z, sigma0_kg_m3=v) for z, v in [(0, 23), (10, 23), (20, 23.02), (40, 23.06), (100, 24)]]
    actual = mixed_layer(points, 'sigma0_kg_m3', .03)
    assert actual['status'] == 'crossing'
    assert actual['depth_m'] == pytest.approx(25, abs=1e-10)


def test_absolute_theta_crossing_handles_signed_reversal_inside_interval():
    points = [dict(depth_m=z, potential_temperature_c=v) for z, v in [(0, 20), (10, 20), (20, 20.1), (40, 19.7), (100, 19)]]
    actual = mixed_layer(points, 'potential_temperature_c', .2, absolute=True)
    # Interpolate theta itself: +0.1 to -0.3 crosses -0.2 at 35m.
    assert actual['depth_m'] == pytest.approx(35, abs=1e-10)


def test_no_crossing_is_a_bound_not_the_bottom_depth():
    points = [dict(depth_m=z, sigma0_kg_m3=v) for z, v in [(0, 23), (10, 23), (100, 23.01)]]
    actual = mixed_layer(points, 'sigma0_kg_m3', .03)
    assert actual['depth_m'] is None
    assert actual['status'] == 'no_crossing'
    assert actual['supported_to_m'] == 100


@pytest.mark.parametrize('depths, limit', [([0, 10, 30, 100], 90), ([1, 10, 30, 100], 100), ([0, 10, 10, 100], 100)])
def test_unsupported_integration_bounds_and_depth_order_are_rejected(depths, limit):
    with pytest.raises(UnsupportedData):
        profile_diagnostics(depths, [20]*4, [35]*4, 13, 87, limit)


def surface_file(location_id):
    folder = ROOT / 'casepacks/heat'
    path = folder / 'manifest.json'
    if not path.exists():
        pytest.skip('Real daily SST pack has not been acquired.')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    location = next(p for p in manifest['locations'] if p['id'] == location_id)
    body = (folder / location['path']).read_bytes()
    assert hashlib.sha256(body).hexdigest() == location['sha256']
    return location, json.loads(body)


@pytest.mark.parametrize('location_id', SURFACE_LOCATIONS)
def test_real_surface_series_matches_independent_reference(location_id):
    _, source = surface_file(location_id)
    calendar = [date.fromisoformat(d) for d in source['dates']]
    values = np.asarray(source['sst_c'], dtype=float)
    baseline_indices = [i for i, d in enumerate(calendar) if 1982 <= d.year <= 2011]
    context_indices = [i for i, d in enumerate(calendar) if 2022 <= d.year <= 2025]
    baseline_dates = [calendar[i] for i in baseline_indices]
    context_dates = [calendar[i] for i in context_indices]
    assert baseline_dates == days('1982-01-01', '2011-12-31')
    assert context_dates == days('2022-01-01', '2025-12-31')
    assert np.isfinite(values).all()
    expected, curves = upstream_analysis(context_dates, values[context_indices], baseline_dates, values[baseline_indices])
    clim = climatology(calendar, values)
    actual = detect_events(context_dates, values[context_indices], clim)
    np.testing.assert_allclose([x['seasonal_mean_c'] for x in actual['series']], curves['seas'], rtol=0, atol=1e-10)
    np.testing.assert_allclose([x['threshold_c'] for x in actual['series']], curves['thresh'], rtol=0, atol=1e-10)
    assert len(actual['events']) == expected['n_events']
    for i, event in enumerate(actual['events']):
        assert event['start'] == date.fromordinal(int(expected['time_start'][i])).isoformat()
        assert event['end'] == date.fromordinal(int(expected['time_end'][i])).isoformat()
        assert event['duration_days'] == expected['duration'][i]
        assert event['peak_date'] == date.fromordinal(int(expected['time_peak'][i])).isoformat()
        assert event['max_intensity_c'] == pytest.approx(expected['intensity_max'][i], abs=1e-10)
        assert event['mean_intensity_c'] == pytest.approx(expected['intensity_mean'][i], abs=1e-10)
        assert event['cumulative_intensity_c_days'] == pytest.approx(expected['intensity_cumulative'][i], abs=1e-8)


@pytest.mark.parametrize('location_id', SURFACE_LOCATIONS)
@pytest.mark.parametrize('stamp,decimal_decode', [('19820101', True), ('19960701', False), ('20240107', False)])
def test_original_ncei_file_confirms_preferred_surface_value(location_id, stamp, decimal_decode):
    import netCDF4
    location, source = surface_file(location_id)
    path = ROOT / f'data/raw/heat/oisst-avhrr-v02r01.{stamp}.nc'
    if not path.exists():
        pytest.skip('Independent original NCEI daily file is absent.')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == NCEI_PRIMARY_SHA[stamp]
    with netCDF4.Dataset(path) as daily:
        latitude, longitude = np.asarray(daily['lat'][:]), np.asarray(daily['lon'][:])
        yi = np.flatnonzero(latitude == location['latitude'])
        xi = np.flatnonzero(longitude == location['longitude'])
        assert len(yi) == len(xi) == 1
        assert daily['sst'].units == 'Celsius'
        day = f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}'
        assert netCDF4.num2date(daily['time'][:], daily['time'].units)[0].strftime('%Y-%m-%d') == day
        decoded = float(daily['sst'][0, 0, int(yi[0]), int(xi[0])])
        if decimal_decode:
            # The checked legacy AOML date uses decimal-centidegree decoding.
            daily['sst'].set_auto_maskandscale(False)
            packed = int(daily['sst'][0, 0, int(yi[0]), int(xi[0])])
            decoded = float(np.float32(packed/100.0))
        # Recovered 1996 PSL and modern AOML _T_V1 reproduce the primary
        # binary Float32 scale decoding exactly on the checked dates.
        i = source['dates'].index(day)
        assert source['sst_c'][i] == decoded


@pytest.mark.parametrize('day,aoml_file,psl_file,psl_index,decimal_aoml', [
    ('19820101', 'aoml-old-1982.nc', 'sst-1982-000-089.dods', 0, True),
    ('20240107', 'aoml-modern-2024.nc', 'sst-2024-000-029.dods', 6, False),
])
def test_original_packed_source_explains_distributor_float32_policy(day, aoml_file, psl_file, psl_index, decimal_aoml):
    """Checked legacy/modern products have exact, different unpacking rules.

    This is an empirical check of two retained source dates, not a claim
    about every historical distributor byte. No production values change.
    """
    import netCDF4
    from pydap.client import open_dods_file
    folder = ROOT / 'data/raw/heat'
    primary = folder / f'oisst-avhrr-v02r01.{day}.nc'
    if not all(path.exists() for path in (primary, folder/aoml_file, folder/psl_file)):
        pytest.skip('Retained primary/distributor source comparison files are absent.')
    assert hashlib.sha256(primary.read_bytes()).hexdigest() == NCEI_PRIMARY_SHA[day]
    with netCDF4.Dataset(primary) as source:
        variable = source['sst']
        auto = np.asarray(variable[0, 0, [413, 429], 268:356])
        scale, offset = variable.scale_factor, variable.add_offset
        assert np.asarray(scale).dtype == np.dtype('float32')
        assert scale == np.float32(.01) and offset == 0
        variable.set_auto_maskandscale(False)
        packed = np.asarray(variable[0, 0, [413, 429], 268:356])
        assert packed.dtype == np.dtype('int16')
        valid = packed != variable._FillValue
    decimal = np.asarray(packed.astype(np.float64) / 100, dtype=np.float32)
    binary = np.asarray(packed * scale + offset, dtype=np.float32)
    np.testing.assert_array_equal(auto[valid], binary[valid])
    with netCDF4.Dataset(folder/aoml_file) as source:
        np.testing.assert_array_equal(source['latitude'][:], [13.375, 17.375])
        np.testing.assert_array_equal(source['longitude'][:], np.arange(67.125, 89, .25))
        dates = [t.strftime('%Y%m%d') for t in netCDF4.num2date(source['time'][:], source['time'].units)]
        aoml = np.asarray(source['sst'][dates.index(day)])
    psl = np.asarray(open_dods_file(str(folder/psl_file))['sst'].array.data[psl_index])
    assert int(valid.sum()) == 116
    np.testing.assert_array_equal(psl[valid], binary[valid])
    np.testing.assert_array_equal(aoml[valid], (decimal if decimal_aoml else binary)[valid])
    # The conversion distinction is observable, not a vacuous equal fixture.
    assert np.count_nonzero(decimal[valid] != binary[valid]) > 0
    assert float(np.max(abs(aoml[valid]-psl[valid]))) == (2**-19 if decimal_aoml else 0)

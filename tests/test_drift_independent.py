"""Independent P11 analytical, provider-file and upstream framework checks.

Expected paths use closed-form solutions or the complete installed Parcels
runtime, not the application's RK4 helper. Provider checks decode original
packed NetCDF without using production ingestion or CaseStore helpers.
"""
from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from api.case_store import CaseStore
from api.drift_store import DriftStore
from science.contracts import UnsupportedData
from science.drift import VelocityField, cosine_degrees, integrate, release_points, rk4_step, segment_entry, step_distance_km
from science.drift_contracts import DriftQuery

ROOT = Path(__file__).resolve().parents[1]
CASES = ('bay-bengal-2024-01', 'arabian-sea-2024-01')
D = 111120.0


def query(**overrides):
    return DriftQuery.model_validate(dict(
        release=dict(kind='point', longitude=0., latitude=11.),
        duration_hours=1, particle_count=4, dt_seconds=600, **overrides))


def constant_field(u=0., v=0., times=(0., 86400.), lon=(-1., 0., 1.), lat=(10., 11., 12.)):
    shape = (len(times), len(lat), len(lon))
    return VelocityField(lon, lat, times, np.full(shape, u), np.full(shape, v))


def result(field, request, start=0.):
    events = list(integrate(field, request, start))
    assert events[0]['type'] == 'progress'
    assert events[-1]['type'] == 'complete'
    progress = [e['completed_steps'] for e in events if e['type'] == 'progress']
    assert progress == sorted(set(progress))
    return events[-1]


def endpoint(particle):
    p = particle['points'][-1]
    return np.array([p['longitude'], p['latitude']])


@lru_cache(maxsize=4)
def provider_field(case_id, depth_index):
    folder = ROOT / ('data/raw' if case_id == CASES[0] else 'data/raw/arabian-sea')
    journal = folder / 'acquisition.json'
    if not journal.exists():
        pytest.skip('Original provider archives absent; acquire the case to perform this check.')
    import netCDF4
    records = sorted((r for r in json.loads(journal.read_text())['files']
                      if r['archive_kind'] == 'packed_source_subset_reconstructed_as_netcdf'),
                     key=lambda r: r['time'])
    frames_u, frames_v, times = [], [], []
    for record in records:
        path = ROOT / record['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
        with netCDF4.Dataset(path) as source:
            for name, expected_name, output in (
                ('water_u', 'eastward_sea_water_velocity', frames_u),
                ('water_v', 'northward_sea_water_velocity', frames_v),
            ):
                variable = source[name]
                assert variable.standard_name == expected_name
                assert variable.units == 'm/s'
                assert variable.dimensions == ('time', 'depth', 'lat', 'lon')
                variable.set_auto_maskandscale(False)
                packed = np.asarray(variable[0, depth_index])
                decoded = packed.astype(np.float64) * float(variable.scale_factor) + float(variable.add_offset)
                decoded[packed == variable._FillValue] = np.nan
                output.append(decoded)
            lon, lat = np.asarray(source['lon'][:]), np.asarray(source['lat'][:])
            times.append(float(source['time'][0]) * 3600)
    times = np.asarray(times) - times[0]
    return lon, lat, times, np.asarray(frames_u), np.asarray(frames_v)


def scalar_source_sample(inputs, t, x, y):
    """Independent scalar interpolation with direct four-corner weights."""
    lon, lat, times, u, v = inputs
    i = min(bisect_right(lon, x)-1, len(lon)-2)
    j = min(bisect_right(lat, y)-1, len(lat)-2)
    k = min(bisect_right(times, t)-1, len(times)-2)
    fx, fy = (x-lon[i])/(lon[i+1]-lon[i]), (y-lat[j])/(lat[j+1]-lat[j])
    ft = (t-times[k])/(times[k+1]-times[k])
    answer = []
    for a in (u, v):
        values = []
        for q in (k, k+1):
            values.append(float(a[q,j,i])*(1-fx)*(1-fy)
                          +float(a[q,j,i+1])*fx*(1-fy)
                          +float(a[q,j+1,i])*(1-fx)*fy
                          +float(a[q,j+1,i+1])*fx*fy)
        answer.append(values[0]*(1-ft)+values[1]*ft)
    return np.array([answer[0]/(D*math.cos(math.radians(y))), answer[1]/D])


def upstream_endpoint(inputs, starts, duration, dt):
    parcels = pytest.importorskip('parcels', reason='Install pinned Parcels 3.1.4 for the independent full-framework check.')
    assert parcels.__version__ == '3.1.4'
    lon, lat, times, u, v = inputs
    fields = parcels.FieldSet.from_data(
        {'U': u.copy(), 'V': v.copy()},
        {'lon': lon.copy(), 'lat': lat.copy(), 'time': times.copy()},
        mesh='spherical', allow_time_extrapolation=False, cast_data_dtype=np.float64,
    )
    particles = parcels.ParticleSet(fieldset=fields, pclass=parcels.ScipyParticle,
                                   lon=starts[:,0], lat=starts[:,1], time=np.zeros(len(starts)),
                                   lonlatdepth_dtype=np.float64)
    particles.execute(parcels.AdvectionRK4, runtime=duration, dt=dt, verbose_progress=False)
    # Parcels 3.1.4 stores its accepted final point in nextloop; lon/time are
    # the beginning of the last step. A constant-flow test verifies this.
    assert np.array_equal(particles.time_nextloop, np.full(len(starts), duration))
    return np.column_stack((particles.lon_nextloop, particles.lat_nextloop))


def test_polynomial_conversion_matches_independent_libm_over_whole_domain():
    latitudes = np.linspace(-30., 30., 12001)
    expected = np.array([math.cos(math.radians(float(x))) for x in latitudes])
    np.testing.assert_allclose(cosine_degrees(latitudes), expected, rtol=0, atol=2.3e-16)


def test_latitude_domain_guard_and_irregular_coordinate_guard():
    with pytest.raises(ValueError):
        constant_field(lat=(29., 31.))
    with pytest.raises(ValueError):
        constant_field(lon=(0., 1., 1.))
    with pytest.raises(ValueError):
        constant_field(times=(0., 0.))


def test_zero_current_keeps_all_particles_fixed_with_zero_distance():
    out = result(constant_field(), query())
    for p in out['particles']:
        assert p['status'] == 'completed'
        assert p['stop_elapsed_seconds'] == 3600
        assert p['distance_km'] == 0
        assert p['arrival_elapsed_seconds'] is None
        assert all(x['longitude'] == 0 and x['latitude'] == 11 for x in p['points'])
    assert out['summary']['released'] == out['summary']['completed'] == 4
    assert out['summary']['arrival_fraction'] is None


@pytest.mark.parametrize('u,v', [(1.2, 0.), (0., -.4), (1.2, -.4)])
def test_constant_physical_velocity_matches_closed_form_spherical_trajectory(u, v):
    hours = 12
    request = DriftQuery.model_validate(dict(release=dict(kind='point', longitude=0., latitude=11.),
                                            duration_hours=hours, particle_count=1, dt_seconds=600))
    out = result(constant_field(u, v), request)
    end_lat = 11 + v * hours*3600/D
    if v == 0:
        end_lon = u*hours*3600/(D*math.cos(math.radians(11)))
    else:
        phi0, phi1 = math.radians(11), math.radians(end_lat)
        end_lon = (u/v)*(180/math.pi)*math.log((1/math.cos(phi1)+math.tan(phi1))/(1/math.cos(phi0)+math.tan(phi0)))
    np.testing.assert_allclose(endpoint(out['particles'][0]), [end_lon, end_lat], rtol=0, atol=3e-12)
    assert out['particles'][0]['distance_km'] == pytest.approx(math.hypot(u,v)*hours*3.6, abs=2e-8)


def test_linearly_changing_northward_flow_matches_time_integral():
    f = constant_field()
    f.v[0] = -.25
    f.v[1] = .75
    end = result(f, query())['particles'][0]
    expected = 11 + (-.25*3600 + .5*(1/86400)*3600**2)/D
    np.testing.assert_allclose(endpoint(end), [0, expected], rtol=0, atol=2e-13)


class RotatingAngularField:
    """Manufactured angular ODE independent of production interpolation."""
    omega = 2*math.pi/7200

    def sample(self, t, p):
        return self.omega*np.column_stack((-(p[:,1]-11), p[:,0])), np.zeros(len(p), dtype=np.int8)

    def segment_status(self, t0, t1, a, b):
        return np.zeros(len(a), dtype=np.int8)


def test_rk4_rotation_converges_to_analytic_half_circle_with_step_halving():
    expected = np.array([[-.25, 11.]])
    errors = []
    for dt in (600, 300, 150):
        p = np.array([[.25, 11.]])
        for t in range(0, 3600, dt):
            p, status = rk4_step(RotatingAngularField(), t, p, dt)
            assert status.tolist() == [0]
        errors.append(float(np.linalg.norm(p-expected)))
    assert errors[0]/errors[1] > 14
    assert errors[1]/errors[2] > 14
    assert errors[-1] < 2e-6


@pytest.mark.parametrize('case_id', CASES)
@pytest.mark.parametrize('depth_index', [0, 32])
def test_interpolated_currents_match_original_packed_provider_values(case_id, depth_index):
    inputs = provider_field(case_id, depth_index)
    lon, lat, times, _, _ = inputs
    f = VelocityField(*inputs)
    positions = np.array([[lon[20], lat[20]],
                          [float(lon[24]+.37*(lon[25]-lon[24])), float(lat[25]+.23*(lat[26]-lat[25]))]])
    for t in (0., 21600., 43200., 259200.):
        values, statuses = f.sample(t, positions)
        assert statuses.tolist() == [0, 0]
        expected = [scalar_source_sample(inputs, t, *p) for p in positions]
        np.testing.assert_allclose(values, expected, rtol=0, atol=1e-20)


@pytest.mark.parametrize('case_id', CASES)
@pytest.mark.parametrize('depth_index', [0,32])
def test_production_adapter_arrays_coordinates_and_masks_equal_original_provider(case_id, depth_index):
    lon,lat,times,u,v = provider_field(case_id,depth_index)
    field = DriftStore(CaseStore(ROOT/'casepacks')).field(case_id,depth_index)
    for actual,expected in ((field.longitude,lon),(field.latitude,lat),(field.times,times),(field.u,u),(field.v,v)):
        np.testing.assert_array_equal(actual,expected)


@pytest.mark.parametrize('case_id', CASES)
@pytest.mark.parametrize('depth_index', [0, 32])
def test_real_case_trajectories_agree_with_full_upstream_parcels(case_id, depth_index):
    inputs = provider_field(case_id, depth_index)
    lon, lat, _, _, _ = inputs
    starts = np.array([[lon[27], lat[31]], [lon[32], lat[42]], [lon[39], lat[34]]])
    f = VelocityField(*inputs)
    actual = starts.copy()
    for t in range(0, 86400, 600):
        actual, states = rk4_step(f, t, actual, 600)
        assert states.tolist() == [0, 0, 0]
    expected = upstream_endpoint(inputs, starts, 86400, 600)
    # Upstream and app interpolation arithmetic order differs. This is a
    # numerical reference tolerance, not the saved-result replay policy.
    np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-10)


@pytest.mark.parametrize('case_id', CASES)
@pytest.mark.parametrize('depth_index', [0, 32])
def test_real_case_step_refinement_changes_checked_endpoints_by_less_than_two_metres(case_id, depth_index):
    inputs = provider_field(case_id, depth_index)
    lon,lat,_,_,_ = inputs
    starts = np.array([[lon[27],lat[31]],[lon[32],lat[42]],[lon[39],lat[34]]])
    f = VelocityField(*inputs)
    finals = []
    for dt in (1200,600,300,150):
        p = starts.copy()
        for t in range(0,86400,dt):
            p, states = rk4_step(f,t,p,dt)
            assert states.tolist() == [0,0,0]
        finals.append(p)
    errors = []
    for p in finals[:-1]:
        errors.append(max(math.hypot((a[0]-b[0])*math.cos(math.radians((a[1]+b[1])/2)),a[1]-b[1])*D
                          for a,b in zip(p,finals[-1])))
    assert max(errors) < 2.0
    assert errors[2] <= errors[1] + 1e-6


def test_upstream_oracle_reads_actual_final_time_and_constant_displacement():
    f = constant_field(1, 0)
    positions = np.array([[0., 11.]])
    p = upstream_endpoint((f.longitude, f.latitude, f.times, f.u, f.v), positions, 3600, 600)
    np.testing.assert_allclose(p, [[3600/(D*math.cos(math.radians(11))),11]], rtol=0, atol=2e-14)


def test_full_missing_spatial_stencil_is_required_even_at_exact_wet_node():
    f = constant_field(1, 0)
    f = VelocityField(f.longitude, f.latitude, f.times,
                      np.where(np.indices(f.u.shape)[2] == 2, np.nan, f.u), f.v)
    velocity, status = f.sample(0, np.array([[0., 11.], [-.25, 10.5]]))
    assert status.tolist() == [2, 0]
    assert velocity[0].tolist() == [0., 0.]
    assert np.isfinite(velocity).all()


def test_exact_time_does_not_require_next_frame_but_inbetween_does():
    f = constant_field()
    u = f.u.copy(); u[1] = np.nan
    f = VelocityField(f.longitude, f.latitude, f.times, u, f.v)
    _, at_source = f.sample(0, np.array([[-.25,10.5]]))
    _, between = f.sample(1, np.array([[-.25,10.5]]))
    assert at_source.tolist() == [0]
    assert between.tolist() == [2]


def test_traversed_masked_strip_cannot_be_skipped_by_valid_stage_points():
    f = constant_field(50, 0, lon=(-1., -.5, -.4, -.3, 0., .5, 1.))
    u = f.u.copy(); u[:,:,2] = np.nan
    f = VelocityField(f.longitude, f.latitude, f.times, u, f.v)
    a, b = np.array([[-.9,10.5]]), np.array([[.9,10.5]])
    assert f.sample(0,a)[1].tolist() == f.sample(3600,b)[1].tolist() == [0]
    assert f.segment_status(0,3600,a,b).tolist() == [2]


def test_real_arabian_subsurface_mask_is_retained():
    inputs = provider_field(CASES[1],32)
    f = VelocityField(*inputs)
    wet = np.isfinite(inputs[3][0]) & np.isfinite(inputs[4][0])
    assert np.count_nonzero(wet) == 4513
    j,i = np.argwhere(~wet)[0]
    _, status = f.sample(0,np.array([[f.longitude[i],f.latitude[j]]]))
    assert status.tolist() == [2]


def test_outside_domain_stops_at_last_accepted_position_without_clipping():
    f = constant_field(1,0)
    request = DriftQuery.model_validate(dict(release=dict(kind='point',longitude=.995,latitude=11),
                                            duration_hours=1,particle_count=1,dt_seconds=600))
    out = result(f,request)
    p = out['particles'][0]
    assert p['status'] == 'left_domain'
    assert p['stop_elapsed_seconds'] == 0
    assert p['distance_km'] == 0
    assert len(p['points']) == 1
    assert p['points'][0]['longitude'] == .995


@pytest.mark.parametrize('time', [-1.,86401.])
def test_forcing_cannot_extrapolate(time):
    with pytest.raises(UnsupportedData) as exc:
        constant_field().sample(time,np.array([[0.,11.]]))
    assert exc.value.code == 'forcing_exhausted'


def test_excess_duration_fails_instead_of_silently_truncating():
    request = DriftQuery.model_validate(dict(release=dict(kind='point',longitude=0,latitude=11),duration_hours=25))
    with pytest.raises(UnsupportedData) as exc:
        list(integrate(constant_field(),request,0))
    assert exc.value.code == 'forcing_exhausted'


@pytest.mark.parametrize('start,end,box,fraction', [
    ((0,0),(10,0),(3,-1,3.5,1),.3),
    ((10,0),(0,0),(3,-1,3.5,1),.65),
    ((0,0),(10,10),(3,3,4,4),.3),
    ((3,3),(3,3),(3,3,4,4),0),
    ((0,0),(10,0),(3,1,4,2),None),
])
def test_target_segment_first_intersection_known_geometry(start,end,box,fraction):
    actual = segment_entry(start,end,box)
    if fraction is None:
        assert actual is None
    else:
        assert actual == pytest.approx(fraction,abs=1e-15)


def test_narrow_target_arrival_is_detected_between_step_endpoints():
    speed = D*math.cos(math.radians(11))*.01/600
    request = query(target_bounds=(.004,10.99,.006,11.01))
    out = result(constant_field(speed,0),request)
    assert out['summary']['arrived'] == out['summary']['released'] == 4
    assert out['summary']['arrival_fraction'] == 1
    assert out['summary']['earliest_arrival_seconds'] == pytest.approx(240,abs=1e-10)


def test_arrivals_use_all_releases_and_distances_only_valid_releases():
    f = constant_field()
    u = f.u.copy();u[:,:,2] = np.nan
    f = VelocityField(f.longitude,f.latitude,f.times,u,f.v)
    request = DriftQuery.model_validate(dict(release=dict(kind='box',bounds=(-.9,10.1,.9,10.9)),
                                            duration_hours=1,particle_count=64,seed=26067,target_bounds=(-1,10,1,12)))
    out = result(f,request)
    valid = [p for p in out['particles'] if p['release_longitude'] < 0]
    invalid = [p for p in out['particles'] if p['release_longitude'] >= 0]
    assert valid and invalid
    assert len(valid) == out['summary']['arrived'] == out['summary']['valid_releases']
    assert out['summary']['invalid_release'] == len(invalid)
    assert out['summary']['arrival_fraction'] == len(valid)/64
    assert out['summary']['earliest_arrival_seconds'] == out['summary']['latest_arrival_seconds'] == 0
    assert out['summary']['mean_distance_km'] == 0
    assert all(p['arrival_elapsed_seconds'] is None for p in invalid)


def test_identical_point_releases_coincide_and_seed_only_changes_box_release():
    a = result(constant_field(.5,.1),query())
    b = result(constant_field(.5,.1),query(seed=45))
    assert [p['points'] for p in a['particles']] == [p['points'] for p in b['particles']]
    assert all(p['points'] == a['particles'][0]['points'] for p in a['particles'])
    q = DriftQuery.model_validate(dict(release=dict(kind='box',bounds=(-.5,10.5,.5,11.5))))
    assert np.array_equal(release_points(q),release_points(q))
    assert not np.array_equal(release_points(q),release_points(q.model_copy(update={'seed':12})))
    assert ((release_points(q) > [-.5,10.5]) & (release_points(q) < [.5,11.5])).all()


@pytest.mark.parametrize('dt,interval', [(300,1800),(600,1800),(1200,3600)])
def test_output_cadence_matches_integration_step_and_keeps_exact_final_point(dt,interval):
    request = DriftQuery.model_validate(dict(release=dict(kind='point',longitude=0,latitude=11),duration_hours=3,dt_seconds=dt))
    p = result(constant_field(.1,0),request)['particles'][0]
    assert [x['elapsed_seconds'] for x in p['points']] == list(range(0,10800+1,interval))
    assert endpoint(p)[0] == pytest.approx(.1*10800/(D*math.cos(math.radians(11))),abs=2e-14)


def test_midpoint_metric_distance_has_known_north_and_east_lengths():
    a = np.array([[0.,11.],[0.,11.]])
    b = np.array([[0.,12.],[1.,11.]])
    np.testing.assert_allclose(step_distance_km(a,b),[111.12,111.12*math.cos(math.radians(11))],rtol=0,atol=2e-14)

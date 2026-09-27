"""P05 scientific acceptance against independent original-source references.

The JSON fixture is generated separately from original packed HYCOM and Argo
NetCDF files. No expectation is obtained by calling the production matcher.
Small synthetic profiles below are labelled test inputs, not deployed data.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from api.app import create_app
from api.case_store import CASE_ID, CaseStore
from api.evidence_store import EvidenceStore
from api.instrument_store import InstrumentStore
from api.version import APP_VERSION
from science.evidence import compare
from science.evidence_contracts import MatchSettings


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads((ROOT / "tests/fixtures/p05-source-reference.json").read_text(encoding="utf-8"))
VARIABLES = ("temperature", "salinity")
SNAPSHOTS = (0, 1, 3, 5)


@pytest.fixture(scope="module")
def stores():
    cases = CaseStore(ROOT / "casepacks")
    instruments = InstrumentStore(ROOT / "casepacks/instruments")
    return cases, instruments, EvidenceStore(cases, instruments)


@pytest.fixture(scope="module")
def profiles(stores):
    return {p["platform"]: stores[1].read(p["profile_id"]) for p in REFERENCE["profiles"]}


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(), raise_server_exceptions=False) as value:
        yield value


def assert_accounting(result):
    accepted = [row for row in result.rows if row.accepted]
    rejected = [row for row in result.rows if not row.accepted]
    assert len(accepted) == result.matched_count == result.metrics.count
    assert len(rejected) == result.excluded_count
    assert len(result.rows) == result.total_samples == result.matched_count + result.excluded_count
    assert dict(Counter(row.reason for row in rejected)) == result.exclusion_counts
    assert all(row.reason == "accepted" and row.model is not None and row.residual is not None for row in accepted)
    assert all(row.reason != "accepted" and row.model is None and row.residual is None for row in rejected)
    if not accepted:
        assert result.metrics.bias is None
        assert result.metrics.rmse is None
        assert result.metrics.mae is None
        assert result.metrics.maximum_abs_residual is None


@pytest.mark.parametrize("time_index", SNAPSHOTS)
@pytest.mark.parametrize("variable", VARIABLES)
def test_real_samples_match_independent_native_source_values(stores, profiles, time_index, variable):
    """The full original source row order, wet brackets and residual sign agree."""
    cases, _, evidence = stores
    assert cases.require(CASE_ID)[1] == REFERENCE["model_manifest_sha256"]
    settings = MatchSettings(variable=variable, time_index=time_index, time_window_hours=72)
    for reference in REFERENCE["profiles"]:
        result = evidence.comparison(CASE_ID, reference["profile_id"], settings)
        assert_accounting(result)
        assert result.manifest_sha256 == REFERENCE["model_manifest_sha256"]
        assert result.profile.source_sha256 == reference["source_sha256"]
        assert [row.sample_index for row in result.rows] == [o["index"] for o in reference["observations"]]
        snapshot = reference["snapshots"][str(time_index)]
        column = snapshot["columns"][variable]
        assert result.model_time == snapshot["time"]
        for row, observed in zip(result.rows, reference["observations"]):
            index = observed["index"]
            assert row.observation_time == reference["time"]
            assert row.time_offset_hours == pytest.approx(snapshot["signed_observation_minus_model_seconds"] / 3600, abs=1e-12)
            if reference["source_review_required"]:
                assert row.reason == "source_review"
                continue
            if observed["pressure_qc"] == "4":
                assert row.reason == "coordinate_qc"
                assert not row.accepted
                continue
            assert row.accepted
            assert row.observed == observed["readings"][variable]["selected_adjusted"]
            assert row.depth_m == pytest.approx(observed["depth_m"], abs=1e-9)
            assert row.model_latitude == reference["nearest_column"]["latitude"]
            assert row.model_longitude == reference["nearest_column"]["longitude"]
            assert row.distance_km == pytest.approx(reference["nearest_column"]["distance_km"], abs=1e-10)
            bracket = observed["bracket"]
            assert row.lower_depth_m == REFERENCE["model_depth_m"][bracket["lower_index"]]
            assert row.upper_depth_m == REFERENCE["model_depth_m"][bracket["upper_index"]]
            assert row.upper_weight == pytest.approx(bracket["weight"], abs=1e-12)
            assert row.model_lower_value == column["native_decoded"][bracket["lower_index"]]
            assert row.model_upper_value == column["native_decoded"][bracket["upper_index"]]
            assert row.model == pytest.approx(column["model_at_observation_depth"][index], abs=1e-10)
            assert row.residual == pytest.approx(column["model_minus_observation"][index], abs=1e-10)


@pytest.mark.parametrize("time_index", SNAPSHOTS)
@pytest.mark.parametrize("variable", VARIABLES)
def test_all_independent_count_scenarios(stores, profiles, time_index, variable):
    """576 independently specified settings, both T/S and all seven profiles."""
    cases, _, evidence = stores
    manifest, digest = cases.require(CASE_ID)
    values = cases._read_array(CASE_ID, "analytical", variable, time_index)
    for scenario in REFERENCE["count_scenarios"]:
        if scenario["time_index"] != time_index:
            continue
        settings = MatchSettings(variable=variable, time_index=time_index,
                                 time_window_hours=scenario["max_time_hours"], distance_km=scenario["max_distance_km"],
                                 max_vertical_gap_m=scenario["max_vertical_gap_m"],
                                 qc="good" if scenario["qc"] == ["1"] else "good_probably_good")
        for offset, platform in enumerate(REFERENCE["profile_order"]):
            result = compare(manifest, digest, evidence.library_sha, profiles[platform], settings, values)
            assert result.matched_count == scenario["review_gated_counts"][variable][offset], (platform, variable, scenario)
            assert_accounting(result)


@pytest.mark.parametrize("platform,variable,bias,rmse,mae", [
    ("1902669", "temperature", -0.07305982885669086, 0.2506753614233362, 0.15574846578038845),
    ("1902669", "salinity", 0.12162861745242372, 0.33570275712883413, 0.14206089874251032),
    ("4903775", "temperature", 0.22138630145783464, 0.6969605907674252, 0.4611977603130188),
    ("4903775", "salinity", 0.21485385793966882, 0.6850501231406266, 0.2675051446701747),
])
def test_selected_sample_statistics_have_independent_reference_values(stores, profiles, platform, variable, bias, rmse, mae):
    result = stores[2].comparison(CASE_ID, profiles[platform].id, MatchSettings(variable=variable))
    assert result.metrics.count == 103
    assert result.metrics.bias == pytest.approx(bias, abs=1e-11)
    assert result.metrics.rmse == pytest.approx(rmse, abs=1e-11)
    assert result.metrics.mae == pytest.approx(mae, abs=1e-11)
    assert any("not independent validation" in note for note in result.caveats)
    assert any("not weighted by depth" in note for note in result.caveats)


def synthetic_profile(profiles, depth=5.0):
    profile = profiles["1902669"].model_copy(deep=True)
    profile.id = "synthetic-test-only"
    profile.title = "Synthetic scientific test input, never deployed"
    profile.source_sha256 = "0" * 64
    profile.levels = [profile.levels[0].model_copy(deep=True)]
    profile.levels[0].depth_m = depth
    profile.levels[0].readings["temperature"].value = 12.0
    profile.samples = 1
    return profile


def run_synthetic(stores, profile, settings=None, values=None, manifest=None):
    cases, _, evidence = stores
    original, digest = cases.require(CASE_ID)
    selected = settings or MatchSettings()
    array = values if values is not None else cases._read_array(CASE_ID, "analytical", selected.variable, selected.time_index)
    result = compare(manifest or original, digest, evidence.library_sha, profile, selected, array)
    assert_accounting(result)
    return result


@pytest.mark.parametrize("probe", REFERENCE["synthetic_edge_probes"]["probes"], ids=lambda p: f"depth_{p['depth_m']}m")
def test_native_depth_boundaries_and_bathymetry_masks(stores, profiles, probe):
    p = synthetic_profile(profiles, depth=probe["depth_m"])
    result = run_synthetic(stores, p, MatchSettings(max_vertical_gap_m=1000))
    row = result.rows[0]
    expected = probe["model"]["temperature"]
    assert row.accepted is (expected is not None)
    if expected is not None:
        assert row.model == pytest.approx(expected, abs=1e-11)
        assert row.residual == pytest.approx(expected - 12, abs=1e-11)
    elif probe["depth_m"] < 0:
        assert row.reason == "invalid_depth"
    elif probe["depth_m"] > 5000:
        assert row.reason == "depth_outside"
    else:
        assert row.reason == "masked_bracket"


def test_vertical_gap_threshold_is_inclusive_and_changes_only_eligible_pairs(stores, profiles):
    profile = synthetic_profile(profiles, depth=1750)
    passes = run_synthetic(stores, profile, MatchSettings(max_vertical_gap_m=500))
    fails = run_synthetic(stores, profile, MatchSettings(max_vertical_gap_m=499))
    assert passes.rows[0].upper_weight == 0.5
    assert passes.rows[0].model == pytest.approx(3.5984992209705524, abs=1e-12)
    assert fails.rows[0].reason == "vertical_gap" and fails.matched_count == 0


def test_exact_node_needs_one_value_but_interpolation_never_bridges_a_mask(stores, profiles):
    manifest = stores[0].require(CASE_ID)[0].model_copy(deep=True)
    manifest.coordinates.latitude = [0]
    manifest.coordinates.longitude = [0]
    manifest.coordinates.depth_m = [0, 10, 20]
    profile = synthetic_profile(profiles, depth=0)
    profile.levels[0].latitude = profile.levels[0].longitude = 0
    values = [10.0, math.nan, 30.0]
    exact = run_synthetic(stores, profile, values=values, manifest=manifest)
    assert exact.rows[0].accepted and exact.rows[0].model == 10
    assert exact.rows[0].lower_depth_m == exact.rows[0].upper_depth_m == 0
    for depth in (5, 10, 15):
        profile.levels[0].depth_m = depth
        result = run_synthetic(stores, profile, values=values, manifest=manifest)
        assert result.rows[0].reason == "masked_bracket"


def test_nearest_column_tie_is_deterministic_and_masked_column_is_not_replaced(stores, profiles):
    manifest = stores[0].require(CASE_ID)[0].model_copy(deep=True)
    manifest.coordinates.latitude = [0]
    manifest.coordinates.longitude = [-0.1, 0.1]
    manifest.coordinates.depth_m = [0, 10]
    profile = synthetic_profile(profiles)
    profile.levels[0].latitude = profile.levels[0].longitude = 0
    settings = MatchSettings(distance_km=50)
    tied = run_synthetic(stores, profile, settings, values=[10, 30, 20, 40], manifest=manifest)
    assert tied.rows[0].model_longitude == -0.1
    assert tied.rows[0].model == 15
    masked = run_synthetic(stores, profile, settings, values=[math.nan, 30, 20, 40], manifest=manifest)
    assert masked.rows[0].reason == "masked_bracket"
    assert masked.rows[0].model_longitude == -0.1


def test_duplicate_depths_and_source_order_are_not_sorted_or_deduplicated(stores, profiles):
    p = synthetic_profile(profiles, depth=1000)
    p.levels = [deepcopy(p.levels[0]) for _ in range(3)]
    for row, index, depth, value in zip(p.levels, (42, 7, 123), (1000, 0, 1000), (6, 28, 7)):
        row.index, row.depth_m, row.readings["temperature"].value = index, depth, value
    p.samples = 3
    result = run_synthetic(stores, p)
    assert [r.sample_index for r in result.rows] == [42, 7, 123]
    assert [r.depth_m for r in result.rows] == [1000, 0, 1000]
    assert result.rows[0].model == result.rows[2].model
    assert result.rows[0].residual - result.rows[2].residual == 1
    assert result.metrics.count == 3


def test_per_sample_locations_and_times_control_moving_profile_matches(stores, profiles):
    p = synthetic_profile(profiles, depth=0)
    p.levels = [deepcopy(p.levels[0]) for _ in range(3)]
    target = next(ref for ref in REFERENCE["profiles"] if ref["platform"] == "4903775")
    p.levels[1].latitude, p.levels[1].longitude = target["latitude"], target["longitude"]
    p.levels[2].time = "2024-01-08T12:00:00Z"
    for index, row in enumerate(p.levels):
        row.index = index
    p.samples = 3
    result = run_synthetic(stores, p)
    assert result.matched_count == 2
    assert result.rows[0].model == pytest.approx(27.999000379932113, abs=1e-11)
    assert result.rows[1].model == target["snapshots"]["1"]["columns"]["temperature"]["native_decoded"][0]
    assert result.rows[0].model_longitude != result.rows[1].model_longitude
    assert result.rows[2].reason == "time_window"


@pytest.mark.parametrize("gate", ["reading", "pressure", "position", "time"])
def test_good_only_narrows_parameter_and_coordinate_qc(stores, profiles, gate):
    p = synthetic_profile(profiles)
    if gate == "reading":
        p.levels[0].readings["temperature"].qc = "2"
    else:
        p.levels[0].coordinate_qc[gate] = "2"
    original = p.model_dump_json()
    broad = run_synthetic(stores, p, MatchSettings(qc="good_probably_good"))
    narrow = run_synthetic(stores, p, MatchSettings(qc="good"))
    assert broad.matched_count == 1
    assert narrow.matched_count == 0
    assert narrow.rows[0].reason == ("observation_qc" if gate == "reading" else "coordinate_qc")
    assert p.model_dump_json() == original


@pytest.mark.parametrize("scheme,flag,accepted", [("argo", "4", False), ("qartod", "2", False), ("woce", "2", True)])
def test_source_quality_meanings_are_not_promoted_or_renumbered(stores, profiles, scheme, flag, accepted):
    p = synthetic_profile(profiles)
    p.parameters["temperature"].qc_scheme = scheme
    p.levels[0].readings["temperature"].qc = flag
    p.levels[0].readings["temperature"].accepted = accepted
    p.levels[0].coordinate_qc = {"scheme": scheme, "pressure": flag, "position": "", "time": ""}
    for policy in ("good", "good_probably_good"):
        result = run_synthetic(stores, p, MatchSettings(qc=policy))
        assert result.rows[0].accepted is accepted


def test_source_review_hold_is_separate_from_provider_qc_and_cannot_be_renamed_away(stores, profiles):
    p = profiles["5907083"].model_copy(deep=True)
    before = p.model_dump_json()
    assert all(level.readings["salinity"].qc == "1" for level in p.levels)
    result = run_synthetic(stores, p, MatchSettings(variable="salinity", time_window_hours=72, distance_km=50, max_vertical_gap_m=1000))
    assert result.matched_count == 0
    assert result.exclusion_counts == {"source_review": 102}
    assert p.model_dump_json() == before
    p.id = "renamed-profile"
    p.platform = "different-visible-name"
    assert run_synthetic(stores, p).exclusion_counts == {"source_review": 102}


@pytest.mark.parametrize("change,reason", [
    ("outside_west", "outside_domain"), ("outside_north", "outside_domain"),
    ("outside_time", "time_window"), ("distance", "distance"),
    ("missing", "missing_value"), ("bad_coordinate", "coordinate_qc"),
    ("bad_reading", "observation_qc"), ("no_depth", "invalid_depth"),
    ("no_parameter", "variable_unavailable"), ("no_reading", "variable_unavailable"),
])
def test_deliberate_mismatches_have_truthful_empty_results(stores, profiles, change, reason):
    p = synthetic_profile(profiles)
    settings = MatchSettings()
    if change == "outside_west": p.levels[0].longitude = 85
    if change == "outside_north": p.levels[0].latitude = 15.01
    if change == "outside_time": p.levels[0].time = "2026-09-22T00:00:00Z"
    if change == "distance": settings = MatchSettings(distance_km=0)
    if change == "missing": p.levels[0].readings["temperature"].value = None
    if change == "bad_coordinate": p.levels[0].coordinate_eligible = False
    if change == "bad_reading": p.levels[0].readings["temperature"].accepted = False
    if change == "no_depth": p.levels[0].depth_m = None
    if change == "no_parameter": del p.parameters["temperature"]
    if change == "no_reading": del p.levels[0].readings["temperature"]
    result = run_synthetic(stores, p, settings)
    assert result.exclusion_counts == {reason: 1}


def test_exact_spatial_temporal_zero_windows_and_six_hour_boundary(stores, profiles):
    p = synthetic_profile(profiles, depth=0)
    cell = REFERENCE["profiles"][0]["nearest_column"]
    p.levels[0].latitude, p.levels[0].longitude = cell["latitude"], cell["longitude"]
    p.levels[0].time = "2024-01-07T12:00:00Z"
    result = run_synthetic(stores, p, MatchSettings(distance_km=0, time_window_hours=0))
    assert result.matched_count == 1
    assert result.rows[0].distance_km == result.rows[0].time_offset_hours == 0
    p.levels[0].time = "2024-01-07T18:00:00Z"
    assert run_synthetic(stores, p).matched_count == 1
    p.levels[0].time = "2024-01-07T18:00:01Z"
    assert run_synthetic(stores, p).exclusion_counts == {"time_window": 1}


@pytest.mark.parametrize("variable,side,field,value", [
    ("temperature", "observation", "definition", "Potential temperature referenced to 0 dbar"),
    ("temperature", "observation", "units", "K"),
    ("temperature", "model", "standard_name", "sea_water_conservative_temperature"),
    ("temperature", "model", "units", "K"),
    ("salinity", "observation", "definition", "Absolute salinity"),
    ("salinity", "observation", "units", "g/kg"),
    ("salinity", "model", "standard_name", "sea_water_absolute_salinity"),
    ("salinity", "model", "units", "g/kg"),
])
def test_incompatible_quantities_are_rejected_even_when_values_look_plausible(stores, profiles, variable, side, field, value):
    p = synthetic_profile(profiles)
    manifest = stores[0].require(CASE_ID)[0].model_copy(deep=True)
    target = p.parameters[variable] if side == "observation" else next(v for v in manifest.variables if v.id == variable)
    setattr(target, field, value)
    result = run_synthetic(stores, p, MatchSettings(variable=variable), manifest=manifest)
    assert result.exclusion_counts == {"incompatible_variable": 1}


def test_unknown_ship_temperature_scale_cannot_pass_through_geographic_overlap(stores, profiles):
    p = synthetic_profile(profiles)
    p.instrument = "ctd"
    p.metadata = {}
    assert run_synthetic(stores, p).exclusion_counts == {"incompatible_variable": 1}
    p.metadata["temperature_scale"] = "IPTS-68"
    assert run_synthetic(stores, p).exclusion_counts == {"incompatible_variable": 1}
    p.metadata["temperature_scale"] = "ITS-90"
    assert run_synthetic(stores, p).matched_count == 1
    # The temperature metadata restriction must not reject compatible salinity.
    p.metadata = {}
    assert run_synthetic(stores, p, MatchSettings(variable="salinity")).matched_count == 1


def test_moving_profile_coverage_ranges_only_describe_accepted_samples(stores, profiles):
    p = synthetic_profile(profiles, depth=0)
    p.instrument = "glider"
    p.levels = [deepcopy(p.levels[0]) for _ in range(4)]
    refs = {r["platform"]: r for r in REFERENCE["profiles"]}
    for i, platform in enumerate(("1902669", "4903775", "7901126", "1902669")):
        p.levels[i].index = i
        p.levels[i].latitude = refs[platform]["latitude"]
        p.levels[i].longitude = refs[platform]["longitude"]
        p.levels[i].depth_m = i * 100
    for level, time in zip(p.levels, ("2024-01-07T12:30:00Z", "2024-01-07T13:00:00Z", "2024-01-07T12:00:00Z", "2024-01-09T12:00:00Z")):
        level.time = time
    p.samples = 4

    class SyntheticLibrary:
        def index(self, case_id=CASE_ID):
            return {"profiles": [p.model_dump()]}

        def catalog(self, case_id=CASE_ID):
            return self.index()

        def read(self, identifier):
            assert identifier == p.id
            return p

    evidence = EvidenceStore(stores[0], SyntheticLibrary())
    result = evidence.coverage(CASE_ID, MatchSettings(distance_km=2))
    entry = result.profiles[0]
    assert entry.matched_count == 2
    assert entry.eligible_depths_m == [0, 100]
    assert entry.exclusion_counts == {"distance": 1, "time_window": 1}
    assert entry.time_offset_hours_min == 0.5
    assert entry.time_offset_hours_max == 1
    assert entry.distance_km_min == pytest.approx(refs["4903775"]["nearest_column"]["distance_km"], abs=1e-10)
    assert entry.distance_km_max == pytest.approx(refs["1902669"]["nearest_column"]["distance_km"], abs=1e-10)
    empty = evidence.coverage(CASE_ID, MatchSettings(distance_km=0)).profiles[0]
    assert empty.matched_count == 0 and empty.eligible_depths_m == []
    assert empty.distance_km_min is empty.distance_km_max is None
    # Empty entries retain source offsets only as an exclusion diagnostic.
    assert empty.time_offset_hours_min == 0 and empty.time_offset_hours_max == 48


def test_coverage_reuses_comparison_gates_and_preserves_real_depth_order(stores):
    evidence = stores[2]
    result = evidence.coverage(CASE_ID, MatchSettings())
    assert result.total_profiles == 13
    assert result.total_samples == 5318
    assert result.matched_profiles == 2 and result.matched_samples == 206
    assert result.total_samples == result.matched_samples + result.excluded_samples
    assert sum(result.exclusion_counts.values()) == result.excluded_samples
    totals = Counter()
    for entry in result.profiles:
        comparison = evidence.comparison(CASE_ID, entry.profile.id, MatchSettings())
        assert entry.matched_count == comparison.matched_count == len(entry.eligible_depths_m)
        assert entry.eligible_depths_m == [r.depth_m for r in comparison.rows if r.accepted]
        assert entry.metrics == comparison.metrics
        assert entry.exclusion_counts == comparison.exclusion_counts
        totals.update(entry.exclusion_counts)
        if entry.suggested_time_index is not None:
            suggested = evidence.comparison(CASE_ID, entry.profile.id, MatchSettings(time_index=entry.suggested_time_index))
            assert suggested.matched_count == entry.suggested_matched_count > 0
            assert entry.matched_count == 0  # suggestions are not applied silently
    assert dict(totals) == result.exclusion_counts
    held = next(entry for entry in result.profiles if entry.profile.platform == "5907083")
    assert held.suggested_time_index is None


def test_coverage_empty_windows_and_empty_library_have_no_fabricated_scores(stores, tmp_path):
    result = stores[2].coverage(CASE_ID, MatchSettings(time_window_hours=0))
    assert result.matched_profiles == result.matched_samples == 0
    assert all(not p.eligible_depths_m and p.metrics.rmse is None and p.suggested_time_index is None for p in result.profiles)
    empty = EvidenceStore(stores[0], InstrumentStore(tmp_path)).coverage(CASE_ID, MatchSettings())
    assert empty.total_profiles == empty.total_samples == empty.matched_samples == empty.excluded_samples == 0
    assert empty.profiles == [] and empty.exclusion_counts == {}


def test_source_bundles_are_not_mutated_by_comparison(stores):
    paths = [ROOT / "casepacks" / CASE_ID / "manifest.json", ROOT / "casepacks/instruments/index.json"]
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    stores[2].coverage(CASE_ID, MatchSettings(variable="salinity", time_index=5, time_window_hours=72, distance_km=10))
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == before


def test_api_profile_coverage_and_all_settings_are_consistent(client):
    reference = REFERENCE["profiles"][0]
    base = f"/api/cases/{CASE_ID}/evidence"
    params = {"variable": "salinity", "time_index": 1, "time_window_hours": 3,
              "distance_km": 2, "max_vertical_gap_m": 100, "qc": "good"}
    response = client.get(f"{base}/profiles/{reference['profile_id']}", params=params)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-ocean-app-version"] == APP_VERSION
    body = response.json()
    assert body["settings"] == params
    assert body["matched_count"] == body["metrics"]["count"] == 62
    assert body["manifest_sha256"] == REFERENCE["model_manifest_sha256"]
    assert body["rows"][0]["residual"] == pytest.approx(0.9349999214755371, abs=1e-10)
    coverage_response = client.get(f"{base}/coverage", params=params)
    assert coverage_response.status_code == 200
    coverage = coverage_response.json()
    assert coverage["settings"] == params
    assert coverage["matched_samples"] == 124
    entry = next(p for p in coverage["profiles"] if p["profile"]["id"] == reference["profile_id"])
    assert entry["matched_count"] == body["matched_count"]
    assert entry["metrics"] == body["metrics"]
    assert entry["eligible_depths_m"] == [r["depth_m"] for r in body["rows"] if r["accepted"]]
    # Returning to the earlier settings must not reuse a narrowed/other-variable response.
    original = client.get(f"{base}/profiles/{reference['profile_id']}").json()
    assert original["settings"]["variable"] == "temperature"
    assert original["matched_count"] == 103


@pytest.mark.parametrize("parameter,value", [
    ("variable", "oxygen"), ("time_index", -1), ("time_index", 7),
    ("time_window_hours", -1), ("time_window_hours", 73), ("time_window_hours", "nan"),
    ("distance_km", -1), ("distance_km", 51), ("distance_km", "inf"),
    ("max_vertical_gap_m", 0), ("max_vertical_gap_m", 1001), ("qc", "accept_everything"),
])
def test_api_rejects_unsupported_and_nonfinite_settings(client, parameter, value):
    response = client.get(f"/api/cases/{CASE_ID}/evidence/coverage", params={parameter: value})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


@pytest.mark.parametrize("path,code", [
    ("/api/cases/unavailable/evidence/coverage", "case_not_found"),
    (f"/api/cases/{CASE_ID}/evidence/profiles/not-in-library", "profile_not_found"),
    (f"/api/cases/{CASE_ID}/evidence/profiles/imported-local-profile", "profile_not_found"),
])
def test_api_uses_catalogue_ids_and_never_fabricates_a_missing_comparison(client, path, code):
    response = client.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == code

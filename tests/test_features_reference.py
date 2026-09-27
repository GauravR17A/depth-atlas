"""P07 runtime checks against a separate original-source and Decimal oracle."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import pytest

from api.case_store import CASE_ID, CaseStore
from api.evidence_store import EvidenceStore
from api.feature_store import FeatureStore
from api.instrument_store import InstrumentStore
from science.contracts import Coordinates
from science.feature_contracts import FeatureQuery, SectionQuery
from science.features import analyze, boundary_faces


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_BODY = (ROOT / "tests/fixtures/p07-source-reference.json").read_bytes()
REFERENCE = json.loads(FIXTURE_BODY)
EXPECTED_SHA = "1e45922b54acffd4f707478e650a8dc7537a39f50d4dc549234455c0f808a0b0"


@pytest.fixture(scope="module")
def stores():
    cases = CaseStore(ROOT / "casepacks")
    instruments = InstrumentStore(ROOT / "casepacks/instruments")
    evidence = EvidenceStore(cases, instruments)
    return cases, FeatureStore(cases, instruments, evidence)


def query_from_reference(reference, cases=None):
    raw = reference["query"]
    variable = raw.get("variable", "temperature")
    units = "\u00b0C"
    if cases is not None:
        if variable == "horizontal_kinetic_energy":
            units = "m\u00b2/s\u00b2"
        else:
            units = next(v.units for v in cases.require(CASE_ID)[0].variables if v.id == variable)
    low, high = raw.get("lower"), raw.get("upper")
    return FeatureQuery(variable=variable, units=units, time_index=raw.get("time_index", 1),
                        operator="between" if low is not None and high is not None else "at_most" if low is None else "at_least",
                        threshold=high if low is None else low,
                        upper_threshold=high if low is not None and high is not None else None,
                        depth_min_m=raw["depth_min_m"], depth_max_m=raw["depth_max_m"])


def expected_bounds(bounds):
    return {"west": bounds["longitude"][0], "east": bounds["longitude"][1],
            "south": bounds["latitude"][0], "north": bounds["latitude"][1],
            "depth_min_m": bounds["depth_m"][0], "depth_max_m": bounds["depth_m"][1]}


def check_analysis(result, expected):
    assert result["qualified_cells"] == expected["qualifying_count"]
    assert len(result["regions"]) == expected["region_count"]
    assert math.fsum(r["estimated_volume_km3"] for r in result["regions"]) == pytest.approx(expected["estimated_volume_m3"] / 1e9, rel=2e-12, abs=1e-10)
    indices = np.flatnonzero(result["labels"].ravel() >= 0).astype("<i8")
    assert hashlib.sha256(indices.tobytes()).hexdigest() == expected["membership_sha256"]
    by_id = {r["id"]: r for r in result["regions"]}
    for item in expected["components"]:
        region = by_id[item["id"]]
        assert region["cell_count"] == item["cell_count"]
        assert region["membership_sha256"] == item["membership_sha256"]
        assert region["estimated_volume_km3"] == pytest.approx(item["estimated_volume_m3"] / 1e9, rel=2e-12, abs=1e-10)
        assert region["min"] == item["minimum"]
        assert region["max"] == item["maximum"]
        assert region["mean"] == pytest.approx(item["sample_mean"], rel=1e-12, abs=1e-12)
        assert region["volume_weighted_mean"] == pytest.approx(item["volume_weighted_mean"], rel=1e-12, abs=1e-12)
        assert region["center_bounds"] == expected_bounds(item["center_extent"])
        assert region["cell_bounds"] == expected_bounds(item["cell_extent"])
        if "members" in item:
            assert result["members"][item["seed_flat_index"]].tolist() == item["members"]
    assert [r["id"] for r in sorted(result["regions"], key=lambda r: (-r["estimated_volume_km3"], int(r["id"][1:])))] == expected["volume_order"]


def test_fixture_identity():
    assert hashlib.sha256(FIXTURE_BODY).hexdigest() == EXPECTED_SHA
    assert "int64" in REFERENCE["method"]["membership_sha256"]


@pytest.mark.parametrize("expected", REFERENCE["synthetic_cases"], ids=lambda case: case["name"])
def test_synthetic_geometry_membership_and_statistics(expected):
    values = np.array([np.nan if v is None else v for v in expected["values"]], dtype=float).reshape(expected["shape"])
    result = analyze(values, expected["axes"], query_from_reference(expected))
    check_analysis(result, expected)


@pytest.mark.parametrize("expected", REFERENCE["source_queries"], ids=lambda case: case.get("name") or f"{case['query']['variable']}-{case['query']['time_index']}")
def test_direct_packed_source_queries_and_observation_associations(stores, expected):
    cases, features = stores
    query = query_from_reference(expected, cases)
    result, values, _ = features.prepared(CASE_ID, query)
    check_analysis(result, expected)
    for component in expected["components"]:
        for probe in component["source_probes"]:
            assert values.ravel()[probe["flat_index"]] == probe["value"]
    association = expected.get("observation_association")
    if association is None:
        return
    for region in result["regions"]:
        reference = association.get(region["id"], {"eligible_samples": 0, "eligible_profiles": 0, "rows": []})
        assert region["eligible_samples"] == reference["eligible_samples"]
        assert region["eligible_profiles"] == reference["eligible_profiles"]
        actual = {(p["profile_id"], index) for p in region["observations"] for index in p["sample_indices"]}
        expected_rows = {(row["profile_id"], row["sample_index"]) for row in reference["rows"]}
        assert actual == expected_rows


@pytest.mark.parametrize("expected", REFERENCE["source_sections"], ids=lambda s: f"{s['variable']}-{s['time_index']}-{s['station_count']}-{s['depth_min_m']}")
def test_native_sections_and_sampled_observation_corridor(stores, expected):
    cases, features = stores
    query = query_from_reference({"query": {**expected, "lower": -100, "upper": None}}, cases)
    request = SectionQuery(query=query, start=expected["start"], end=expected["end"], stations=expected["station_count"])
    result = features.section(CASE_ID, request)
    assert result["shape"] == [len(expected["depth_m"]), expected["station_count"]]
    assert result["depth_m"] == expected["depth_m"]
    for actual, station in zip(result["stations"], expected["stations"]):
        assert actual["longitude"] == pytest.approx(station["requested_longitude"], abs=1e-12)
        assert actual["latitude"] == pytest.approx(station["requested_latitude"], abs=1e-12)
        assert actual["model_longitude"] == station["longitude"]
        assert actual["model_latitude"] == station["latitude"]
        assert actual["offset_km"] == pytest.approx(station["offset_m"] / 1000, abs=1e-10)
        assert actual["distance_km"] == pytest.approx(station["distance_m"] / 1000, abs=1e-10)
    reference_values = [station["values"][z] for z in range(len(expected["depth_m"])) for station in expected["stations"]]
    assert result["values"] == reference_values
    if "observation_association" in expected:
        reference = expected["observation_association"]
        actual_rows = {(r["profile_id"], r["sample_index"]): r for r in result["observations"]}
        assert len(actual_rows) == reference["eligible_samples"]
        assert len({key[0] for key in actual_rows}) == reference["eligible_profiles"]
        for row in reference["rows"]:
            actual = actual_rows[(row["profile_id"], row["sample_index"])]
            assert actual["station_index"] == row["station_index"]
            assert actual["distance_to_station_km"] == pytest.approx(row["station_distance_m"] / 1000, abs=1e-10)
            assert actual["observed"] == row["observed"]
            assert actual["depth_m"] == row["depth_m"]


def elementary_faces(member_indices, shape):
    """Independent unmerged face set by per-voxel neighbour enumeration."""
    members = {tuple(int(v) for v in np.unravel_index(i, shape)) for i in member_indices}
    faces = set()
    for cell in members:
        for axis in range(3):
            others = [i for i in range(3) if i != axis]
            for sign in (-1, 1):
                neighbour = list(cell)
                neighbour[axis] += sign
                if tuple(neighbour) not in members:
                    faces.add((axis, cell[axis] + (sign > 0), cell[others[0]], cell[others[1]], sign))
    return faces


@pytest.mark.parametrize("expected", REFERENCE["synthetic_cases"], ids=lambda case: case["name"])
def test_merged_mesh_retains_every_and_only_exposed_native_face(expected):
    values = np.array([np.nan if v is None else v for v in expected["values"]], dtype=float).reshape(expected["shape"])
    result = analyze(values, expected["axes"], query_from_reference(expected))
    for component in expected["components"]:
        faces = boundary_faces(result["labels"], component["seed_flat_index"])
        counts = Counter((axis, plane, row, col, sign)
                         for axis, plane, row_start, row_end, col_start, col_end, sign in faces
                         for row in range(row_start, row_end) for col in range(col_start, col_end))
        assert set(counts) == elementary_faces(component["members"], tuple(expected["shape"]))
        assert all(count == 1 for count in counts.values())


def test_exact_upper_depth_and_midpoint_observations(stores):
    real_cases, _ = stores
    template, digest = real_cases.require(CASE_ID)
    coordinates = Coordinates(**{**template.coordinates.model_dump(), "depth_m": [0., 10., 40.],
                                "latitude": [12., 13.], "longitude": [86., 87.]})
    manifest = template.model_copy(update={"coordinates": coordinates})
    values = np.ones((3, 2, 2))
    # The shallower bin is excluded by the threshold. Exact midpoint 5 belongs
    # to the deeper bin; exact upper query depth 10 must still be associated.
    values[0] = 0
    cases = SimpleNamespace(require=lambda _: (manifest, digest), _read_array=lambda *args: values.ravel())
    features = FeatureStore(cases, None, None)
    profile = SimpleNamespace(id="synthetic-only", platform="synthetic-only")
    rows = [SimpleNamespace(depth_m=depth, model_latitude=12., model_longitude=86., sample_index=i)
            for i, depth in enumerate([4.999, 5., 10., 10.001])]
    features.accepted_rows = lambda *args: [(profile, row) for row in rows]
    result, _, _ = features.prepared(CASE_ID, FeatureQuery(threshold=1, depth_min_m=0, depth_max_m=10))
    assert len(result["regions"]) == 1
    assert result["regions"][0]["eligible_samples"] == 2
    assert result["regions"][0]["observations"][0]["sample_indices"] == [1, 2]


def test_real_region_mesh_covers_original_membership_boundary(stores):
    cases, features = stores
    expected = next(q for q in REFERENCE["source_queries"] if q.get("name") == "default-query")
    result, _, _ = features.prepared(CASE_ID, query_from_reference(expected, cases))
    seed = expected["components"][0]["seed_flat_index"]
    faces = boundary_faces(result["labels"], seed)
    assert faces is not None
    expanded = Counter((axis, plane, row, col, sign)
                       for axis, plane, row_start, row_end, col_start, col_end, sign in faces
                       for row in range(row_start, row_end) for col in range(col_start, col_end))
    assert set(expanded) == elementary_faces(result["members"][seed], result["labels"].shape)
    assert all(count == 1 for count in expanded.values())


def test_source_default_numerical_runtime_measurement(stores, record_property):
    cases, _ = stores
    reference = next(q for q in REFERENCE["source_queries"] if q.get("name") == "default-query")
    query = query_from_reference(reference, cases)
    coords = cases.require(CASE_ID)[0].coordinates.model_dump()
    values = np.asarray(cases._read_array(CASE_ID, "analytical", query.variable, query.time_index)).reshape(40, 76, 63)
    started = perf_counter()
    result = analyze(values, coords, query)
    elapsed = perf_counter() - started
    record_property("native_query_seconds_local", elapsed)
    record_property("native_grid_cells", values.size)
    record_property("qualifying_cells", result["qualified_cells"])
    check_analysis(result, reference)
    # Timing is recorded, not promoted to an arbitrary performance guarantee.

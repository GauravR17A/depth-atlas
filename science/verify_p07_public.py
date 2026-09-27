"""Check a running P07 API against independently generated source expectations.

Uses the Python standard library only. It imports no application numerical code
and reads no runtime case arrays. Every failure is retained in the output; there
are no hidden retries. Run against a local server before running on Vercel.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests/fixtures/p07-source-reference.json"
FIXTURE_SHA = "1e45922b54acffd4f707478e650a8dc7537a39f50d4dc549234455c0f808a0b0"
CASE_ID = "bay-bengal-2024-01"
UNITS = {"temperature": "\u00b0C", "salinity": "psu", "eastward_velocity": "m/s",
         "northward_velocity": "m/s", "horizontal_kinetic_energy": "m\u00b2/s\u00b2"}


def close(actual, expected, rel=2e-12, absolute=1e-10):
    assert isinstance(actual, (int, float)) and math.isfinite(actual)
    assert math.isclose(actual, expected, rel_tol=rel, abs_tol=absolute), f"{actual!r} differs from {expected!r}"


def query(raw):
    lower, upper = raw.get("lower"), raw.get("upper")
    return {"variable": raw["variable"], "units": UNITS[raw["variable"]], "time_index": raw["time_index"],
            "operator": "between" if lower is not None and upper is not None else "at_most" if lower is None else "at_least",
            "threshold": upper if lower is None else lower,
            "upper_threshold": upper if lower is not None and upper is not None else None,
            "depth_min_m": raw["depth_min_m"], "depth_max_m": raw["depth_max_m"], "order": "volume"}


def bounds(item):
    return {"west": item["longitude"][0], "east": item["longitude"][1], "south": item["latitude"][0],
            "north": item["latitude"][1], "depth_min_m": item["depth_m"][0], "depth_max_m": item["depth_m"][1]}


def compare_region(actual, expected, association):
    assert actual["id"] == expected["id"]
    assert actual["cell_count"] == expected["cell_count"]
    assert actual["membership_sha256"] == expected["membership_sha256"]
    assert actual["center_bounds"] == bounds(expected["center_extent"])
    assert actual["cell_bounds"] == bounds(expected["cell_extent"])
    close(actual["estimated_volume_km3"], expected["estimated_volume_m3"] / 1e9)
    for name, target in (("min", "minimum"), ("max", "maximum"), ("mean", "sample_mean"), ("volume_weighted_mean", "volume_weighted_mean")):
        close(actual[name], expected[target])
    if association is not None:
        rows = association.get(expected["id"], {"rows": [], "eligible_samples": 0, "eligible_profiles": 0})
        assert actual["eligible_samples"] == rows["eligible_samples"]
        assert actual["eligible_profiles"] == rows["eligible_profiles"]
        assert {(p["profile_id"], i) for p in actual["observations"] for i in p["sample_indices"]} == {(r["profile_id"], r["sample_index"]) for r in rows["rows"]}


def mesh_volume_km3(response):
    """Independent divergence integral over the returned radial boundary faces."""
    depths, lat, lon = [response["edges"][name] for name in ("depth_m", "latitude", "longitude")]
    with localcontext() as context:
        context.prec = 70
        radius = Decimal.from_float(6371008.8)
        radians = Decimal.from_float(math.pi / 180)
        total = Decimal(0)
        for axis, plane, row0, row1, col0, col1, sign in response["faces"]:
            if axis != 0:
                continue
            sine_width = Decimal.from_float(math.sin(math.radians(lat[row1]))) - Decimal.from_float(math.sin(math.radians(lat[row0])))
            lon_width = (Decimal.from_float(lon[col1]) - Decimal.from_float(lon[col0])) * radians
            total += -sign * (radius - Decimal.from_float(depths[plane])) ** 3 / 3 * sine_width * lon_width
        return float(total / Decimal(1000000000))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-version")
    parser.add_argument("--timeout", type=float, default=45)
    args = parser.parse_args()
    body = FIXTURE_PATH.read_bytes()
    assert hashlib.sha256(body).hexdigest() == FIXTURE_SHA
    fixture = json.loads(body)
    version = args.expected_version or json.loads((ROOT / "api/release.json").read_text())["version"]
    report = {"base_url": args.base.rstrip("/"), "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "expected_version": version, "fixture_sha256": FIXTURE_SHA,
              "independence": "HTTP values checked against independent packed-source fixtures; no runtime numerical imports.",
              "requests": [], "checks": []}
    api = f"/api/cases/{CASE_ID}/features/"

    def request(path, payload=None, expected_status=200):
        start = perf_counter()
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        req = Request(report["base_url"] + path, data=data,
                      headers={"Content-Type": "application/json", "User-Agent": "OceanNavigator-P07-SourceVerifier/1"})
        try:
            response = urlopen(req, timeout=args.timeout)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            status, headers = response.status, response.headers
        report["requests"].append({"path": path, "method": "GET" if payload is None else "POST",
                                   "status": status, "bytes": len(raw), "seconds": perf_counter() - start,
                                   "app_version": headers.get("X-Ocean-App-Version"),
                                   "request_sha256": hashlib.sha256(data or b"").hexdigest()})
        assert status == expected_status, f"HTTP {status}, expected {expected_status} at {path}: {raw[:250]!r}"
        assert headers.get("X-Ocean-App-Version") == version
        assert "no-store" in headers.get("Cache-Control", "")
        return json.loads(raw)

    def check(name, action):
        started = perf_counter()
        item = {"name": name}
        try:
            detail = action()
            item.update(passed=True, detail=detail)
        except Exception as error:
            item.update(passed=False, error=f"{type(error).__name__}: {error}")
        item["seconds"] = perf_counter() - started
        report["checks"].append(item)
        print(f"{'PASS' if item['passed'] else 'FAIL'} {name}", flush=True)

    def identity(response, expected_query, kind):
        assert response["schema_version"] == "1" and response["method_version"] == "p07-native-regions-v1"
        assert response["kind"] == kind and response["case_id"] == CASE_ID
        assert response["manifest_sha256"] == fixture["model_manifest_sha256"]
        assert response["query"] == expected_query and response["units"] == expected_query["units"]
        from datetime import timedelta
        expected_time = datetime(2024, 1, 7, tzinfo=timezone.utc) + timedelta(hours=12 * expected_query["time_index"])
        assert response["model_time"] == expected_time.isoformat().replace("+00:00", "Z")
        assert response["observation_library_sha256"] == "6508c2a1a9e95a30ad9f2892bdf329f1db7fa955e567a6845e01f326497e8919"

    check("health and release identity", lambda: request("/api/health"))
    for index, expected in enumerate(fixture["source_queries"]):
        def search(expected=expected):
            settings = query(expected["query"])
            result = request(api + "search", settings)
            identity(result, settings, "threshold_regions")
            assert result["qualified_cells"] == expected["qualifying_count"]
            assert result["total_regions"] == expected["region_count"]
            assert result["returned_regions"] == min(50, expected["region_count"])
            assert result["coordinates"] == fixture["axes"]
            assert [r["id"] for r in result["regions"]] == expected["volume_order"][:50]
            by_id = {r["id"]: r for r in expected["components"]}
            for region in result["regions"]:
                compare_region(region, by_id[region["id"]], expected.get("observation_association"))
            assert all(value is None or value in by_id for value in result["footprint"]["region_ids"])
            return {"query": settings, "regions": result["total_regions"], "qualified_cells": result["qualified_cells"]}
        check(f"source query {index + 1}: {expected.get('name') or expected['query']['variable']}", search)

    for index, expected in enumerate(fixture["source_sections"]):
        def section(expected=expected):
            settings = query({**expected, "lower": -100, "upper": None})
            result = request(api + "section", {"query": settings, "start": expected["start"], "end": expected["end"], "stations": expected["station_count"]})
            identity(result, settings, "native_transect")
            assert result["depth_m"] == expected["depth_m"]
            assert result["shape"] == [len(expected["depth_m"]), expected["station_count"]]
            for actual, station in zip(result["stations"], expected["stations"]):
                close(actual["longitude"], station["requested_longitude"])
                close(actual["latitude"], station["requested_latitude"])
                assert actual["model_longitude"] == station["longitude"] and actual["model_latitude"] == station["latitude"]
                close(actual["distance_km"], station["distance_m"] / 1000)
                close(actual["offset_km"], station["offset_m"] / 1000)
            samples = [station["values"][z] for z in range(len(expected["depth_m"])) for station in expected["stations"]]
            assert result["values"] == samples
            if "observation_association" in expected:
                reference = expected["observation_association"]
                rows = {(r["profile_id"], r["sample_index"]): r for r in result["observations"]}
                assert len(rows) == reference["eligible_samples"]
                for row in reference["rows"]:
                    actual = rows[(row["profile_id"], row["sample_index"])]
                    assert actual["observed"] == row["observed"] and actual["depth_m"] == row["depth_m"]
                    assert actual["station_index"] == row["station_index"]
                    close(actual["distance_to_station_km"], row["station_distance_m"] / 1000)
            return {"variable": expected["variable"], "native_values": len(samples), "observations": len(result["observations"])}
        check(f"source section {index + 1}", section)

    for name in ("default-query", "packed-equality", "cold-deep"):
        expected = next(item for item in fixture["source_queries"] if item.get("name") == name)
        component = expected["components"][-1] if name == "packed-equality" else expected["components"][0]
        def mesh(expected=expected, component=component):
            settings = query(expected["query"])
            result = request(api + "region", {"query": settings, "region_id": component["id"]})
            identity(result, settings, "threshold_region")
            compare_region(result["region"], component, expected.get("observation_association"))
            assert result["mesh_available"] and result["face_count"] == len(result["faces"]) > 0
            volume = mesh_volume_km3(result)
            close(volume, component["estimated_volume_m3"] / 1e9, rel=5e-11, absolute=1e-9)
            return {"region_id": component["id"], "rectangles": result["face_count"], "independent_mesh_volume_km3": volume}
        check(f"returned boundary geometry: {name}", mesh)

    # One exact source sample per field and snapshot verifies values behind the
    # metadata as well, without downloading all 191,520 cells per request.
    for index, expected in enumerate(fixture["source_queries"][:35]):
        if not expected["components"]:
            continue
        probe = expected["components"][0]["source_probes"][0]
        def native_probe(expected=expected, probe=probe):
            z, y, x = probe["index_zyx"]
            lon, lat = fixture["axes"]["longitude"][x], fixture["axes"]["latitude"][y]
            params = {"variable": expected["query"]["variable"], "time_index": expected["query"]["time_index"],
                      "representation": "analytical", "operation": "depth_slice", "depth_index": z,
                      "west": lon, "east": lon, "south": lat, "north": lat}
            result = request(f"/api/cases/{CASE_ID}/subset?" + urlencode(params))
            assert result["shape"] == [1, 1, 1] and result["values"] == [probe["value"]]
            assert result["manifest_sha256"] == fixture["model_manifest_sha256"]
            return {"variable": params["variable"], "time_index": params["time_index"], "flat_index": probe["flat_index"], "value": probe["value"]}
        check(f"original source scalar {index + 1}", native_probe)

    baseline = query(next(q for q in fixture["source_queries"] if q.get("name") == "default-query")["query"])
    for name, path, payload, code in (
            ("wrong units", "search", {**baseline, "units": "K"}, "incompatible_units"),
            ("invalid time", "search", {**baseline, "time_index": 7}, "invalid_request"),
            ("inverted depth", "search", {**baseline, "depth_min_m": 1000}, "invalid_request"),
            ("outside section", "section", {"query": baseline, "start": [84, 13], "end": [87, 14]}, "outside_coverage"),
            ("zero-length section", "section", {"query": baseline, "start": [87, 13], "end": [87, 13]}, "empty_section"),
            ("excess stations", "section", {"query": baseline, "start": [87, 13], "end": [88, 14], "stations": 202}, "invalid_request"),
            ("unknown region", "region", {"query": baseline, "region_id": "r9999999"}, "region_not_found")):
        def error_case(path=path, payload=payload, code=code):
            result = request(api + path, payload, expected_status=422)
            assert result["error"]["code"] == code
            return {"error_code": code}
        check(f"bounded error: {name}", error_case)

    report["passed"] = sum(c["passed"] for c in report["checks"])
    report["failed"] = len(report["checks"]) - report["passed"]
    report["request_count"] = len(report["requests"])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("base_url", "passed", "failed", "request_count")}))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())

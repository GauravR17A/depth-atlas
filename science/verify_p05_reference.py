"""Independent P05 numerical references from the pinned original source files.

Run ``python science/verify_p05_reference.py`` to regenerate the fixture or add
``--check`` to verify it without writing. This program deliberately imports no
Depth Atlas adapter, model store, instrument parser or matching code. It
reads native packed NetCDF values directly and evaluates the documented method
with a separate scalar implementation. GSW is the reviewed external pressure
conversion dependency, not a separately reimplemented thermodynamic library.

The fixture does not certify source quality. In particular, 5907083 has unusual
source calibration text; source-QC counts and review-gated counts are distinct.
Synthetic edge probes are test inputs only, never observations shown in the app.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import itertools
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gsw
import netCDF4


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests/fixtures/p05-source-reference.json"
MANIFEST = ROOT / "casepacks/bay-bengal-2024-01/manifest.json"
MANIFEST_SHA256 = "9598b33dc9eef89cb909f2811e1590ca580a143c1dbcc25d97e51a84faf7d28d"
RADIUS_KM = 6371.0088
SNAPSHOTS = (0, 1, 3, 5)
REVIEW_EXCLUDED = {"5907083"}
UTC = timezone.utc


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(value) -> str:
    return value.tobytes().decode("ascii").replace("\x00", "").strip()


def distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a, b = math.radians(lat1), math.radians(lat2)
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * RADIUS_KM * math.atan2(math.sqrt(max(0.0, h)), math.sqrt(max(0.0, 1 - h)))


def decoded(variable, indices) -> float | None:
    """Read with auto mask/scale OFF; mask the native source representation."""
    raw = float(variable[indices])
    if not math.isfinite(raw):
        return None
    for key in ("_FillValue", "missing_value"):
        if key in variable.ncattrs() and raw == float(variable.getncattr(key)):
            return None
    if "valid_min" in variable.ncattrs() and raw < float(variable.valid_min):
        return None
    if "valid_max" in variable.ncattrs() and raw > float(variable.valid_max):
        return None
    return raw * float(getattr(variable, "scale_factor", 1)) + float(getattr(variable, "add_offset", 0))


def bracket(depths: list[float], depth: float | None) -> dict | None:
    if depth is None or depth < depths[0] or depth > depths[-1]:
        return None
    upper = bisect.bisect_left(depths, depth)
    if depths[upper] == depth:
        return {"lower_index": upper, "upper_index": upper, "weight": 0.0, "gap_m": 0.0}
    lower = upper - 1
    return {"lower_index": lower, "upper_index": upper,
            "weight": (depth - depths[lower]) / (depths[upper] - depths[lower]),
            "gap_m": depths[upper] - depths[lower]}


def sample_column(column: list[float | None], bounds: dict | None) -> float | None:
    if bounds is None:
        return None
    low, high = column[bounds["lower_index"]], column[bounds["upper_index"]]
    if low is None or high is None:
        return None
    return low + (high - low) * bounds["weight"]


def main_fixture() -> dict:
    assert digest(MANIFEST) == MANIFEST_SHA256, "Pinned model manifest changed. Do not silently rewrite reference identity."
    models = sorted((ROOT / "data/raw/hycom").glob("*.nc"))
    assert len(models) == 7
    sources = []
    dates = []
    with netCDF4.Dataset(models[0]) as d:
        d.set_auto_maskandscale(False)
        depths = [float(n) for n in d["depth"][:]]
        latitudes = [float(n) for n in d["lat"][:]]
        longitudes = [float(n) for n in d["lon"][:]]
        assert d["water_temp"].standard_name == "sea_water_temperature"
        assert d["water_temp"].comment == "in-situ temperature"
        assert d["salinity"].units == "psu"
        packing = {name: {"scale_factor": float(d[name].scale_factor), "add_offset": float(d[name].add_offset),
                          "fill": int(d[name]._FillValue), "source_units": d[name].units,
                          "standard_name": d[name].standard_name}
                   for name in ("water_temp", "salinity")}
    for path in models:
        with netCDF4.Dataset(path) as d:
            d.set_auto_maskandscale(False)
            assert d["time"].units == "hours since 2000-01-01 00:00:00"
            date = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(hours=float(d["time"][0]))
            dates.append(date)
        sources.append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "bytes": path.stat().st_size})

    profiles = []
    for path in sorted((ROOT / "data/raw/argo").glob("D*.nc")):
        sha = digest(path)
        sources.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha, "bytes": path.stat().st_size})
        with netCDF4.Dataset(path) as d:
            d.set_auto_maskandscale(False)
            assert text(d["DATA_MODE"][:]) == "D"
            assert d["JULD"].units == "days since 1950-01-01 00:00:00 UTC"
            assert "ITS-90" in d["TEMP_ADJUSTED"].long_name
            platform = text(d["PLATFORM_NUMBER"][:])
            cycle = int(d["CYCLE_NUMBER"][0])
            latitude, longitude = float(d["LATITUDE"][0]), float(d["LONGITUDE"][0])
            # Integer rounding here is explicitly the P04 observation contract.
            moment = datetime(1950, 1, 1, tzinfo=UTC) + timedelta(seconds=round(float(d["JULD"][0]) * 86400))
            position_qc, time_qc = text(d["POSITION_QC"][:]), text(d["JULD_QC"][:])
            station = min((distance(latitude, longitude, y, x), iy, ix)
                          for iy, y in enumerate(latitudes) for ix, x in enumerate(longitudes))
            separation, iy, ix = station
            observations = []
            for index in range(len(d.dimensions["N_LEVELS"])):
                pressure = decoded(d["PRES_ADJUSTED"], (0, index))
                depth = None if pressure is None or pressure < 0 else max(0.0, -float(gsw.z_from_p(pressure, latitude)))
                readings = {}
                for name, prefix in (("temperature", "TEMP"), ("salinity", "PSAL")):
                    readings[name] = {"raw": decoded(d[prefix], (0, index)),
                                      "selected_adjusted": decoded(d[prefix + "_ADJUSTED"], (0, index)),
                                      "qc": text(d[prefix + "_ADJUSTED_QC"][0, index:index + 1])}
                observations.append({"index": index, "pressure_dbar": pressure,
                                     "pressure_qc": text(d["PRES_ADJUSTED_QC"][0, index:index + 1]),
                                     "depth_m": depth, "bracket": bracket(depths, depth), "readings": readings})
            calibration = text(d["SCIENTIFIC_CALIB_COMMENT"][:])
            reference = {"profile_id": f"argo-{platform}-{cycle}-0-{sha[:10]}", "platform": platform,
                         "source_file": path.name, "source_sha256": sha, "latitude": latitude,
                         "longitude": longitude, "source_juld": float(d["JULD"][0]),
                         "time": moment.isoformat().replace("+00:00", "Z"), "position_qc": position_qc,
                         "time_qc": time_qc, "nearest_column": {"latitude_index": iy, "longitude_index": ix,
                         "latitude": latitudes[iy], "longitude": longitudes[ix], "distance_km": separation},
                         "source_review_required": platform in REVIEW_EXCLUDED,
                         "calibration_comment": calibration, "observations": observations, "snapshots": {}}
        for time_index in SNAPSHOTS:
            with netCDF4.Dataset(models[time_index]) as d:
                d.set_auto_maskandscale(False)
                columns = {}
                for name, field in (("temperature", "water_temp"), ("salinity", "salinity")):
                    values = [decoded(d[field], (0, iz, iy, ix)) for iz in range(len(depths))]
                    samples = [sample_column(values, o["bracket"]) for o in observations]
                    residuals = [None if value is None or o["readings"][name]["selected_adjusted"] is None
                                 else value - o["readings"][name]["selected_adjusted"]
                                 for value, o in zip(samples, observations)]
                    columns[name] = {"native_packed": [int(d[field][0, iz, iy, ix]) for iz in range(len(depths))],
                                     "native_decoded": values, "model_at_observation_depth": samples,
                                     "model_minus_observation": residuals}
                reference["snapshots"][str(time_index)] = {"time": dates[time_index].isoformat().replace("+00:00", "Z"),
                    "signed_observation_minus_model_seconds": (moment - dates[time_index]).total_seconds(), "columns": columns}
        profiles.append(reference)

    scenarios = []
    for time_index, hours, radius, gap, qc in itertools.product(SNAPSHOTS, (0, 2, 3, 6, 24, 72), (0, 2, 5, 10), (25, 100, 500), (("1",), ("1", "2"))):
        # Counts remain separate by variable even though this source selection has
        # matching T/S quality masks. Do not generalize that property to imports.
        source_counts = {name: [] for name in ("temperature", "salinity")}
        review_counts = {name: [] for name in ("temperature", "salinity")}
        for profile in profiles:
            snapshot = profile["snapshots"][str(time_index)]
            station_ok = (profile["nearest_column"]["distance_km"] <= radius
                          and abs(snapshot["signed_observation_minus_model_seconds"]) <= hours * 3600
                          and profile["position_qc"] in qc and profile["time_qc"] in qc)
            for variable in source_counts:
                count = 0
                if station_ok:
                    samples = snapshot["columns"][variable]["model_at_observation_depth"]
                    for observation, model_value in zip(profile["observations"], samples):
                        reading = observation["readings"][variable]
                        count += int(observation["pressure_qc"] in qc and reading["qc"] in qc
                                     and reading["selected_adjusted"] is not None and model_value is not None
                                     and observation["bracket"] is not None and observation["bracket"]["gap_m"] <= gap)
                source_counts[variable].append(count)
                review_counts[variable].append(0 if profile["source_review_required"] else count)
        scenarios.append({"time_index": time_index, "max_time_hours": hours, "max_distance_km": radius,
                          "max_vertical_gap_m": gap, "qc": list(qc), "source_qc_counts": source_counts,
                          "review_gated_counts": review_counts})

    primary = profiles[0]
    probes = []
    for depth in (-1, 0, 2, 1000, 1500, 1750, 2000, 3000, 3500, 4000, 5000, 5001):
        bounds = bracket(depths, depth)
        probes.append({"label": "synthetic test depth, not an observed sample", "depth_m": depth,
                       "bracket": bounds, "model": {name: sample_column(primary["snapshots"]["1"]["columns"][name]["native_decoded"], bounds)
                                                      for name in ("temperature", "salinity")}})
    assert sum(len(p["observations"]) for p in profiles) == 720
    assert profiles[1]["observations"][0]["pressure_qc"] == "1"
    assert [o["index"] for o in profiles[1]["observations"] if o["pressure_qc"] == "4"] == [29, 30]
    assert digest(MANIFEST) == MANIFEST_SHA256
    return {"fixture_version": 1, "generator": "science/verify_p05_reference.py",
            "independence": "No application adapter, instrument parser, store or matching implementation is imported. Native packed source values are decoded in float64 here. All model sample arrays retain the original observation row order.",
            "pressure_depth": {"method": "max(0,-gsw.z_from_p(PRES_ADJUSTED,latitude))", "gsw_version": gsw.__version__,
                               "defaults": "zero dynamic height and zero sea-surface geopotential", "reference": "https://www.teos-10.org/pubs/gsw/html/gsw_z_from_p.html",
                               "limitation": "GSW is shared as an external reference library; this fixture does not independently reimplement TEOS-10."},
            "method": {"time": "Fixed selected snapshot; absolute observation-to-snapshot offset, no temporal interpolation.",
                       "horizontal": "Minimum great-circle distance over every native grid centre, no search for a wetter neighbour.",
                       "earth_radius_km": RADIUS_KM, "vertical": "Exact native node or linear interpolation between immediately adjacent finite native depths. No extrapolation or mask bridging.",
                       "residual_sign": "model minus observation", "limits_are_inclusive": True,
                       "source_review_policy": "5907083 remains represented in raw source references but is excluded from review_gated_counts because unusual calibration metadata needs source review.",
                       "temperature_scale_limitation": "HYCOM declares in-situ degC but does not explicitly declare ITS-90 in its source attributes; Argo explicitly declares ITS-90."},
            "model_manifest_sha256": MANIFEST_SHA256, "model_depth_m": depths, "model_packing": packing,
            "profile_order": [p["platform"] for p in profiles], "sources": sources, "profiles": profiles,
            "count_scenarios": scenarios, "synthetic_edge_probes": {"profile_column": primary["profile_id"], "time_index": 1, "probes": probes}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare the deterministic bytes without writing.")
    options = parser.parse_args()
    fixture = main_fixture()
    encoded = (json.dumps(fixture, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    if options.check:
        assert OUTPUT.read_bytes() == encoded, "Independent P05 fixture differs from current raw sources or generator."
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(encoded)
    print(json.dumps({"fixture": str(OUTPUT), "action": "verified" if options.check else "generated",
                      "profiles": len(fixture["profiles"]), "samples": sum(len(p["observations"]) for p in fixture["profiles"]),
                      "count_scenarios": len(fixture["count_scenarios"]), "bytes": len(encoded),
                      "sha256": hashlib.sha256(encoded).hexdigest(), "model_manifest_unchanged": True}))


if __name__ == "__main__":
    main()

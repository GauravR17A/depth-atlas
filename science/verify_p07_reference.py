"""Independent P07 expectations from original packed files and analytic test grids.

No production adapter, store, query, geometry or observation matcher is imported.
SciPy's compiled connected-component implementation is an offline oracle only.
Volumes use Decimal integration of spherical shells and scalar summation. This
program produces test evidence, not a deployable data source or observations.
"""

from __future__ import annotations

import argparse
import bisect
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path

import netCDF4
import numpy as np
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests/fixtures/p07-source-reference.json"
MANIFEST_SHA = "9598b33dc9eef89cb909f2811e1590ca580a143c1dbcc25d97e51a84faf7d28d"
P05_SHA = "4773abc59e39596bc2d4cff951a40a805d6d3463f7dc173992b20ea1a7d574c9"
RADIUS_M = 6371008.8
SOURCE_NAMES = {"temperature": "water_temp", "salinity": "salinity",
                "eastward_velocity": "water_u", "northward_velocity": "water_v"}


def sha(body):
    return hashlib.sha256(body).hexdigest()


def midpoint_edges(axis):
    return [axis[0], *[(a + b) / 2 for a, b in zip(axis, axis[1:])], axis[-1]]


def shell_integral(top, bottom):
    """Independent, high precision antiderivative rather than runtime expansion."""
    with localcontext() as context:
        context.prec = 70
        radius = Decimal.from_float(RADIUS_M)
        low, high = Decimal.from_float(top), Decimal.from_float(bottom)
        return float(((radius - low) ** 3 - (radius - high) ** 3) / 3)


def geometry(depths, latitudes, longitudes, low, high):
    ze, ye, xe = map(midpoint_edges, (depths, latitudes, longitudes))
    clipped = [(max(low, ze[z]), min(high, ze[z + 1])) for z in range(len(depths))]
    shells = [shell_integral(a, b) if b > a else 0.0 for a, b in clipped]
    areas = [[(math.sin(math.radians(n)) - math.sin(math.radians(s))) * math.radians(e - w)
              for w, e in zip(xe, xe[1:])] for s, n in zip(ye, ye[1:])]
    return ze, ye, xe, clipped, shells, areas


def component_reference(values, axes, query, include_members=False):
    depths, latitudes, longitudes = axes
    low, high = query["depth_min_m"], query["depth_max_m"]
    ze, ye, xe, clipped, shells, areas = geometry(*axes, low, high)
    depth_selected = np.array([low <= depth <= high and shells[z] > 0
                               for z, depth in enumerate(depths)], dtype=bool)
    eligible = np.isfinite(values) & depth_selected[:, None, None]
    selected = eligible.copy()
    if query.get("lower") is not None:
        selected &= values >= query["lower"]
    if query.get("upper") is not None:
        selected &= values <= query["upper"]
    labels, count = ndimage.label(selected, structure=ndimage.generate_binary_structure(3, 1))
    components = []
    for label in range(1, count + 1):
        flat = np.flatnonzero(labels.ravel() == label)
        indices = [tuple(int(n) for n in np.unravel_index(int(i), values.shape)) for i in flat]
        samples = [float(values[z, y, x]) for z, y, x in indices]
        volumes = [shells[z] * areas[y][x] for z, y, x in indices]
        total = math.fsum(volumes)
        z0, y0, x0 = np.min(indices, axis=0).tolist()
        z1, y1, x1 = np.max(indices, axis=0).tolist()
        component = {
            "id": f"r{int(flat[0])}", "seed_flat_index": int(flat[0]),
            "cell_count": len(indices),
            "membership_sha256": sha(np.asarray(flat, dtype="<i8").tobytes()),
            "estimated_volume_m3": total, "minimum": min(samples), "maximum": max(samples),
            "sample_mean": math.fsum(samples) / len(samples),
            "volume_weighted_mean": math.fsum(v * w for v, w in zip(samples, volumes)) / total,
            "center_extent": {"longitude": [longitudes[x0], longitudes[x1]],
                              "latitude": [latitudes[y0], latitudes[y1]],
                              "depth_m": [depths[z0], depths[z1]]},
            "cell_extent": {"longitude": [xe[x0], xe[x1 + 1]], "latitude": [ye[y0], ye[y1 + 1]],
                            "depth_m": [clipped[z0][0], clipped[z1][1]]},
            "source_probes": [{"flat_index": int(flat[i]), "index_zyx": indices[i], "value": samples[i],
                               "estimated_volume_m3": volumes[i]}
                              for i in sorted({0, len(indices) // 2, len(indices) - 1})],
        }
        if include_members:
            component["members"] = [int(n) for n in flat]
        components.append(component)
    return {"query": query, "selected_depth_indices": np.flatnonzero(depth_selected).tolist(),
            "eligible_count": int(np.count_nonzero(eligible)), "qualifying_count": int(np.count_nonzero(selected)),
            "missing_count_in_selected_depths": int(np.count_nonzero(depth_selected)) * len(latitudes) * len(longitudes) - int(np.count_nonzero(eligible)),
            "region_count": count, "estimated_volume_m3": math.fsum(c["estimated_volume_m3"] for c in components),
            "membership_sha256": sha(np.asarray(np.flatnonzero(selected), dtype="<i8").tobytes()),
            "components": components,
            "volume_order": [c["id"] for c in sorted(components, key=lambda c: (-c["estimated_volume_m3"], c["seed_flat_index"]))]}, labels


def decode(variable):
    """Manually unpack original Int16 data with masking before multiplication."""
    packed = np.asarray(variable[0], dtype=np.float64)
    valid = np.isfinite(packed)
    for attribute in ("_FillValue", "missing_value"):
        if attribute in variable.ncattrs():
            valid &= packed != float(variable.getncattr(attribute))
    if "valid_min" in variable.ncattrs():
        valid &= packed >= float(variable.valid_min)
    if "valid_max" in variable.ncattrs():
        valid &= packed <= float(variable.valid_max)
    result = packed * float(getattr(variable, "scale_factor", 1)) + float(getattr(variable, "add_offset", 0))
    result[~valid] = np.nan
    return result


def great_circle_m(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * RADIUS_M * math.atan2(math.sqrt(max(0.0, min(1.0, h))), math.sqrt(max(0.0, 1 - h)))


def section_reference(values, axes, start, end, count, depth_min, depth_max):
    depths, latitudes, longitudes = axes
    stations, cumulative = [], 0.0
    selected_z = [z for z, depth in enumerate(depths) if depth_min <= depth <= depth_max]
    previous = None
    for i in range(count):
        fraction = i / (count - 1)
        lon = start[0] + fraction * (end[0] - start[0])
        lat = start[1] + fraction * (end[1] - start[1])
        separation, y, x = min((great_circle_m(lat, lon, native_lat, native_lon), y, x)
                              for y, native_lat in enumerate(latitudes) for x, native_lon in enumerate(longitudes))
        if previous:
            cumulative += great_circle_m(previous[1], previous[0], lat, lon)
        previous = (lon, lat)
        samples = [float(values[z, y, x]) if math.isfinite(values[z, y, x]) else None for z in selected_z]
        stations.append({"station_index": i, "requested_longitude": lon, "requested_latitude": lat,
                         "longitude_index": x, "latitude_index": y, "longitude": longitudes[x], "latitude": latitudes[y],
                         "distance_m": cumulative, "offset_m": separation, "values": samples})
    return {"start": start, "end": end, "station_count": count, "depth_min_m": depth_min,
            "depth_max_m": depth_max, "selected_depth_indices": selected_z,
            "depth_m": [depths[z] for z in selected_z], "stations": stations, "length_m": cumulative}


def accepted_observations(reference, variable, time_index):
    """Repeat the recorded P05 gates using its independently decoded originals."""
    if variable not in ("temperature", "salinity") or str(time_index) not in ("0", "1", "3", "5"):
        return None
    rows = []
    for profile in reference["profiles"]:
        snapshot = profile["snapshots"][str(time_index)]
        column = profile["nearest_column"]
        if (profile["source_review_required"] or profile["position_qc"] not in ("1", "2")
                or profile["time_qc"] not in ("1", "2") or column["distance_km"] > 5
                or abs(snapshot["signed_observation_minus_model_seconds"]) > 6 * 3600):
            continue
        for level in profile["observations"]:
            reading, bracket = level["readings"][variable], level["bracket"]
            model = snapshot["columns"][variable]["model_at_observation_depth"][level["index"]]
            if (level["pressure_qc"] not in ("1", "2") or reading["qc"] not in ("1", "2")
                    or reading["selected_adjusted"] is None or level["depth_m"] is None
                    or bracket is None or bracket["gap_m"] > 500 or model is None):
                continue
            rows.append({"profile_id": profile["profile_id"], "platform": profile["platform"],
                         "sample_index": level["index"], "depth_m": level["depth_m"],
                         "latitude": profile["latitude"], "longitude": profile["longitude"],
                         "latitude_index": column["latitude_index"], "longitude_index": column["longitude_index"],
                         "observed": reading["selected_adjusted"], "model_at_observation_depth": model})
    # Baseline checks belong to the older independent fixture, so these assert
    # agreement without consulting any runtime matching implementation.
    scenario = next(case for case in reference["count_scenarios"]
                    if case["time_index"] == time_index and case["max_time_hours"] == 6
                    and case["max_distance_km"] == 5 and case["max_vertical_gap_m"] == 500
                    and case["qc"] == ["1", "2"])
    assert len(rows) == sum(scenario["review_gated_counts"][variable])
    return rows


def associate_reference(reference, query, axes, labels):
    accepted = accepted_observations(reference, query["variable"], query["time_index"])
    if accepted is None:
        return None
    edges = midpoint_edges(axes[0])
    groups = {}
    for row in accepted:
        depth = row["depth_m"]
        if not query["depth_min_m"] <= depth <= query["depth_max_m"]:
            continue
        z = min(len(axes[0]) - 1, bisect.bisect_right(edges, depth) - 1)
        label = int(labels[z, row["latitude_index"], row["longitude_index"]])
        if label == 0:
            continue
        region_id = f"r{int(np.flatnonzero(labels.ravel() == label)[0])}"
        groups.setdefault(region_id, []).append({**row, "depth_index": z})
    return {region_id: {"eligible_samples": len(rows),
                       "eligible_profiles": len({row["profile_id"] for row in rows}), "rows": rows}
            for region_id, rows in groups.items()}


def synthetic_cases():
    axes = ([0.0, 10.0, 40.0], [-1.0, 0.0, 2.0], [10.0, 11.0, 14.0])
    templates = []
    def add(name, array, lower=1.0, upper=None, low=0.0, high=40.0):
        query = {"lower": lower, "upper": upper, "depth_min_m": low, "depth_max_m": high}
        result, _ = component_reference(array, axes, query, include_members=True)
        result.update(name=name, axes={"depth_m": axes[0], "latitude": axes[1], "longitude": axes[2]},
                      values=[float(v) if np.isfinite(v) else None for v in array.ravel()], shape=list(array.shape))
        templates.append(result)
    a = np.zeros((3, 3, 3)); a[0, 0, 0] = a[1, 1, 1] = a[2, 2, 2] = 1
    add("diagonal-corners-remain-three-components", a)
    a = np.zeros((3, 3, 3)); a[0, 0, 0] = a[0, 1, 1] = 1
    add("edge-touching-is-not-face-connected", a)
    a = np.zeros((3, 3, 3)); a[1, 1, 1] = a[1, 1, 2] = a[1, 2, 1] = a[2, 1, 1] = 1
    add("faces-connect-across-all-three-axes", a)
    a = np.zeros((3, 3, 3)); a[1, 1, :] = 1; a[1, 1, 1] = np.nan
    add("masked-cell-breaks-bridge", a)
    a = np.ones((3, 3, 3)); a[0, 0, 0] = 0; a[2, 2, 2] = 2
    add("inclusive-threshold-equality", a, lower=1.0, upper=1.0)
    add("empty-threshold", a, lower=10.0)
    add("all-cells-full-spherical-shell", np.ones((3, 3, 3)))
    add("irregular-depth-window-clips-bins", np.ones((3, 3, 3)), low=3.0, high=30.0)
    add("depth-window-with-no-centers", np.ones((3, 3, 3)), low=11.0, high=20.0)
    a = np.zeros((3, 3, 3)); a[0, 0, 0] = a[0, 0, 1] = a[2, 2, 2] = 1
    add("volume-order-differs-from-cell-count", a)
    a = np.full((3, 3, 3), np.nan)
    add("all-missing", a)
    a = np.arange(27, dtype=np.float64).reshape(3, 3, 3)
    add("weighted-and-sample-means-differ", a, lower=0.0)
    a = np.zeros((3, 3, 3)); a[0, 0, -1] = a[0, 1, 0] = 1
    add("flattened-row-edges-do-not-wrap", a)
    return templates


def make_fixture():
    assert sha((ROOT / "casepacks/bay-bengal-2024-01/manifest.json").read_bytes()) == MANIFEST_SHA
    p05_body = (ROOT / "tests/fixtures/p05-source-reference.json").read_bytes()
    assert sha(p05_body) == P05_SHA
    p05 = json.loads(p05_body)
    sources, models, axes = [], [], None
    source_hashes = {item["path"]: item["sha256"] for item in p05["sources"]}
    for path in sorted((ROOT / "data/raw/hycom").glob("*.nc")):
        relative, digest = path.relative_to(ROOT).as_posix(), sha(path.read_bytes())
        assert digest == source_hashes[relative]
        sources.append({"path": relative, "sha256": digest, "bytes": path.stat().st_size})
        with netCDF4.Dataset(path) as source:
            source.set_auto_maskandscale(False)
            actual_axes = tuple([float(v) for v in source[name][:]] for name in ("depth", "lat", "lon"))
            assert all("bounds" not in source[name].ncattrs() for name in ("depth", "lat", "lon"))
            if axes is not None:
                assert actual_axes == axes
            axes = actual_axes
            fields = {name: decode(source[source_name]) for name, source_name in SOURCE_NAMES.items()}
            u, v = fields["eastward_velocity"], fields["northward_velocity"]
            fields["horizontal_kinetic_energy"] = (u ** 2 + v ** 2) / 2
            models.append(fields)
    assert len(models) == 7
    scenarios = []
    for time_index in range(7):
        for variable, lower, upper, low, high in (
                ("temperature", 28.0, None, 0.0, 1000.0),
                ("salinity", None, 33.5, 0.0, 500.0),
                ("eastward_velocity", 0.25, None, 0.0, 1000.0),
                ("northward_velocity", None, -0.15, 0.0, 1000.0),
                ("horizontal_kinetic_energy", 0.08, None, 0.0, 1000.0)):
            query = {"variable": variable, "time_index": time_index, "lower": lower, "upper": upper,
                     "depth_min_m": low, "depth_max_m": high}
            expected, labels = component_reference(models[time_index][variable], axes, query)
            expected["observation_association"] = associate_reference(p05, query, axes, labels)
            scenarios.append(expected)
    for name, variable, lower, upper, low, high in (
            ("range", "temperature", 20.0, 24.0, 25.0, 1500.0),
            ("cold-deep", "temperature", None, 10.0, 100.0, 5000.0),
            ("clipped-depth", "temperature", 28.0, None, 3.0, 53.0),
            ("no-depth-centres", "temperature", 28.0, None, 101.0, 124.0),
            ("empty", "temperature", 99.0, None, 0.0, 5000.0),
            ("deepest-missing", "temperature", -100.0, None, 4500.0, 5000.0),
            ("all-finite", "temperature", -100.0, None, 0.0, 5000.0),
            ("salinity-range", "salinity", 34.0, 35.0, 0.0, 5000.0),
            ("ke-zero-inclusive", "horizontal_kinetic_energy", 0.0, None, 0.0, 5000.0),
            ("default-query", "temperature", 26.0, None, 0.0, 300.0),
            ("packed-equality", "temperature", float(models[1]["temperature"][0, 0, 0]),
             float(models[1]["temperature"][0, 0, 0]), 0.0, 1000.0)):
        query = {"variable": variable, "time_index": 1, "lower": lower, "upper": upper,
                 "depth_min_m": low, "depth_max_m": high}
        expected, labels = component_reference(models[1][variable], axes, query)
        expected["observation_association"] = associate_reference(p05, query, axes, labels)
        expected["name"] = name
        scenarios.append(expected)
    sections = []
    primary = next(profile for profile in p05["profiles"] if profile["platform"] == "1902669")
    for variable, time_index, start, end, count, low, high in (
            ("temperature", 1, [86.0, 12.4], [89.0, 14.6], 7, 0, 1000),
            ("salinity", 3, [89.0, 14.6], [86.0, 12.4], 7, 25, 1500),
            ("horizontal_kinetic_energy", 6, [axes[2][0], axes[1][0]], [axes[2][-1], axes[1][-1]], 81, 0, 5000),
            ("eastward_velocity", 0, [86.0, 13.0], [86.01, 13.001], 3, 3, 53),
            ("northward_velocity", 5, [86.5, 14.0], [88.5, 14.0], 201, 1000, 5000),
            ("temperature", 1, [86.0, 12.4], [89.0, 14.6], 7, 101, 124),
            ("temperature", 1, [primary["longitude"] - .5, primary["latitude"]],
             [primary["longitude"] + .5, primary["latitude"]], 81, 0, 300)):
        expected = section_reference(models[time_index][variable], axes, start, end, count, low, high)
        expected.update(variable=variable, time_index=time_index)
        accepted = accepted_observations(p05, variable, time_index)
        if accepted is not None:
            near = []
            for row in accepted:
                if not low <= row["depth_m"] <= high:
                    continue
                distance, station = min((great_circle_m(row["latitude"], row["longitude"],
                                                        point["requested_latitude"], point["requested_longitude"]),
                                         point["station_index"]) for point in expected["stations"])
                if distance <= 5000:
                    near.append({**row, "station_index": station, "station_distance_m": distance})
            expected["observation_association"] = {"eligible_samples": len(near),
                                                   "eligible_profiles": len({r["profile_id"] for r in near}), "rows": near}
        sections.append(expected)
    return {"fixture_version": "p07-independent-v1", "generator": "science/verify_p07_reference.py",
            "independence": "Reads original packed NetCDF with automatic decoding off. Uses offline SciPy face labeling and Decimal spherical-shell integration. Does not import app science, adapters or stores.",
            "radius_m": RADIUS_M, "model_manifest_sha256": MANIFEST_SHA,
            "p05_reference_sha256": P05_SHA, "sources": sources,
            "method": {"connectivity": "six faces; no edge/corner connections or wrapped boundaries",
                       "threshold": "inclusive finite lower/upper comparisons on decoded native float64",
                       "depth": "inclusive native centers, then positive midpoint-bin overlap clipped to the selected depth window",
                       "volume": "project estimate from midpoint bins, endpoint bounds at outermost centers, exact spherical-shell integral; no provider cell-boundary claim",
                       "membership_sha256": "ascending global C-order flat indices serialized as little-endian int64",
                       "transect": "straight lon/lat segment; evenly spaced stations; closest native column by spherical great-circle distance; original depth levels; no interpolation"},
            "axes": {"depth_m": axes[0], "latitude": axes[1], "longitude": axes[2]},
            "synthetic_cases": synthetic_cases(), "source_queries": scenarios, "source_sections": sections}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    fixture = make_fixture()
    body = (json.dumps(fixture, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    if args.check:
        assert OUTPUT.read_bytes() == body, "Independent fixture differs. Inspect changes before updating."
    else:
        OUTPUT.write_bytes(body)
    print(json.dumps({"status": "checked" if args.check else "written", "path": str(OUTPUT.relative_to(ROOT)),
                      "sha256": sha(body), "bytes": len(body), "source_queries": len(fixture["source_queries"]),
                      "source_sections": len(fixture["source_sections"]), "synthetic_cases": len(fixture["synthetic_cases"])}))


if __name__ == "__main__":
    main()

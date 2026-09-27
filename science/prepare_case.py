"""Build a versioned read-only case pack from acquired source subsets."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

from adapters.argo import parse_argo
from adapters.cf_model import json_value
from adapters.registry import ADAPTERS
from science.acquire_case import ROOT, VARIABLES
from science.case_recipes import RECIPES
from science.contracts import CaseManifest, CaseSummary, Coordinates, ProfileSummary, Provenance

CASE_ID = "bay-bengal-2024-01"
PACK = ROOT / "casepacks" / CASE_ID
VERSION = "p02.1"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n", encoding="utf-8")


def file_record(path, pack=PACK):
    return {"path": path.relative_to(pack).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def display_indices(length):
    return sorted(set(range(0, length, 2)) | {length - 1})


def prepare(case_id=CASE_ID, destination=None):
    recipe = RECIPES[case_id]
    PACK = Path(destination) if destination is not None else ROOT / "casepacks" / case_id
    acquisition = json.loads((ROOT / recipe["raw"] / "acquisition.json").read_text())
    models = sorted([f for f in acquisition["files"] if f["archive_kind"] == "packed_source_subset_reconstructed_as_netcdf"], key=lambda f: f["time"])
    expected_times = recipe.get('times')
    if len(models) != (len(expected_times) if expected_times else 7):
        raise ValueError("Acquire every declared model snapshot first.")
    if expected_times and [record['time'] for record in models] != expected_times:
        raise ValueError("Acquired timestamps differ from the declared recipe.")
    PACK.mkdir(parents=True, exist_ok=True)
    all_times, files, grids, metadata = [], [], [], []
    for record in models:
        path = ROOT / record["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Source fingerprint mismatch; refuse silent source replacement.")
        grid = ADAPTERS.load(recipe.get('adapter', 'hycom-rectilinear'), path)
        if grid.coordinates.times != [record["time"]]:
            raise ValueError("Source timestamp does not match acquisition record.")
        if grids:
            for key in ("depth_m", "latitude", "longitude", "calendar", "source_time_units"):
                if getattr(grid.coordinates, key) != getattr(grids[0].coordinates, key):
                    raise ValueError("Frame coordinates differ; no implicit interpolation allowed.")
            if grid.variables != grids[0].variables:
                raise ValueError("Frame variable semantics differ.")
        grids.append(grid)
        all_times += grid.coordinates.times
        metadata.append(grid.source_metadata)
    coordinates = grids[0].coordinates.model_copy(update={"times": all_times})
    yi, xi = display_indices(len(coordinates.latitude)), display_indices(len(coordinates.longitude))
    display = coordinates.model_copy(update={"latitude": [coordinates.latitude[i] for i in yi], "longitude": [coordinates.longitude[i] for i in xi]})
    errors, stats, samples = {}, {}, []
    for t, grid in enumerate(grids):
        for key, values in grid.fields.items():
            analytical = values[0]
            decimated = analytical[:, yi, :][:, :, xi]
            visual = decimated.astype("<f4")
            valid = np.isfinite(decimated)
            error = float(np.max(np.abs(visual[valid].astype(float) - decimated[valid]))) if valid.any() else 0.0
            errors[key] = max(errors.get(key, 0.0), error)
            for representation, array in [("analytical", analytical.astype("<f8")), ("display", visual)]:
                path = PACK / representation / f"{key}-{t}.bin.gz"
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(gzip.compress(array.tobytes(order="C"), compresslevel=6, mtime=0))
                files.append(file_record(path, PACK) | {"representation": representation, "variable": key, "time_index": t, "shape": list(array.shape), "dtype": "<f8" if representation == "analytical" else "<f4"})
            stats[f"{key}-{t}"] = {"minimum": float(np.nanmin(analytical)), "maximum": float(np.nanmax(analytical)), "valid": int(np.isfinite(analytical).sum()), "missing": int(np.isnan(analytical).sum())}
        # A native-grid point near the central case, clearly separate from any float.
        y, x = len(coordinates.latitude) // 2, len(coordinates.longitude) // 2
        for z in (0, 19, 26, 35):
            samples.append({"time_index": t, "time": all_times[t], "depth_index": z, "latitude_index": y, "longitude_index": x, "depth_m": coordinates.depth_m[z], "latitude": coordinates.latitude[y], "longitude": coordinates.longitude[x], "values": {key: json_value(array[0,z,y,x]) for key,array in grid.fields.items()}})
    profiles, summaries, argo_files = [], [], []
    for record in acquisition["files"]:
        if record["archive_kind"] != "original_gdac_file":
            continue
        path = ROOT / record["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Argo source fingerprint mismatch.")
        argo_files.append(record)
        for observation in parse_argo(path, record["source_url"]):
            spatial = coordinates.latitude[0] <= observation.latitude <= coordinates.latitude[-1] and coordinates.longitude[0] <= observation.longitude <= coordinates.longitude[-1]
            temporal = all_times[0] <= observation.time <= all_times[-1]
            zrange = observation.depth_range_m
            vertical = bool(zrange and max(zrange[0],coordinates.depth_m[0]) <= min(zrange[1],coordinates.depth_m[-1]))
            closest = min(range(len(all_times)), key=lambda i: abs((np.datetime64(all_times[i].rstrip("Z")) - np.datetime64(observation.time.rstrip("Z"))).astype("timedelta64[s]").astype(int)))
            observation.overlap = {"spatial": spatial, "temporal": temporal, "vertical": vertical, "eligible": bool(spatial and temporal and vertical and observation.eligible_samples > 0), "nearest_model_time": all_times[closest], "time_offset_seconds": int((np.datetime64(observation.time.rstrip("Z")) - np.datetime64(all_times[closest].rstrip("Z"))).astype("timedelta64[s]").astype(int)), "meaning": "Within case bounds and time/depth coverage; no model/profile interpolation or validation score has been computed."}
            profile_path = PACK / "profiles" / (observation.id + ".json")
            write_json(profile_path, observation.model_dump())
            files.append(file_record(profile_path, PACK))
            profiles.append(observation)
            summaries.append(ProfileSummary.model_validate({key: getattr(observation,key) for key in ProfileSummary.model_fields}))
    if recipe.get('require_observation_overlap', True) and not any(p.overlap["eligible"] for p in profiles):
        raise ValueError("No quality-eligible Argo/model overlap; case cannot be published.")
    # Detailed source metadata belongs in the reproducibility pack, not a hand-written guess.
    meta_path = PACK / "source-metadata.json"
    write_json(meta_path, {"model_frames": metadata, "field_statistics": stats, "acquisition": acquisition})
    files.append(file_record(meta_path, PACK))
    model_provenance = Provenance(source_id="hycom-gofs31-93.0", title="HYCOM GOFS 3.1 + NCODA", kind="model_analysis", provider="NRL / HYCOM Consortium", dataset_version="GLBy0.08/expt_93.0", source_url="https://www.hycom.org/dataserver/gofs-3pt1/analysis", licence_url="https://www.hycom.org/dataserver/access-methods/ncss", licence="Approved for public release; distribution unlimited. Provided as-is, with no fitness or availability warranty.", citation="HYCOM Consortium / NRL, GOFS 3.1 41-layer HYCOM + NCODA Global Analysis, GLBy0.08/expt_93.0; source output has 40 fixed depth levels.", retrieved_at=acquisition["retrieved_at"], files=models, transformations=["Extract native packed values through serial OPeNDAP requests, one snapshot at a time; preserve source metadata in reconstructed NetCDF subsets.", *grids[0].transformations], limitations=["Historical assimilative model analysis, not a live forecast or direct measurement.", "Seven instantaneous snapshots sampled every 12 hours from a 3-hourly archive; intervening archive snapshots are not bundled.", "The source has 40 fixed output depths, distinct from the model's 41 hybrid layers.", "Argo observations may have been assimilated. Agreement is not independent validation."])
    argo_provenance = None
    if profiles:
        argo_provenance = Provenance(source_id="argo-gdac-incois", title="Argo profiles from the INCOIS DAC", kind="observation", provider="International Argo Program; INCOIS DAC; Ifremer GDAC distribution", dataset_version="GDAC files retrieved in 2026; individual update dates and SHA-256 fingerprints retained", source_url="https://data-argo.ifremer.fr/dac/incois/", licence_url="https://argo.ucsd.edu/data/acknowledging-argo/", licence="Freely available without restriction; acknowledge Argo and contributing national programs.", citation="Argo (2000), Argo float data and metadata from Global Data Assembly Centre (Argo GDAC), SEANOE, https://doi.org/10.17882/42182", retrieved_at=acquisition["retrieved_at"], files=argo_files, transformations=[profiles[0].qc_policy, profiles[0].depth_method, "Preserve raw/adjusted values, QC, adjusted errors, original source level order and calibration metadata."], limitations=["These January 2024 observations are historical, not live 2026 observations.", "Seven profiles do not establish basin-wide observational coverage." if case_id==CASE_ID else f"{len(profiles)} profiles do not establish basin-wide observational coverage.", "Depth is derived from pressure and latitude; dynamic height and sea-surface geopotential are not supplied."])
    case = CaseSummary(id=case_id,title=recipe["name"]+" · 7–10 January 2024",region_id=recipe["region_id"],bounds=(coordinates.longitude[0],coordinates.latitude[0],coordinates.longitude[-1],coordinates.latitude[-1]),time_start=all_times[0],time_end=all_times[-1],time_count=len(all_times),depth_range_m=(coordinates.depth_m[0],coordinates.depth_m[-1]),depth_count=len(coordinates.depth_m),profile_count=len(profiles),variables=list(grids[0].fields),source_label="HYCOM GOFS 3.1 + Argo / INCOIS DAC")
    representations={"analytical":{"dtype":"little-endian float64","shape":[len(coordinates.depth_m),len(coordinates.latitude),len(coordinates.longitude)],"method":"Native subset grid, decoded once. No interpolation, rounding, smoothing or gap filling."},"display":{"dtype":"little-endian float32","shape":[len(display.depth_m),len(display.latitude),len(display.longitude)],"method":"Select every second latitude/longitude plus the last coordinate, retain every depth; round selected values to float32. No interpolation or gap filling.","latitude_source_indices":yi,"longitude_source_indices":xi,"max_absolute_rounding_error":errors},"missing":"IEEE NaN in binary; JSON null in API. Missing does not mean zero or necessarily land.","array_order":"depth,latitude,longitude in C order; longitude changes fastest."}
    if case_id != CASE_ID:
        representations['display']['variable_ranges'] = {key: {'min': float(np.floor(min(stats[f'{key}-{t}']['minimum'] for t in range(len(all_times))))), 'max': float(np.ceil(max(stats[f'{key}-{t}']['maximum'] for t in range(len(all_times)))))} for key in ('temperature','salinity')}
    manifest = CaseManifest(case=case,coordinates=coordinates,display_coordinates=display,variables=grids[0].variables,sources=[model_provenance]+([argo_provenance] if argo_provenance else []),profiles=summaries,representations=representations,samples=samples,limitations=["A bounded historical compatibility case, not live ocean monitoring.","Model cells below bathymetry or otherwise unavailable remain missing; 5000 m is an output coordinate, not guaranteed usable depth everywhere.","No chlorophyll, vertical velocity, glider, ship CTD or BGC variables are included.","This phase provides real data and source summaries. Scientific 3D rendering and model/profile comparison are subsequent phases." if case_id==CASE_ID else "A bounded regional example; comparisons use explicit source/QC and matching rules, not independent forecast validation."],files=files,processing_version=recipe["processing_version"])
    if expected_times:
        manifest.representations['unavailable_tools'] = ['heat']
        manifest.case.title = recipe['title']
        manifest.case.source_label = "HYCOM GOFS 3.1" + (" + Argo" if profiles else "")
        model_provenance.limitations[1] = f"{len(all_times)} instantaneous snapshots sampled from a 3-hourly archive; only the declared timestamps are bundled."
        manifest.limitations = [
            "Historical HYCOM analysis for a bounded region and explicit dates, not current conditions.",
            "All 40 native output depths are retained. Missing source cells remain missing.",
            "No chlorophyll model field is supplied. Imported chlorophyll is an observation with its own units and QC.",
            "No bundled matched observations or surface heatwave series are supplied for this case. Import compatible observations for co-display; imported numerical comparisons remain unavailable.",
            "The same source and adapter as the January cases are used with newly acquired March snapshots. This is not proof of arbitrary model-format support.",
        ]
    write_json(PACK / "manifest.json",manifest.model_dump())
    print(json.dumps({"case":case.model_dump(),"eligible_profiles":sum(p.overlap["eligible"] for p in profiles),"analytical_shape":representations["analytical"]["shape"],"display_shape":representations["display"]["shape"],"pack_bytes":sum(p.stat().st_size for p in PACK.rglob('*') if p.is_file()),"manifest_sha256":hashlib.sha256((PACK/'manifest.json').read_bytes()).hexdigest()},indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",choices=RECIPES,default=CASE_ID)
    prepare(parser.parse_args().case)

"""Reproduce the bounded historical case. Serial HYCOM requests, no credentials."""

import argparse
import hashlib
import json
import time as time_module
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import netCDF4
import numpy as np
from pydap.client import open_url
from requests.exceptions import RequestException
from science.case_recipes import RECIPES

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://tds.hycom.org/thredds/dodsC/GLBy0.08/expt_93.0"
VARIABLES = ["water_temp", "salinity", "water_u", "water_v"]
PROFILES = ["1902669", "2903891", "4903775", "4903776", "5907083", "7901125", "7901126"]


def fingerprint(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def acquire(case_id='bay-bengal-2024-01') -> None:
    recipe = RECIPES[case_id]
    raw = ROOT / recipe['raw']
    model_dir, argo_dir = raw / "hycom", raw / "argo"
    model_dir.mkdir(parents=True, exist_ok=True)
    argo_dir.mkdir(parents=True, exist_ok=True)
    journal_path = raw / "acquisition.json"
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else {"schema_version": "1", "retrieved_at": datetime.now(timezone.utc).isoformat(), "files": []}
    def record(path, **detail):
        item = fingerprint(path) | detail
        journal["files"] = [f for f in journal["files"] if f["path"] != item["path"]] + [item]
        journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")
    ds = open_url(BASE, protocol="dap2", timeout=60)
    time = np.asarray(ds["time"][:].data)
    lat, lon, depth = [np.asarray(ds[k][:].data) for k in ("lat", "lon", "depth")]
    west,south,east,north = recipe['bounds']
    lat_ids, lon_ids = np.where((lat >= south) & (lat <= north))[0], np.where((lon >= west) & (lon <= east))[0]
    time_values = (netCDF4.date2num(
        [datetime.fromisoformat(t.replace('Z', '+00:00')) for t in recipe['times']],
        ds['time'].attributes['units'], calendar=ds['time'].attributes['calendar'])
        if 'times' in recipe else np.arange(210528, 210600 + 1, 12, dtype=float))
    assert (len(depth),len(lat_ids),len(lon_ids)) == recipe['shape'], "Source grid changed; review recipe."
    for numeric in time_values:
        matches = np.flatnonzero(time == numeric)
        if len(matches) != 1:
            raise ValueError("Required historical timestamp unavailable; do not substitute a forecast.")
        index = int(matches[0])
        stamp = netCDF4.num2date(numeric, ds["time"].attributes["units"], calendar=ds["time"].attributes["calendar"])
        path = model_dir / (stamp.strftime("%Y%m%dT%H%M%SZ") + ".nc")
        known = next((f for f in journal["files"] if f["path"] == path.relative_to(ROOT).as_posix()), None)
        if path.exists() and known:
            if fingerprint(path)["sha256"] != known["sha256"]:
                raise ValueError("Cached source checksum changed; inspect it before replacing the acquisition record.")
            print("Verified cached", path.name, flush=True)
            continue
        arrays = {}
        for name in VARIABLES:
            print("Reading", stamp.isoformat(), name, flush=True)
            # One request at a time, one timestamp, native-grid stride 1.
            for attempt in range(3):
                try:
                    arrays[name] = np.asarray(ds[name][index:index+1, :, int(lat_ids[0]):int(lat_ids[-1])+1, int(lon_ids[0]):int(lon_ids[-1])+1].data, dtype=np.int16)
                    break
                except (RequestException, TimeoutError, OSError) as exc:
                    if attempt == 2:
                        raise
                    print(f"Source request failed ({type(exc).__name__}); serial retry {attempt + 1}/2.", flush=True)
                    time_module.sleep(5 * (attempt + 1))
            assert arrays[name].shape == (1, *recipe['shape'])
        temp = path.with_suffix(".partial.nc")
        with netCDF4.Dataset(temp, "w", format="NETCDF4") as out:
            out.setncatts(ds.attributes.get("NC_GLOBAL", {}))
            out.setncattr("ocean_navigator_acquisition", "Packed OPeNDAP subset, reconstructed as NetCDF without interpolation; original whole archive file not downloaded.")
            out.setncattr("source_url", BASE)
            out.setncattr("source_time_index", index)
            out.setncattr("source_lat_indices", [int(lat_ids[0]), int(lat_ids[-1])])
            out.setncattr("source_lon_indices", [int(lon_ids[0]), int(lon_ids[-1])])
            for name, vals in [("time", [numeric]), ("depth", depth), ("lat", lat[lat_ids]), ("lon", lon[lon_ids])]:
                out.createDimension(name, len(vals))
                v = out.createVariable(name, "f8", (name,))
                v.setncatts(ds[name].attributes)
                v[:] = vals
            for name, vals in arrays.items():
                attrs = dict(ds[name].attributes)
                fill = np.int16(attrs.pop("_FillValue"))
                # HYCOM's DAS explicitly declares these packing attributes Float32.
                for key in ("scale_factor", "add_offset"):
                    attrs[key] = np.float32(attrs[key])
                attrs["missing_value"] = np.int16(attrs["missing_value"])
                v = out.createVariable(name, "i2", ("time", "depth", "lat", "lon"), fill_value=fill, zlib=True, complevel=4)
                v.setncatts(attrs)
                v.set_auto_maskandscale(False)
                v[:] = vals
        temp.replace(path)
        record(path, source_url=BASE, time_index=index, time_numeric=float(numeric), time=stamp.strftime("%Y-%m-%dT%H:%M:%SZ"), depth_indices=[0,39], latitude_indices=[int(lat_ids[0]),int(lat_ids[-1])], longitude_indices=[int(lon_ids[0]),int(lon_ids[-1])], stride=1, archive_kind="packed_source_subset_reconstructed_as_netcdf")
        print("Saved", path.name, path.stat().st_size, flush=True)
    for profile_path in recipe['profiles']:
        filename = profile_path.rsplit('/',1)[1]
        url = f"https://data-argo.ifremer.fr/dac/{profile_path}"
        path = argo_dir / filename
        known = next((f for f in journal["files"] if f["path"] == path.relative_to(ROOT).as_posix()), None)
        if path.exists() and known and fingerprint(path)["sha256"] != known["sha256"]:
            raise ValueError("Cached Argo source checksum changed; review before replacing it.")
        if not path.exists():
            with urlopen(url, timeout=45) as r:
                body = r.read(4_000_001)
                if len(body) > 4_000_000:
                    raise ValueError("Profile exceeds 4 MB limit.")
                path.write_bytes(body)
        record(path, source_url=url, archive_kind="original_gdac_file")
    print("Acquisition complete", journal_path, flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=RECIPES,default='bay-bengal-2024-01')
    acquire(parser.parse_args().case)

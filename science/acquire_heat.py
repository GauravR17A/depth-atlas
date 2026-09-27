"""Acquire bounded, unmodified NOAA AOML/PSL OISST v2.1 responses.

The six positions are fixed from the two existing case rectangles before
examining event outcomes. No heatwave calculation belongs in acquisition.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
import netCDF4
from pydap.client import open_dods_file

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/heat"
BASE = "https://psl.noaa.gov/thredds/dodsC/Datasets/noaa.oisst.v2.highres"
YEARS = tuple(range(1982, 2026))
# Two latitude rows and the bounded longitude interval covering all six points.
LAT_START, LAT_STRIDE, LAT_STOP = 413, 16, 429
LON_START, LON_STOP = 268, 355


def fingerprint(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def acquire(years=YEARS, workers=2) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    journal_path = RAW / "acquisition.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.exists() else {
        "schema_version": "1", "source": "NOAA PSL OISST v2.1 annual archive",
        "started_at": datetime.now(timezone.utc).isoformat(), "files": [], "attempts": []}

    journal_lock = threading.RLock()
    stop_on_service_failure = threading.Event()
    def save():
        with journal_lock:
            journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")

    def fetch(url: str, path: Path, **detail):
        if stop_on_service_failure.is_set():
            raise RuntimeError("Acquisition paused after repeated service failures")
        relative = path.relative_to(ROOT).as_posix()
        known = next((f for f in journal["files"] if f["path"] == relative), None)
        if path.exists() and known:
            if fingerprint(path)["sha256"] != known["sha256"]:
                raise ValueError(f"Cached source checksum changed: {relative}")
            print("Verified cache", path.name, flush=True)
            return
        for attempt in range(1, 4):
            started = datetime.now(timezone.utc).isoformat()
            clock = time.perf_counter()
            try:
                response = requests.get(url, timeout=(10, 85))
                response.raise_for_status()
                if len(response.content) > 2_000_000:
                    raise ValueError("Unexpectedly large bounded source response")
                if path.suffix == ".dods" and b"\nData:\n" not in response.content:
                    raise ValueError("Response is not a DAP2 binary data document")
                tmp = path.with_suffix(path.suffix + ".partial")
                tmp.write_bytes(response.content)
                if path.suffix == ".dods":
                    ds = open_dods_file(str(tmp))
                    expected_days = detail["time_indices"][1] - detail["time_indices"][0] + 1
                    if ds["sst"].array.shape != (expected_days, 2, 88):
                        raise ValueError("Annual source shape differs from declared recipe")
                    np.testing.assert_array_equal(ds["sst"]["lat"].data, [13.375, 17.375])
                    np.testing.assert_array_equal(ds["sst"]["lon"].data,
                                                  np.arange(67.125, 89, .25))
                tmp.replace(path)
                journal["files"].append(fingerprint(path) | {
                    "source_url": url, "resolved_url": response.url,
                    "retrieved_at": started, "http_status": response.status_code,
                    "archive_kind": "unmodified_dap2_response" if path.suffix == ".dods" else "source_metadata",
                    **detail})
                journal["attempts"].append({"url": url, "attempt": attempt, "started_at": started,
                    "elapsed_s": round(time.perf_counter() - clock, 3), "outcome": "saved"})
                save()
                print("Saved", path.name, len(response.content), flush=True)
                return
            except (requests.RequestException, ValueError, OSError, EOFError) as exc:
                journal["attempts"].append({"url": url, "attempt": attempt, "started_at": started,
                    "elapsed_s": round(time.perf_counter() - clock, 3),
                    "outcome": type(exc).__name__, "detail": str(exc)[:500]})
                save()
                print("Request failed", path.name, attempt, type(exc).__name__, flush=True)
                if attempt == 3:
                    stop_on_service_failure.set()
                    raise
                time.sleep(5 * attempt)

    def year_chunks(year):
        if stop_on_service_failure.is_set():
            return
        base = f"{BASE}/sst.day.mean.{year}.nc"
        fetch(base + ".das", RAW / f"sst-{year}.das", year=year)
        last = (366 if calendar.isleap(year) else 365) - 1
        start = 0
        while start <= last:
            # Reuse already verified larger chunks. New work is capped at30 days
            # because the upstream service ends some longer replies near60s.
            known_chunk = next((item for item in journal["files"]
                if item.get("year") == year and item.get("archive_kind") == "unmodified_dap2_response"
                and item.get("time_indices", [-1])[0] == start), None)
            stop = known_chunk["time_indices"][1] if known_chunk else min(start + 29, last)
            constraint = f"sst[{start}:1:{stop}][{LAT_START}:{LAT_STRIDE}:{LAT_STOP}][{LON_START}:1:{LON_STOP}]"
            fetch(base + ".dods?" + constraint, RAW / f"sst-{year}-{start:03d}-{stop:03d}.dods", year=year,
                  variable="sst", time_indices=[start, stop], latitude_indices=[LAT_START, LAT_STOP],
                  latitude_stride=LAT_STRIDE, longitude_indices=[LON_START, LON_STOP], longitude_stride=1)
            start = stop + 1
    # At most two requests run together. Large annual queries exceed upstream deadlines.
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(year_chunks, year): year for year in years}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                stop_on_service_failure.set()
                failures.append((futures[future], type(exc).__name__, str(exc)))
                for pending in futures:
                    pending.cancel()
    if failures:
        raise RuntimeError(f"Incomplete acquisition; checkpoint retained: {failures}")
    journal["last_completed_at"] = datetime.now(timezone.utc).isoformat()
    save()


def acquire_primary_spots():
    """Retain three primary daily files independently of the distributor journal."""
    RAW.mkdir(parents=True, exist_ok=True)
    journal_path = RAW / "primary-source-checks.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.exists() else {
        "schema_version": "1", "files": [], "attempts": []}
    for stamp in ("19820101", "19960701", "20240107"):
        filename = f"oisst-avhrr-v02r01.{stamp}.nc"
        url = ("https://www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/"
               f"v2.1/access/avhrr/{stamp[:6]}/{filename}")
        path = RAW / filename
        known = next((r for r in journal["files"] if r["path"] == path.relative_to(ROOT).as_posix()), None)
        if path.exists() and known:
            if fingerprint(path)["sha256"] != known["sha256"]:
                raise ValueError("Primary spot-check file changed")
            continue
        # Re-download even a preliminary probe when it has no acquisition record.
        for attempt in range(1, 4):
            started = datetime.now(timezone.utc).isoformat()
            try:
                response = requests.get(url, timeout=(10, 45))
                response.raise_for_status()
                temporary = path.with_suffix(".partial.nc")
                temporary.write_bytes(response.content)
                with netCDF4.Dataset(temporary) as ds:
                    if ds.variables["sst"].shape != (1, 1, 720, 1440):
                        raise ValueError("Primary OISST daily shape changed")
                temporary.replace(path)
                journal["files"].append(fingerprint(path) | {"source_url": url,
                    "retrieved_at": started, "http_status": response.status_code, "date": stamp})
                journal["attempts"].append({"source_url": url, "attempt": attempt, "outcome": "saved"})
                break
            except (requests.RequestException, ValueError, OSError) as exc:
                journal["attempts"].append({"source_url": url, "attempt": attempt,
                    "outcome": type(exc).__name__, "detail": str(exc)[:500]})
                journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")
                if attempt == 3:
                    raise
                time.sleep(2 * attempt)
        journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")
        print("Saved primary", filename, path.stat().st_size, flush=True)


def acquire_aoml(years=YEARS):
    """Acquire fast AOML subsets serially, retaining gaps for explicit PSL recovery."""
    RAW.mkdir(parents=True, exist_ok=True)
    journal_path = RAW / "aoml-acquisition.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.exists() else {
        "schema_version": "1", "files": [], "attempts": []}
    base = "https://erddap.aoml.noaa.gov/hdb/erddap/griddap/"

    def fetch(url, path, **detail):
        relative = path.relative_to(ROOT).as_posix()
        known = next((r for r in journal["files"] if r["path"] == relative), None)
        if known:
            if not path.exists() or fingerprint(path)["sha256"] != known["sha256"]:
                raise ValueError("Cached AOML source checksum changed")
            print("Verified AOML cache", path.name, flush=True)
            return
        for attempt in range(1, 4):
            started = datetime.now(timezone.utc).isoformat()
            tick = time.perf_counter()
            try:
                response = requests.get(url, timeout=(10, 55))
                response.raise_for_status()
                if len(response.content) > 2_000_000:
                    raise ValueError("AOML source subset unexpectedly large")
                tmp = path.with_suffix(path.suffix + ".partial")
                tmp.write_bytes(response.content)
                if path.suffix == ".nc":
                    with netCDF4.Dataset(tmp) as ds:
                        var = ds.variables["sst"]
                        if var.shape[1:] != (2, 88) or var.dtype != np.dtype("float32"):
                            raise ValueError("AOML source subset grid/dtype changed")
                        np.testing.assert_array_equal(ds.variables["latitude"][:], [13.375, 17.375])
                        np.testing.assert_array_equal(ds.variables["longitude"][:], np.arange(67.125, 89, .25))
                        times = ds.variables["time"]
                        actual_dates = [t.strftime("%Y-%m-%d") for t in netCDF4.num2date(times[:], times.units)]
                        if actual_dates != detail["expected_dates"]:
                            raise ValueError("AOML dates changed after the captured coordinate query")
                        detail.pop("expected_dates")
                        detail.update(sample_count=len(actual_dates), source_start=actual_dates[0],
                                      source_end=actual_dates[-1], time_units=times.units)
                tmp.replace(path)
                journal["files"].append(fingerprint(path) | {"source_url": url,
                    "resolved_url": response.url, "retrieved_at": started,
                    "archive_kind": "unmodified_erddap_netcdf_response" if path.suffix == ".nc" else "source_metadata",
                    **detail})
                journal["attempts"].append({"source_url": url, "attempt": attempt,
                    "started_at": started, "elapsed_s": round(time.perf_counter() - tick, 3), "outcome": "saved"})
                journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")
                print("Saved AOML", path.name, len(response.content), flush=True)
                return
            except (requests.RequestException, ValueError, OSError) as exc:
                journal["attempts"].append({"source_url": url, "attempt": attempt,
                    "started_at": started, "elapsed_s": round(time.perf_counter() - tick, 3),
                    "outcome": type(exc).__name__, "detail": str(exc)[:500]})
                journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")
                if attempt == 3:
                    raise
                time.sleep(5 * attempt)

    missing_days = []
    for dataset, selected_years in [
        ("SST_OI_DAILY_1981_PRESENT_T", [y for y in years if y <= 2021]),
        ("SST_OI_DAILY_1981_PRESENT_T_V1", [y for y in years if y >= 2022])]:
        short = "aoml-old" if dataset.endswith("_T") else "aoml-modern"
        axis_path, das_path = RAW / f"{short}-time.json", RAW / f"{short}.das"
        fetch(base + dataset + ".json?time", axis_path, dataset_id=dataset)
        fetch(base + dataset + ".das", das_path, dataset_id=dataset)
        axis = json.loads(axis_path.read_text(encoding="utf-8"))["table"]["rows"]
        source_dates = [row[0][:10] for row in axis]
        if source_dates != sorted(set(source_dates)):
            raise ValueError("AOML coordinate axis is not sorted unique daily dates")
        for year in selected_years:
            indices = [i for i, value in enumerate(source_dates) if value.startswith(str(year) + "-")]
            all_dates = [(datetime(year, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
                         for i in range(366 if calendar.isleap(year) else 365)]
            available = set(source_dates[i] for i in indices)
            missing_days.extend(day for day in all_dates if day not in available)
            if not indices:
                print("AOML absent year, requires explicit recovery", year, flush=True)
                continue
            query = f"sst[{indices[0]}:1:{indices[-1]}][(13.375):16:(17.375)][(67.125):1:(88.875)]"
            fetch(base + dataset + ".nc?" + query, RAW / f"{short}-{year}.nc", year=year,
                  dataset_id=dataset, expected_dates=[source_dates[i] for i in indices],
                  time_indices=[indices[0], indices[-1]], latitude=[13.375, 17.375],
                  longitude=[67.125, 88.875], longitude_stride=1)
    journal["missing_days"] = missing_days
    journal["last_completed_at"] = datetime.now(timezone.utc).isoformat()
    journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")
    print("AOML acquisition complete; absent days require verified recovery:", len(missing_days), flush=True)


def recover_aoml_gaps():
    """Reproduce missing-date recovery serially, with source checks and no interpolation.

    Ten-day source blocks avoid the annual service's observed reply cutoff near 60 seconds.
    Existing verified blocks, including larger ones, are reused as coverage.
    """
    aoml = json.loads((RAW / "aoml-acquisition.json").read_text(encoding="utf-8"))
    if "missing_days" not in aoml:
        raise ValueError("Complete --aoml acquisition before recovering its declared date gaps")
    journal_path = RAW / "acquisition.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.exists() else {
        "schema_version": "1", "files": [], "attempts": []}
    covered = set()
    for record in journal["files"]:
        if record["archive_kind"] != "unmodified_dap2_response":
            continue
        path = ROOT / record["path"]
        if fingerprint(path)["sha256"] != record["sha256"]:
            raise ValueError("Cached recovery source checksum changed")
        first, last = record["time_indices"]
        covered.update((datetime(record["year"], 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
                       for i in range(first, last + 1))

    def fetch(url, path, **details):
        known = next((r for r in journal["files"] if r["path"] == path.relative_to(ROOT).as_posix()), None)
        if known:
            if fingerprint(path)["sha256"] != known["sha256"]:
                raise ValueError("Recovery metadata checksum changed")
            return
        for attempt in range(1, 4):
            started, tick = datetime.now(timezone.utc).isoformat(), time.perf_counter()
            try:
                response = requests.get(url, timeout=(10, 55))
                response.raise_for_status()
                temporary = path.with_suffix(path.suffix + ".partial")
                temporary.write_bytes(response.content)
                if path.suffix == ".dods":
                    ds = open_dods_file(str(temporary))
                    expected = details["time_indices"][1] - details["time_indices"][0] + 1
                    if ds["sst"].array.shape != (expected, 2, 88):
                        raise ValueError("Recovery response shape changed")
                    np.testing.assert_array_equal(ds["sst"]["lat"].data, [13.375, 17.375])
                    np.testing.assert_array_equal(ds["sst"]["lon"].data, np.arange(67.125, 89, .25))
                temporary.replace(path)
                journal["files"].append(fingerprint(path) | {"source_url": url, "resolved_url": response.url,
                    "retrieved_at": started, "archive_kind": "unmodified_dap2_response" if path.suffix == ".dods" else "source_metadata", **details})
                journal["attempts"].append({"url": url, "attempt": attempt, "started_at": started,
                    "elapsed_s": round(time.perf_counter()-tick, 3), "outcome": "saved"})
                journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")
                print("Recovered", path.name, flush=True)
                return
            except (requests.RequestException, ValueError, OSError, EOFError) as exc:
                journal["attempts"].append({"url": url, "attempt": attempt, "started_at": started,
                    "elapsed_s": round(time.perf_counter()-tick, 3), "outcome": type(exc).__name__, "detail": str(exc)[:500]})
                journal_path.write_text(json.dumps(journal, indent=2), encoding="utf-8")
                if attempt == 3:
                    raise
                time.sleep(5 * attempt)

    needed = sorted(set(aoml["missing_days"]) - covered)
    while needed:
        first = datetime.fromisoformat(needed[0])
        group = [needed[0]]
        while len(group) < 10 and len(group) < len(needed):
            following = datetime.fromisoformat(needed[len(group)])
            if following.year != first.year or (following-first).days != len(group):
                break
            group.append(needed[len(group)])
        year = first.year
        begin = (first-datetime(year, 1, 1)).days
        end = begin + len(group) - 1
        base = f"{BASE}/sst.day.mean.{year}.nc"
        fetch(base + ".das", RAW / f"sst-{year}.das", year=year)
        query = f"sst[{begin}:1:{end}][413:16:429][268:1:355]"
        fetch(base + ".dods?" + query, RAW / f"sst-{year}-{begin:03d}-{end:03d}.dods",
              year=year, time_indices=[begin, end])
        needed = needed[len(group):]
    print("Every absent AOML calendar date has a checked PSL source response", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, choices=YEARS)
    parser.add_argument("--primary-spots", action="store_true")
    parser.add_argument("--aoml", action="store_true")
    parser.add_argument("--recover-gaps", action="store_true")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    if args.primary_spots:
        acquire_primary_spots()
    elif args.aoml:
        acquire_aoml(tuple(args.years) if args.years else YEARS)
    elif args.recover_gaps:
        recover_aoml_gaps()
    else:
        acquire(tuple(args.years) if args.years else YEARS, workers=args.workers)

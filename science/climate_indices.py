"""Pinned official climate-index snapshots and strict, deterministic parsers.

Acquisition is an offline preparation action. Production never refreshes labels
from a mutable provider endpoint. No index is reconstructed from local fields.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/climate/indices"
SEASONS = ("DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ")
SOURCES = {
    "cpc-oni-v5.html": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v5/",
    "cpc-oni-v6.html": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v6/",
    "cpc-roni-v6.html": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/",
    "cpc-oni-baselines.html": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_change.shtml",
    "cpc-roni-notice.pdf": "https://www.weather.gov/media/notification/pdf_2026/pns26-05_Relative_ONI.pdf",
    "cpc-roni.txt": "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt",
    "cpc-dmi-v6.html": "https://www.cpc.ncep.noaa.gov/products/international/ocean_monitoring/IODMI/DMI_season.html",
    "cpc-dmi-v6.txt": "https://www.cpc.ncep.noaa.gov/products/international/ocean_monitoring/IODMI/mnth.ersstv6.clim19912020.dmi_season.txt",
    "psl-dmi-hadisst.txt": "https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.data",
    "psl-dmi-description.html": "https://psl.noaa.gov/data/timeseries/month/DMI/",
    "psl-dmi-method.ncl": "https://psl.noaa.gov/data/timeseries/month/DMI/dmi.ncl",
    "bom-iod-years.html": "https://www.bom.gov.au/climate/iod/content/years-iod-enso.html",
    "bom-2015.html": "https://www.bom.gov.au/climate/current/annual/aus/2015/",
    "bom-2016.html": "https://www.bom.gov.au/climate/current/annual/aus/2016/",
    "bom-2019.html": "https://www.bom.gov.au/climate/current/annual/aus/2019/",
    "bom-2022.html": "https://www.bom.gov.au/climate/current/annual/aus/2022/",
    "jamstec-2019.html": "https://www.jamstec.go.jp/e/about/press_release/20200406/",
}


def sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def acquire(directory: Path = RAW) -> dict:
    """Acquire once; subsequent calls verify cached bytes rather than refreshing."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "acquisition.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "schema_version": "p13-index-sources-v1", "files": [], "failures": []}
    for name, url in SOURCES.items():
        existing = next((x for x in manifest["files"] if x["name"] == name), None)
        target = directory / name
        if existing:
            if not target.is_file() or sha256(target.read_bytes()) != existing["sha256"]:
                raise ValueError(f"Pinned climate source checksum mismatch: {name}")
            continue
        started = datetime.now(timezone.utc).isoformat()
        try:
            request = Request(url, headers={"User-Agent": "DepthAtlas historical research"})
            with urlopen(request, timeout=40) as response:
                body = response.read(2_000_001)
                if len(body) > 2_000_000 or not body:
                    raise ValueError("Empty or oversized index response")
                item = {"name": name, "url": url, "resolved_url": response.url,
                        "retrieved_at": started, "sha256": sha256(body), "bytes": len(body),
                        "last_modified": response.headers.get("Last-Modified"),
                        "etag": response.headers.get("ETag"),
                        "content_type": response.headers.get("Content-Type")}
            if name.endswith(".html") and b"<html" not in body.lower() and b"<h2" not in body.lower():
                raise ValueError("Expected an HTML source document")
            target.write_bytes(body)
            manifest["files"].append(item)
            print(f"Acquired {name}: {len(body)} bytes", flush=True)
        except Exception as exc:
            manifest["failures"].append({"name": name, "url": url, "attempted_at": started,
                                          "error": str(exc)})
            print(f"Failed {name}: {exc}", flush=True)
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict]] = []
        self.row: list[dict] | None = None
        self.cell: dict | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            # HTML permits omitted closing TR tags. The CPC DMI page uses
            # that form before each repeated decade header.
            if self.row is not None:
                self.rows.append(self.row)
            self.row = []
        elif tag in ("th", "td") and self.row is not None:
            self.cell = {"text": "", "attributes": [dict(attrs)]}
        elif self.cell is not None:
            self.cell["attributes"].append(dict(attrs))

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"] += data

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.cell["text"] = " ".join(self.cell["text"].split())
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def parse_cpc_table(text: str, kind: str = "enso") -> list[dict]:
    """Keep source seasonal precision, blank cells, and provider styling."""
    if kind not in ("enso", "dmi"):
        raise ValueError("Unknown climate index kind")
    parser = _TableParser()
    parser.feed(text)
    result = []
    seen = set()
    partial_years = set()
    for row in parser.rows:
        if not row or not re.fullmatch(r"(?:19|20)\d\d", row[0]["text"]):
            continue
        if len(row) > 13 or len(row) < 2:
            raise ValueError("CPC climate table season count mismatch")
        year = int(row[0]["text"])
        if year in seen:
            raise ValueError(f"Duplicate climate table year: {year}")
        seen.add(year)
        if len(row) != 13:
            partial_years.add(year)
        cells = row[1:] + [{"text": "", "attributes": []}] * (13 - len(row))
        for index, cell in enumerate(cells):
            value = float(cell["text"]) if cell["text"] else None
            if value is not None and not math.isfinite(value):
                raise ValueError("Non-finite climate index")
            attrs = json.dumps(cell["attributes"]).lower()
            # Both legacy <font color> and current CSS class conventions are
            # retained as metadata; qualification is verified independently.
            phase = "unavailable" if value is None else "neutral"
            if any(x in attrs for x in ('"red"', '#ff0000', '"warm"', 'color:red', 'roni-warm', 'w3-text-red')):
                phase = "el_nino"
            elif any(x in attrs for x in ('"blue"', '#0000ff', '"cold"', 'color:blue', 'roni-cold', 'w3-text-blue')):
                phase = "la_nina"
            if kind == "dmi":
                phase = {"el_nino": "positive", "la_nina": "negative", "neutral": "within_threshold", "unavailable": "unavailable"}[phase]
            result.append({"year": year, "season": SEASONS[index],
                           "center_month": index + 1, "value_c": value,
                           "provider_phase": phase})
    if not result:
        raise ValueError("No twelve-season CPC table found")
    if partial_years - {max(seen)}:
        raise ValueError("An historical CPC year has missing season cells")
    for before, after in zip(sorted(seen), sorted(seen)[1:]):
        if after != before + 1:
            raise ValueError("Climate table year gap")
    return sorted(result, key=lambda item: (item["year"], item["center_month"]))


def qualify_enso(rows: list[dict]) -> list[dict]:
    """Qualify inclusive +/-0.5 C runs of five chronological seasons.

    This audits the published rounded table; official cell classification is
    retained separately and any disagreement must be reviewed, not hidden.
    """
    positions = [row["year"] * 12 + row["center_month"] for row in rows]
    if any(after <= before for before, after in zip(positions, positions[1:])):
        raise ValueError("ENSO seasons must be unique and chronological")
    result = [dict(row, calculated_phase="unavailable" if row["value_c"] is None else "neutral") for row in rows]
    start = 0
    while start < len(result):
        value = result[start]["value_c"]
        sign = 0 if value is None else (1 if value >= 0.5 else (-1 if value <= -0.5 else 0))
        stop = start + 1
        if sign:
            while stop < len(result):
                previous, current = result[stop - 1], result[stop]
                consecutive = (current["year"] * 12 + current["center_month"] == previous["year"] * 12 + previous["center_month"] + 1)
                if not consecutive or current["value_c"] is None or sign * current["value_c"] < 0.5:
                    break
                stop += 1
            if stop - start >= 5:
                for index in range(start, stop):
                    result[index]["calculated_phase"] = "el_nino" if sign == 1 else "la_nina"
        start = stop
    return result


def parse_psl_monthly(text: str) -> list[dict]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header = lines[0].split()
    if len(header) != 2 or not all(re.fullmatch(r"\d{4}", x) for x in header):
        raise ValueError("Missing PSL year-range header")
    start, end = map(int, header)
    years = end - start + 1
    if len(lines) < years + 2:
        raise ValueError("Truncated PSL climate table")
    missing = float(lines[years + 1])
    result = []
    for expected_year, line in zip(range(start, end + 1), lines[1:years + 1]):
        parts = line.split()
        if len(parts) != 13 or int(parts[0]) != expected_year:
            raise ValueError("PSL climate table year or month mismatch")
        for month, raw in enumerate(parts[1:], start=1):
            value = float(raw)
            if not math.isfinite(value):
                raise ValueError("Non-finite PSL climate value")
            result.append({"year": expected_year, "month": month,
                           "value_c": None if value == missing else value})
    return result


def season_dates(year: int, season: str) -> dict:
    """CPC's year belongs to the centre month, including cross-year DJF/NDJ."""
    if season not in SEASONS or not 1800 <= year <= 2200:
        raise ValueError("Unsupported season/year")
    month = SEASONS.index(season) + 1
    serial = year * 12 + month - 1
    pairs = [divmod(serial + offset, 12) for offset in (-1, 0, 1)]
    return {"season": season, "center_year": year, "center_month": month,
            "months": [f"{yr:04d}-{mon + 1:02d}" for yr, mon in pairs]}


def seasonal_monthly_context(rows: list[dict], year: int, season: str) -> dict:
    """Mean of three actual monthly indices, with no missing-month filling."""
    dates = season_dates(year, season)
    mapping = {(row["year"], row["month"]): row["value_c"] for row in rows}
    keys = [tuple(map(int, date.split("-"))) for date in dates["months"]]
    values = [mapping.get(key) for key in keys]
    total = 0.0
    for value in values:
        if value is None:
            return {**dates, "monthly_values_c": values, "mean_c": None}
        total = total + value
    return {**dates, "monthly_values_c": values, "mean_c": total / 3.0}


def parse_cpc_dmi_ascii(text: str) -> list[dict]:
    if "Climatology : 1991-2020" not in text or "ERSST.V6" not in text:
        raise ValueError("CPC DMI version or climatology changed")
    rows = []
    seen = set()
    for line in text.splitlines():
        parts = line.split()
        if not parts or not re.fullmatch(r"(?:19|20)\d\d", parts[0]):
            continue
        if len(parts) != 5 or parts[1] not in SEASONS:
            raise ValueError("Malformed CPC DMI text row")
        key = int(parts[0]), parts[1]
        if key in seen:
            raise ValueError("Duplicate CPC DMI season")
        seen.add(key)
        values = [None if value == "NaN" else float(value) for value in parts[2:]]
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("Invalid CPC DMI value")
        rows.append({"year": key[0], "season": key[1], "center_month": SEASONS.index(key[1]) + 1,
                     "wtio_c": values[0], "setio_c": values[1], "value_c": values[2]})
    if not rows:
        raise ValueError("Missing CPC DMI data")
    return rows


def qualifying_run(rows: list[dict], year: int, season: str) -> dict | None:
    selected = next((index for index, row in enumerate(rows) if row["year"] == year and row["season"] == season), None)
    if selected is None:
        raise ValueError("Season is outside source coverage")
    phase = rows[selected]["calculated_phase"]
    if phase not in ("el_nino", "la_nina"):
        return None
    begin, end = selected, selected
    def adjacent(first, second):
        return second["year"] * 12 + second["center_month"] == first["year"] * 12 + first["center_month"] + 1
    while begin > 0 and rows[begin - 1]["calculated_phase"] == phase and adjacent(rows[begin - 1], rows[begin]):
        begin -= 1
    while end + 1 < len(rows) and rows[end + 1]["calculated_phase"] == phase and adjacent(rows[end], rows[end + 1]):
        end += 1
    def identity(row):
        return {"year": row["year"], "season": row["season"], "value_c": row["value_c"]}
    return {"first": identity(rows[begin]), "last": identity(rows[end]),
            "season_count": end - begin + 1,
            "season_values": [identity(row) for row in rows[begin:end + 1]]}


def prepare(directory: Path = RAW, output: Path = ROOT / "casepacks/climate") -> dict:
    acquisition = json.loads((directory / "acquisition.json").read_text(encoding="utf-8"))
    sources = []
    for item in sorted(acquisition["files"], key=lambda item: item["name"]):
        body = (directory / item["name"]).read_bytes()
        if sha256(body) != item["sha256"]:
            raise ValueError(f"Pinned climate source checksum mismatch: {item['name']}")
        sources.append({"source_id": item["name"], **item})
    needed = set(SOURCES)
    if needed - {source["name"] for source in sources}:
        raise ValueError("Required climate source snapshots are missing")
    def read(name):
        return (directory / name).read_text(encoding="utf-8")
    tables = {key: qualify_enso(parse_cpc_table(read(f"cpc-{name}.html"))) for key, name in
              (("roni_v6", "roni-v6"), ("oni_v5", "oni-v5"), ("oni_v6", "oni-v6"))}
    for key, table in tables.items():
        disagreements = [row for row in table if row["provider_phase"] != row["calculated_phase"]]
        if disagreements:
            raise ValueError(f"Published {key} labels differ from run qualification: {disagreements[:3]}")
    dmi_table = parse_cpc_table(read("cpc-dmi-v6.html"), "dmi")
    dmi_text = parse_cpc_dmi_ascii(read("cpc-dmi-v6.txt"))
    by_index = {key: {(row["year"], row["season"]): row for row in table} for key, table in tables.items()}
    by_dmi = {(row["year"], row["season"]): row for row in dmi_table}
    by_dmi_text = {(row["year"], row["season"]): row for row in dmi_text}
    for key, row in by_dmi_text.items():
        if key not in by_dmi or by_dmi[key]["value_c"] != row["value_c"]:
            raise ValueError("CPC DMI HTML/text disagreement")
    definitions = {
        "roni_v6": {
            "name": "Relative Oceanic Nino Index", "provider": "NOAA Climate Prediction Center",
            "dataset": "ERSSTv6", "units": "degrees_Celsius", "baseline_period": [1991, 2020],
            "source_id": "cpc-roni-v6.html", "primary": True,
            "region": {"west": -170, "east": -120, "south": -5, "north": 5},
            "method": "Three-month mean Nino 3.4 SST anomaly minus the tropical (20S-20N) mean SST anomaly, rescaled to the original Nino 3.4 index variance.",
            "classification": "Provider historical episode labels; independently checked using inclusive +/-0.5 C thresholds for at least five consecutive overlapping three-month seasons in the published rounded table.",
            "threshold_c": 0.5, "minimum_consecutive_seasons": 5,
            "operational_since": "2026-02-01", "operational_notice_source_id": "cpc-roni-notice.pdf",
            "revision_policy": "Snapshot pinned; provider notes newest values may change for two months. Selected 2013, 2015 and 2022 rows are historical, not current provisional monitoring.",
            "interpretation": "An ENSO index does not by itself establish every coupled atmospheric feature or a local weather forecast."},
        "oni_v5": {
            "name": "Historical Oceanic Nino Index", "provider": "NOAA Climate Prediction Center",
            "dataset": "ERSSTv5", "units": "degrees_Celsius", "source_id": "cpc-oni-v5.html", "primary": False,
            "baseline_period": None, "baseline_policy": "Provider centered 30-year periods, revised every five years; use the exact pinned provider table, not a replacement fixed baseline.",
            "method": "Three-month Nino 3.4 SST anomaly; five overlapping seasons at inclusive +/-0.5 C for historical episodes.",
            "interpretation": "Legacy historical context, separately versioned; not the current operational index."},
        "oni_v6": {
            "name": "Oceanic Nino Index", "provider": "NOAA Climate Prediction Center",
            "dataset": "ERSSTv6", "units": "degrees_Celsius", "source_id": "cpc-oni-v6.html", "primary": False,
            "baseline_period": None, "baseline_policy": "Provider centered 30-year periods, revised every five years; use the exact pinned provider table.",
            "method": "Three-month Nino 3.4 SST anomaly; five overlapping seasons at inclusive +/-0.5 C for historical episodes.",
            "interpretation": "A separate index, not interchangeable with RONI or ONI ERSSTv5."},
        "dmi_cpc_v6": {
            "name": "Dipole Mode Index", "provider": "NOAA Climate Prediction Center International Desks",
            "dataset": "ERSSTv6", "units": "degrees_Celsius", "baseline_period": [1991, 2020],
            "source_id": "cpc-dmi-v6.txt", "display_table_source_id": "cpc-dmi-v6.html",
            "method": "Three-month western Indian Ocean SST anomaly minus southeastern Indian Ocean SST anomaly from the provider's seasonal text table.",
            "west_region": {"west": 50, "east": 70, "south": -10, "north": 10},
            "east_region": {"west": 90, "east": 110, "south": -10, "north": 0},
            "threshold_c": 0.4,
            "classification": "Numerical seasonal context only. Historical IOD episode labels are attributed separately to the Bureau of Meteorology statements; a seasonal value does not automatically reproduce that episode classification.",
            "metadata_note": "The downloadable series and its filename explicitly specify 1991-2020. The HTML page also has generic centered-30-year/10-year-update wording. This snapshot follows the specific downloadable series definition and retains both source documents.",
            "revision_policy": "Snapshot pinned; recent provider values may change for two months. No current provisional season is selected."},
    }
    events = []
    for year in (2013, 2015, 2022):
        primary = by_index["roni_v6"][(year, "SON")]
        iod = {
            "classification": "unassigned", "classification_basis": "No historical IOD episode label is assigned to the 2013 case. The numerical index remains visible.",
            "event_label_source_id": None, "seasonal_dmi_c": by_dmi[(year, "SON")]["value_c"],
            "index_id": "dmi_cpc_v6", "episode_timing_note": "No event interval assigned.",
        }
        if year == 2015:
            iod.update(classification="positive", event_label_source_id="bom-2015.html",
                       classification_basis="Positive IOD episode documented in the Bureau of Meteorology 2015 annual statement. This is separate from the CPC SON DMI of +0.39 C, which is below +0.4 C.",
                       episode_timing_note="The source describes late August to mid-November 2015; exact onset and end dates are not supplied here.")
        elif year == 2022:
            iod.update(classification="negative", event_label_source_id="bom-2022.html",
                       classification_basis="Negative IOD episode documented in the Bureau of Meteorology 2022 annual statement; the independently sourced CPC SON DMI is -0.48 C.",
                       episode_timing_note="The source describes strong negative conditions from July through September, weakening during austral spring and dissipating by late November 2022. Exact event dates are not assigned.")
        monthly = []
        for month in (9, 10, 11):
            season = SEASONS[month - 1]
            dmi_row = by_dmi_text[(year, season)]
            monthly.append({"month": month, "centered_season": season,
                            "season_months": season_dates(year, season)["months"],
                            **{f"{key}_c": mapping[(year, season)]["value_c"] for key, mapping in by_index.items()},
                            "cpc_dmi_v6_c": dmi_row["value_c"], "cpc_wtio_v6_c": dmi_row["wtio_c"], "cpc_setio_v6_c": dmi_row["setio_c"],
                            "interpretation": "This is a centered three-month index window, not the single month's SST anomaly."})
        events.append({"event_id": f"son-{year}", "year": year, "season": "SON", "months": [9, 10, 11],
                       "period": {"start": f"{year}-09-01", "end": f"{year}-11-30"},
                       "data_status": "historical_pinned_snapshot",
                       "enso": {"classification": primary["provider_phase"], "index_id": "roni_v6", "value_c": primary["value_c"],
                                "units": "degrees_Celsius", "qualifying_run": qualifying_run(tables["roni_v6"], year, "SON")},
                       "iod": iod, "monthly_context": monthly,
                       "legacy_enso_context": [{"index_id": key, "value_c": by_index[key][(year, "SON")]["value_c"],
                                                "classification": by_index[key][(year, "SON")]["provider_phase"]}
                                               for key in ("oni_v5", "oni_v6")]})
    snapshot = sha256(json.dumps([(s["name"], s["sha256"]) for s in sources], separators=(",", ":")).encode())
    result = {"schema_version": "p13-indices-v1", "primary_enso_index_id": "roni_v6",
              "snapshot_id": snapshot, "snapshot_retrieved_at": max(s["retrieved_at"] for s in sources),
              "sources": sources, "definitions": definitions, "events": events,
              "limits": ["Three selected seasons are historical examples, not a composite or a causal experiment.",
                         "ENSO and IOD use separate definitions and event evidence.",
                         "Index baselines differ from the ocean-field baseline and their anomaly magnitudes must not be equated."]}
    output.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()
    (output / "indices.json").write_bytes(body)
    manifest = {"schema_version": "p13-index-manifest-v1", "file": "indices.json", "sha256": sha256(body),
                "bytes": len(body), "snapshot_id": snapshot, "source_files": sources,
                "method": "p13-indices-v1", "event_ids": [event["event_id"] for event in events]}
    (output / "index-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    if args.acquire:
        result = acquire()
        print(json.dumps({"acquired": len(result["files"]), "failures": result["failures"]}, indent=2))
    if args.prepare:
        result = prepare()
        print(json.dumps({"snapshot_id": result["snapshot_id"], "events": result["events"]}, indent=2))

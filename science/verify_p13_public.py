"""Bounded P13 HTTP/source transport, exact replay and export acceptance.

No request retries automatically. Local expected outputs are deployment
consistency checks; independent source/scalar checks live in the test suite.
Every request and the whole run have explicit limits. Failed checks remain in
the evidence report, which is checkpointed after each completed check.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

from api.case_store import CaseStore
from api.climate_store import ClimateStore
from api.instrument_store import InstrumentStore
from science.climate_contracts import ClimateQuery, METHOD
from science.verify_p10_public import fingerprint, validate_bundle
from science.verify_p11_public import read_records
from science.verify_p12_public import check_csv

ROOT = Path(__file__).resolve().parents[1]
YEARS = (2013, 2015, 2022)


def exact(actual, expected, path="$", depth=0):
    """Strict value equality with a useful first-difference path, no epsilon."""
    assert depth < 60, "Unexpectedly deep comparison"
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and set(actual) == set(expected), f"{path}: keys differ"
        for key in expected:
            exact(actual[key], expected[key], f"{path}.{key}", depth + 1)
    elif isinstance(expected, (tuple, list)):
        assert isinstance(actual, list) and len(actual) == len(expected), f"{path}: sequence length differs"
        for i, (a, b) in enumerate(zip(actual, expected)):
            exact(a, b, f"{path}[{i}]", depth + 1)
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


def expected_csv(output):
    metadata = dict(method_version=METHOD, climate_manifest_sha256=output["climate_manifest_sha256"],
                    event_id=output["query"]["event_id"], reference_event_id=output["query"]["reference_event_id"],
                    period=output["query"]["period"], baseline_start_year=1991, baseline_end_year=2020)
    sections, profiles, difference, indices = [], [], [], []
    for panel in output["panels"]:
        for basin in ("pacific", "indian"):
            section = panel[basin]
            for z, depth in enumerate(section["depth_m"]):
                for x, longitude in enumerate(section["longitude"]):
                    i = z * section["shape"][1] + x
                    sections.append(dict(panel_event_id=panel["event"]["event_id"], case_id=panel["case_id"],
                        period_start_utc=panel["period_start"], period_end_exclusive_utc=panel["period_end_exclusive"],
                        basin=basin, longitude_deg_east_0_360=longitude, latitude_deg_north=section["latitude"],
                        depth_m=depth, potential_temperature_c=section["potential_temperature_c"][i],
                        baseline_potential_temperature_c=section["baseline_c"][i], anomaly_c=section["anomaly_c"][i]))
        p = panel["profile"]
        for z, depth in enumerate(p["depth_m"]):
            profiles.append(dict(panel_event_id=panel["event"]["event_id"], longitude_deg_east_0_360=p["longitude"],
                latitude_deg_north=p["latitude"], depth_m=depth, potential_temperature_c=p["potential_temperature_c"][z],
                baseline_potential_temperature_c=p["baseline_c"][z], anomaly_c=p["anomaly_c"][z]))
    for basin in ("pacific", "indian"):
        section = output["difference"][basin]
        for z, depth in enumerate(section["depth_m"]):
            for x, longitude in enumerate(section["longitude"]):
                difference.append(dict(basin=basin, longitude_deg_east_0_360=longitude,
                    latitude_deg_north=section["latitude"], depth_m=depth,
                    selected_minus_reference_c=section["values_c"][z * section["shape"][1] + x]))
    for event in output["events"]:
        for context in event["monthly_context"]:
            indices.append(dict(panel_event_id=event["event_id"], enso_classification=event["enso"]["classification"],
                enso_index_id=event["enso"]["index_id"], son_enso_index_c=event["enso"]["value_c"],
                iod_episode_label=event["iod"]["classification"], iod_label_basis=event["iod"]["classification_basis"],
                dmi_index_id=event["iod"]["index_id"], son_dmi_c=event["iod"]["seasonal_dmi_c"],
                center_month=context["month"], centered_three_month_season=context["centered_season"],
                **{key: context[key] for key in ("roni_v6_c", "oni_v5_c", "oni_v6_c", "cpc_dmi_v6_c")}))
    p = output["selected_point"]
    point = [dict(longitude_deg_east_0_360=p["longitude"], latitude_deg_north=p["latitude"], depth_m=p["depth_m"],
        selected_potential_temperature_c=p["selected"]["potential_temperature_c"],
        reference_potential_temperature_c=p["reference"]["potential_temperature_c"],
        selected_anomaly_c=p["selected"]["anomaly_c"], reference_anomaly_c=p["reference"]["anomaly_c"],
        selected_minus_reference_c=p["difference_c"])]
    return metadata, {"climate-sections.csv": sections, "climate-profiles.csv": profiles,
                      "climate-difference.csv": difference, "climate-index-context.csv": indices,
                      "climate-selected-point.csv": point}


def validate_archive(raw, saved, version):
    with ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        metadata, tables = expected_csv(saved["results"][0]["output"])
        assert set(tables) | {"investigation.json", "settings.json", "SOURCES.json", "report.html", "source-credits.txt", "README.txt"} <= set(names)
        result = json.loads(archive.read("investigation.json"))
        validate_bundle(result, version)
        exact(result["results"], saved["results"])
        exact(result["replay"], saved["replay"])
        exact(json.loads(archive.read("settings.json")), saved["replay"])
        exact(json.loads(archive.read("SOURCES.json")), saved["references"])
        html = archive.read("report.html").decode()
        assert "<script" not in html.lower() and "1991" in html and "2020" in html and "GODAS" in html
        assert "GODAS" in archive.read("source-credits.txt").decode()
        counts = {name: check_csv(archive.read(name), rows, metadata) for name, rows in tables.items()}
        return dict(files=names, csv_rows=counts, result_sha256=result["result_sha256"])


class Audit:
    def __init__(self, args):
        self.args, self.start = args, perf_counter()
        self.deadline = self.start + args.max_runtime_seconds
        self.report = dict(base_url=args.base_url.rstrip("/"), release=args.expected_version, method_version=METHOD,
            checked_at_utc=datetime.now(timezone.utc).isoformat(), method=__doc__, retries=0,
            timeout_seconds=args.timeout_seconds, max_runtime_seconds=args.max_runtime_seconds,
            checks=[], requests=[], complete=False)

    def save(self):
        r = self.report
        r["passed_checks"] = sum(item["passed"] for item in r["checks"])
        r["failed_checks"] = len(r["checks"]) - r["passed_checks"]
        r["passed"] = r["complete"] and not r["failed_checks"]
        r["request_count"] = len(r["requests"])
        r["elapsed_seconds"] = round(perf_counter() - self.start, 4)
        self.args.output.parent.mkdir(parents=True, exist_ok=True)
        self.args.output.write_text(json.dumps(r, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")

    def request(self, path, payload=None, status=200):
        remaining = self.deadline - perf_counter()
        assert remaining > 0, "Whole-run request budget exhausted"
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
        entry = dict(path=path, method="GET" if data is None else "POST", request_sha256=hashlib.sha256(data or b"").hexdigest())
        self.report["requests"].append(entry)
        began = perf_counter()
        try:
            req = Request(self.report["base_url"] + path, data=data, headers={"Content-Type": "application/json", "Accept-Encoding": "identity", "User-Agent": "OceanNavigator-P13-Verifier/1"})
            try:
                response = urlopen(req, timeout=min(self.args.timeout_seconds, remaining))
            except HTTPError as error:
                response = error
            with response:
                headers, actual_status = response.headers, response.status
                chunks, size = [], 0
                while True:
                    assert perf_counter() < self.deadline, "Whole-run budget exceeded while reading"
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    assert size <= 8 * 1024 * 1024, "Response exceeds 8 MiB acceptance bound"
                raw = b"".join(chunks)
            entry.update(status=actual_status, bytes=len(raw), seconds=round(perf_counter() - began, 4), response_sha256=hashlib.sha256(raw).hexdigest())
            assert actual_status == status, f"HTTP {actual_status}, expected {status}: {raw[:250]!r}"
            if path.startswith("/api/"):
                assert headers.get("X-Ocean-App-Version") == self.args.expected_version, "Incorrect API release"
                assert headers.get("Cache-Control") == "no-store", "Incorrect API cache policy"
            return raw, headers
        except Exception as error:
            entry.update(error=f"{type(error).__name__}: {str(error)[:500]}", seconds=round(perf_counter() - began, 4))
            raise

    def json(self, path, payload=None, status=200):
        return json.loads(self.request(path, payload, status)[0])

    def check(self, name, action):
        began = perf_counter()
        try:
            item = dict(name=name, passed=True, detail=action())
        except Exception as error:
            item = dict(name=name, passed=False, error=f"{type(error).__name__}: {str(error)[:900]}")
        item["seconds"] = round(perf_counter() - began, 4)
        self.report["checks"].append(item)
        self.save()
        print(("PASS " if item["passed"] else "FAIL ") + name + ("" if item["passed"] else ": " + item["error"]), flush=True)
        return item["passed"]

    def finish(self):
        self.report["complete"] = True
        self.save()
        print(json.dumps({key: self.report[key] for key in ("passed", "passed_checks", "failed_checks", "request_count", "elapsed_seconds")}))
        return 0 if self.report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", default="0.13.0")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--records-output", type=Path)
    parser.add_argument("--replay-records", type=Path)
    parser.add_argument("--replay-only", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=60)
    parser.add_argument("--max-runtime-seconds", type=float, default=900)
    args = parser.parse_args()
    if args.replay_only and not args.replay_records:
        parser.error("--replay-only requires eight P13 records via --replay-records")
    if not 1 <= args.timeout_seconds <= 120 or not 30 <= args.max_runtime_seconds <= 1800:
        parser.error("Request and whole-run budgets must be bounded")
    audit = Audit(args)
    cases, instruments = CaseStore(ROOT / "casepacks"), InstrumentStore(ROOT / "casepacks/instruments")
    climate, captures = ClimateStore(cases, instruments), []

    def health():
        result = audit.json("/api/health")
        assert result["status"] == "ok" and result["version"] == args.expected_version and result["case_count"] == 5
        return result
    audit.check("health, five real cases and release identity", health)

    def source_identity():
        result = climate.catalog()
        audit.report["source_identities"] = dict(climate_manifest_sha256=climate.manifest()[1],
            source_records=climate.manifest()[0]["sources"],
            models={f"pacific-godas-{year}-son": cases.require(f"pacific-godas-{year}-son")[1] for year in YEARS})
        assert result["baseline"]["strict_count"] == 30
        assert result["events"][1]["iod"]["seasonal_dmi_c"] == 0.39
        assert result["events"][1]["iod"]["classification"] == "positive"
        assert result["events"][1]["enso"]["value_c"] == 2.0
        return audit.report["source_identities"]
    if not audit.check("pinned field/index identity and separate IOD episode labels", source_identity):
        return audit.finish()

    def replay(saved):
        result = audit.json("/api/investigations/replay", saved["replay"])
        validate_bundle(result, args.expected_version)
        exact(result["results"], saved["results"])
        exact(result["replay"], saved["replay"])
        assert result["result_sha256"] == saved["result_sha256"]
        return dict(result_sha256=result["result_sha256"], mode=result["replay"]["recipe"]["mode"])

    def records(label, path, new=False):
        loaded = []
        def load():
            loaded.extend(read_records(path))
            assert loaded
            if new:
                assert len(loaded) == 8 and all(row["replay"]["recipe"]["mode"] == "climate" for row in loaded)
            identity = dict(label=label, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), count=len(loaded))
            audit.report.setdefault("replay_reference_files", []).append(identity)
            return identity
        if audit.check(label + ": reference records available", load):
            for i, saved in enumerate(loaded, 1):
                audit.check(f"{label} {i}: exact replay", lambda saved=saved: replay(saved))
                if new:
                    audit.check(f"{label} {i}: exact ZIP numerical evidence", lambda saved=saved: validate_archive(audit.request("/api/investigations/export", dict(replay=saved["replay"], format="zip"))[0], saved, args.expected_version))

    if args.replay_only:
        records("Separate process P13", args.replay_records, True)
        return audit.finish()

    def catalog():
        result = audit.json("/api/climate/catalog")
        exact(result, climate.catalog())
        return dict(events=[event["event_id"] for event in result["events"]], index_definitions=result["index_definitions"])
    audit.check("full climate catalogue and original source references", catalog)

    def analysis(query):
        result = audit.json("/api/climate/analyse", query.model_dump(mode="json"))
        exact(result, climate.analyse(query))
        return dict(query=query.model_dump(), result_sha256=fingerprint(result), selected_point=result["selected_point"])
    for year in YEARS:
        for period in ("SON", "09", "10", "11"):
            query = ClimateQuery(event_id=f"son-{year}", period=period)
            audit.check(f"SON {year} {period}: full numerical field, anomaly, difference and observations", lambda query=query: analysis(query))
        case_id = f"pacific-godas-{year}-son"
        def case(case_id=case_id):
            result = audit.json("/api/cases/" + case_id)
            exact(result, cases.require(case_id)[0].model_dump(mode="json"))
            assert result["coordinates"]["longitude"][39:41] == [179.5, 180.5]
            assert result["variables"][0]["standard_name"] == "sea_water_potential_temperature"
            return dict(case_id=case_id, source_kind=result["variables"][0]["standard_name"])
        audit.check(f"{case_id}: shared native case and dateline coordinates", case)
        for representation, operation, depth_index in (("display", "volume", None), ("analytical", "depth_slice", 10)):
            def subset(case_id=case_id, representation=representation, operation=operation, depth_index=depth_index):
                settings = dict(variable="temperature", time_index=1, representation=representation, operation=operation)
                if depth_index is not None:
                    settings["depth_index"] = depth_index
                actual = audit.json(f"/api/cases/{case_id}/subset?" + urlencode(settings))
                expected = cases.subset(case_id, "temperature", 1, representation, operation, depth_index, (None,) * 4).model_dump(mode="json")
                exact(actual, expected)
                return dict(shape=actual["shape"], missing_values=sum(value is None for value in actual["values"]))
            audit.check(f"{case_id}: exact {representation} {operation}", subset)
        def instruments_catalog(case_id=case_id):
            result = audit.json("/api/instruments?" + urlencode(dict(case_id=case_id)))
            exact(result, instruments.catalog(case_id))
            assert len(result["profiles"]) == 3
            return dict(profile_ids=[item["id"] for item in result["profiles"]])
        audit.check(f"{case_id}: three original Argo profile identities", instruments_catalog)
        for item in instruments.catalog(case_id)["profiles"]:
            def profile(item=item):
                result = audit.json("/api/instruments/profiles/" + item["id"])
                exact(result, instruments.read(item["id"]).model_dump(mode="json"))
                accepted = {key: sum(level["readings"][key]["accepted"] for level in result["levels"] if key in level["readings"]) for key in result["parameters"]}
                return dict(id=result["id"], source_sha256=result["source_sha256"], time=result["time"], accepted_by_parameter=accepted)
            audit.check(f"original observation {item['id']}: values, positions and original QC", profile)

    variants = [(2015, 2013, "SON", 70, 10), (2015, 2022, "SON", 39, 0),
                (2022, 2013, "09", 40, 27), (2022, 2015, "10", 139, 20),
                (2013, 2013, "11", 0, 0), (2013, 2022, "SON", 39, 27),
                (2015, 2013, "09", 40, 10), (2022, 2013, "11", 100, 18)]
    for number, (year, reference, period, longitude_index, depth_index) in enumerate(variants, 1):
        query = ClimateQuery(event_id=f"son-{year}", reference_event_id=f"son-{reference}", period=period,
                             longitude_index=longitude_index, depth_index=depth_index)
        case_id = f"pacific-godas-{year}-son"
        before = len(captures)
        def capture(query=query, case_id=case_id, number=number):
            recipe = dict(mode="climate", case_id=case_id, query=query.model_dump(mode="json"))
            result = audit.json("/api/investigations/capture", dict(title=f"P13 example {number} <script>", recipe=recipe,
                expected_model_sha256=cases.require(case_id)[1], expected_climate_manifest_sha256=climate.manifest()[1]))
            validate_bundle(result, args.expected_version)
            assert result["replay"]["sources"]["methods"]["climate"] == METHOD
            assert result["replay"]["sources"]["climate_manifest_sha256"] == climate.manifest()[1]
            assert [module["module"] for module in result["results"]] == ["climate_analysis"]
            exact(result["results"][0]["output"], climate.analyse(query))
            captures.append(result)
            return dict(query=query.model_dump(), result_sha256=result["result_sha256"])
        audit.check(f"capture {number}: applied climate settings and exact source identity", capture)
        if len(captures) == before:
            continue
        saved = captures[-1]
        audit.check(f"capture {number}: exact replay", lambda saved=saved: replay(saved))
        audit.check(f"capture {number}: all five numerical CSV tables in ZIP", lambda saved=saved: validate_archive(audit.request("/api/investigations/export", dict(replay=saved["replay"], format="zip"))[0], saved, args.expected_version))
        if number == 1:
            def direct_exports(saved=saved):
                raw, headers = audit.request("/api/investigations/export", dict(replay=saved["replay"], format="csv"))
                metadata, tables = expected_csv(saved["results"][0]["output"])
                count = check_csv(raw, tables["climate-sections.csv"], metadata)
                assert "climate-sections.csv" in headers.get("Content-Disposition", "")
                html = audit.request("/api/investigations/export", dict(replay=saved["replay"], format="html"))[0].decode()
                assert "&lt;script&gt;" in html and "<script" not in html.lower()
                return dict(csv_rows=count, escaped_report=True)
            audit.check("direct CSV and escaped HTML report", direct_exports)

    for label, filename in (("P08", "p08-local-records.json"), ("P10", "p10-v2-local-records.json"),
                            ("P11", "p11-v2-local-records.json"), ("P12", "p12-local-records.json")):
        records("Retained " + label, ROOT / "docs/evidence" / filename)
    if args.replay_records:
        records("Separate process P13", args.replay_records, True)
    for name, patch in (("event", {"event_id": "son-1997"}), ("month", {"period": "12"}),
                        ("depth", {"depth_index": 28}), ("longitude", {"longitude_index": 140}),
                        ("fractional longitude", {"longitude_index": 1.5}), ("Boolean depth", {"depth_index": True}),
                        ("forecast setting", {"forecast": True})):
        def guard(patch=patch):
            result = audit.json("/api/climate/analyse", {**ClimateQuery().model_dump(), **patch}, 422)
            assert result["error"]["code"] == "invalid_request"
            return result["error"]
        audit.check("reject unsupported " + name, guard)
    for suffix in ("subset?variable=salinity&depth_index=0", "subset?variable=eastward_velocity&depth_index=0",
                   "heat/catalog", "drift/context", "subset?representation=analytical&operation=volume",
                   "subset?depth_index=0&west=-179&south=0&east=-160&north=1"):
        def guard(suffix=suffix):
            # The established API deliberately distinguishes the resource
            # ceiling (413) from invalid scientific selections (422).
            status = 413 if "representation=analytical&operation=volume" in suffix else 422
            result = audit.json("/api/cases/pacific-godas-2015-son/" + suffix, status=status)
            assert result["error"]["code"] != "internal_error"
            return result["error"]
        audit.check("explain unsupported Pacific path " + suffix, guard)
    if captures:
        for kind in ("source", "climate_source", "method", "recipe", "result"):
            def mismatch(kind=kind):
                record = deepcopy(captures[0]["replay"])
                if kind == "source": record["sources"]["model_manifest_sha256"] = "0" * 64
                elif kind == "climate_source": record["sources"]["climate_manifest_sha256"] = "0" * 64
                elif kind == "method": record["sources"]["methods"]["climate"] = "p13-unrecognized"
                elif kind == "recipe": record["recipe"]["query"]["depth_index"] = 27
                else: record["expected_result_sha256"] = "0" * 64
                if kind in ("source", "climate_source", "method"):
                    record["expected_recipe_sha256"] = fingerprint(dict(recipe=record["recipe"], sources=record["sources"]))
                result = audit.json("/api/investigations/replay", record, 422)
                expected = ("source" if kind == "climate_source" else kind) + "_mismatch"
                assert result["error"]["code"] == expected
                return result["error"]
            audit.check("reject saved " + kind + " mismatch", mismatch)
    for path, tokens in (("/", ("Depth Atlas",)), ("/privacy", ("Privacy",)), ("/terms", ("Terms",)),
                         ("/favicon.svg", ("<svg",)), ("/third-party-notices.txt", ("GODAS", "Argo", "OISST"))):
        def document(path=path, tokens=tokens):
            raw, headers = audit.request(path)
            assert all(token in raw.decode() for token in tokens)
            return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), content_type=headers.get("Content-Type"))
        audit.check("public document " + path, document)
    if args.records_output:
        args.records_output.parent.mkdir(parents=True, exist_ok=True)
        args.records_output.write_text(json.dumps(dict(schema_version="p13-verification-records-v1", base_url=audit.report["base_url"], release=args.expected_version, records=captures), ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")
        audit.report["records_written"] = dict(path=str(args.records_output), count=len(captures), sha256=hashlib.sha256(args.records_output.read_bytes()).hexdigest())
    return audit.finish()


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only P05 HTTP audit of a deployed release against checked local sources.

Run after deployment, never as a deployment command:
    python science/verify_p05_public.py

OCEAN_TEST_URL selects the target (default: the linked public Vercel project).
OCEAN_HTTP_REPORT selects a JSON output path, absolute or relative to this repo.
The default report is docs/evidence/p05-public-http.json. All HTTP requests are
GETs. Failed checks are retained, independent checks continue, and the final
report is written even when verification fails. No automatic retry hides a
first-request failure. Exit status is nonzero if any request or assertion fails.

Vercel excludes browser test sources during its Linux build. The only reviewed
CSS difference for this release is the absent, unused `.table{display:table}`
utility generated locally from getByRole('table') in web/e2e/case.spec.ts.
Asset filename hashes and HTML CRLF/LF are normalized; JavaScript code otherwise
must match exactly. CSS permits only that one exact reviewed rule omission.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote, urlencode, urlsplit

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.case_store import CASE_ID, CaseStore
from api.evidence_store import EvidenceStore
from api.instrument_store import InstrumentStore
from science.evidence_contracts import MatchSettings


RELEASE = "0.5.0"
MODEL_SHA256 = "9598b33dc9eef89cb909f2811e1590ca580a143c1dbcc25d97e51a84faf7d28d"
BASE = os.getenv("OCEAN_TEST_URL", "https://depth-atlas-seifuku.vercel.app").rstrip("/")
REPORT = Path(os.getenv("OCEAN_HTTP_REPORT", "docs/evidence/p05-public-http.json"))
if not REPORT.is_absolute():
    REPORT = ROOT / REPORT


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_asset_references(value: str) -> str:
    return re.sub(r"((?:workspace|scene|legal)-)[A-Za-z0-9_-]+(\.(?:js|css))", r"\1BUILDHASH\2", value)


def normalize_html(value: bytes) -> str:
    return normalize_asset_references(value.decode("utf-8")).replace("\r\n", "\n")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def same(actual, expected, path="response") -> None:
    """Exact structure/strings, tightly bounded cross-platform float rounding."""
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and actual.keys() == expected.keys(), f"{path}: object keys differ")
        for key, value in expected.items():
            same(actual[key], value, f"{path}.{key}")
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), f"{path}: array length differs")
        for index, value in enumerate(expected):
            same(actual[index], value, f"{path}[{index}]")
    elif isinstance(expected, bool) or expected is None or isinstance(expected, str):
        require(type(actual) is type(expected) and actual == expected, f"{path}: value differs")
    elif isinstance(expected, int):
        require(not isinstance(actual, bool) and actual == expected, f"{path}: integer differs")
    elif isinstance(expected, float):
        require(isinstance(actual, (int, float)) and math.isfinite(actual)
                and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-9),
                f"{path}: numeric value differs ({actual!r} versus {expected!r})")
    else:
        require(actual == expected, f"{path}: unsupported reference type differs")


def comparison_accounting(body: dict) -> None:
    accepted = [row for row in body["rows"] if row["accepted"]]
    excluded = [row for row in body["rows"] if not row["accepted"]]
    require(len(accepted) == body["matched_count"] == body["metrics"]["count"], "Comparison accepted counts disagree")
    require(len(excluded) == body["excluded_count"], "Comparison excluded counts disagree")
    require(len(body["rows"]) == body["total_samples"] == len(accepted) + len(excluded), "Comparison total disagrees")
    require(dict(Counter(row["reason"] for row in excluded)) == body["exclusion_counts"], "Exclusion reasons disagree")
    require(all(row["model"] is None and row["residual"] is None for row in excluded), "Excluded sample has a comparison value")
    require(all(row["reason"] == "accepted" and row["model"] is not None and row["residual"] is not None for row in accepted), "Accepted sample lacks a comparison value")
    if not accepted:
        require(all(body["metrics"][name] is None for name in ("bias", "rmse", "mae", "maximum_abs_residual")), "Empty comparison has a fabricated metric")


class Audit:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "Ocean-Navigator-P05-read-only-verification/0.5.0"
        self.started = time.perf_counter()
        self.report = {"checked_utc": datetime.now(timezone.utc).isoformat(), "base": BASE,
                       "release": RELEASE, "status": "running", "http_method_policy": "GET only",
                       "automatic_retries": 0, "requests": [], "checks": [], "failures": [],
                       "independent_metrics": [], "coverage_scenarios": [], "asset_verification": []}

    def get(self, path: str, status=200):
        started = time.perf_counter()
        record = {"path": path, "method": "GET", "expected_status": status}
        self.report["requests"].append(record)
        try:
            response = self.session.get(BASE + path, timeout=(15, 45), allow_redirects=False)
            record.update(status=response.status_code, seconds=round(time.perf_counter() - started, 6),
                          decoded_bytes=len(response.content), sha256=digest(response.content),
                          version=response.headers.get("X-Ocean-App-Version"),
                          cache_control=response.headers.get("Cache-Control"))
            require(response.status_code == status, f"{path}: HTTP {response.status_code}, expected {status}")
            if path.startswith("/api/"):
                require(response.headers.get("X-Ocean-App-Version") == RELEASE, f"{path}: release header mismatch")
                require(response.headers.get("Cache-Control") == "no-store", f"{path}: API cache policy mismatch")
            record["status_check"] = "passed"
            return response
        except Exception as error:
            record.update(status_check="failed", seconds=round(time.perf_counter() - started, 6),
                          error=f"{type(error).__name__}: {error}")
            raise

    def check(self, name, operation):
        started = time.perf_counter()
        record = {"name": name}
        self.report["checks"].append(record)
        try:
            detail = operation()
            record["status"] = "passed"
            if detail is not None:
                record["detail"] = detail
        except Exception as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
            self.report["failures"].append({"check": name, "error": record["error"]})
        finally:
            record["seconds"] = round(time.perf_counter() - started, 6)
            print(json.dumps({"check": name, "status": record["status"], "seconds": record["seconds"]}), flush=True)

    def finish(self):
        self.report["status"] = "failed" if self.report["failures"] else "passed"
        self.report["elapsed_seconds"] = round(time.perf_counter() - self.started, 6)
        self.report["passed_checks"] = sum(row["status"] == "passed" for row in self.report["checks"])
        self.report["failed_checks"] = len(self.report["failures"])
        self.report["request_count"] = len(self.report["requests"])
        self.session.close()
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(self.report, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": self.report["status"], "passed_checks": self.report["passed_checks"],
                          "failed_checks": self.report["failed_checks"], "requests": self.report["request_count"],
                          "report": str(REPORT), "seconds": self.report["elapsed_seconds"]}), flush=True)


def main() -> int:
    audit = Audit()
    try:
        parsed = urlsplit(BASE)
        require(parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not parsed.query and not parsed.fragment,
                "OCEAN_TEST_URL must be an HTTP(S) origin, without a query or fragment")
        require(not parsed.username and not parsed.password, "Target URL must not contain credentials")
        cases = CaseStore(ROOT / "casepacks")
        instruments = InstrumentStore(ROOT / "casepacks/instruments")
        evidence = EvidenceStore(cases, instruments)
        index = instruments.index()
        fixture = json.loads((ROOT / "tests/fixtures/p05-source-reference.json").read_text(encoding="utf-8"))
        references = {profile["profile_id"]: profile for profile in fixture["profiles"]}
        manifest_path = ROOT / "casepacks" / CASE_ID / "manifest.json"
        index_path = ROOT / "casepacks/instruments/index.json"
        original_hashes = {str(path): digest(path.read_bytes()) for path in (manifest_path, index_path)}
        require(original_hashes[str(manifest_path)] == MODEL_SHA256, "Pinned model manifest changed")
        require(len(index["profiles"]) == 13, "Expected the checked 13-profile P04/P05 observation library")
        audit.report.update(model_manifest_sha256=MODEL_SHA256, observation_library_sha256=evidence.library_sha,
                            library_profiles=13, reference_fixture_sha256=digest((ROOT / "tests/fixtures/p05-source-reference.json").read_bytes()))

        verified_assets = {}

        def verify_asset(path):
            if path in verified_assets:
                return verified_assets[path]
            filename = path.rsplit("/", 1)[-1]
            match = re.fullmatch(r"(workspace|scene|legal)-[A-Za-z0-9_-]+\.(js|css)", filename)
            require(bool(match), f"Unreviewed asset type: {path}")
            stem, extension = match.groups()
            candidates = list((ROOT / "web/dist/assets").glob(f"{stem}-*.{extension}"))
            require(len(candidates) == 1, f"Local reference asset is ambiguous: {path}")
            local_path = candidates[0]
            local_body = local_path.read_bytes()
            public_body = audit.get(path).content
            detail = {"public_path": path, "local_path": local_path.relative_to(ROOT).as_posix(),
                      "public_bytes": len(public_body), "local_bytes": len(local_body),
                      "public_sha256": digest(public_body), "local_sha256": digest(local_body)}
            if extension == "js":
                public_code = normalize_asset_references(public_body.decode("utf-8"))
                local_code = normalize_asset_references(local_body.decode("utf-8"))
                require(public_code == local_code, f"JavaScript differs beyond generated asset references: {path}")
                detail.update(comparison="Exact JavaScript after generated workspace/scene/legal filename hash normalization only",
                              normalized_sha256=digest(public_code.encode("utf-8")))
            elif public_body == local_body:
                detail["comparison"] = "Exact CSS bytes"
            else:
                rule = b".table{display:table}"
                require(local_body.count(rule) == 1 and public_body == local_body.replace(rule, b"", 1),
                        f"CSS differs beyond the one reviewed unused test-source utility: {path}")
                detail.update(comparison="Exact CSS after one reviewed unused utility omission",
                              local_only_rule=rule.decode(), omitted_bytes=len(rule),
                              source="Tailwind scanner identifies table at offset 1184 in web/e2e/case.spec.ts getByRole('table'); .vercelignore excludes web/e2e. Production JSX table elements do not yield this utility candidate.")
            audit.report["asset_verification"].append(detail)
            verified_assets[path] = public_body
            return public_body

        def home_assets():
            response = audit.get("/")
            require("Depth Atlas" in response.text, "Home page title missing")
            require(normalize_html(response.content) == normalize_html((ROOT / "web/dist/index.html").read_bytes()),
                    "Public home differs beyond generated asset references and CRLF/LF")
            paths = sorted(set(re.findall(r'(?:src|href)=["\'](/assets/[^"\']+)["\']', response.text)))
            require(any(path.endswith(".js") for path in paths), "Home has no application script")
            require(any(path.endswith(".css") for path in paths), "Home has no application stylesheet")
            dynamic = set()
            for path in paths:
                body = verify_asset(path)
                if path.endswith(".js"):
                    require(RELEASE.encode() in body, "Application bundle has the wrong release")
                    require(b"Evidence" in body, "Application bundle lacks the evidence workspace")
                    dynamic.update("/assets/" + name.decode() for name in re.findall(rb"scene-[A-Za-z0-9_-]+\.js", body))
            require(bool(dynamic), "No scientific scene chunk was referenced by the main application")
            for path in sorted(dynamic):
                verify_asset(path)
            return {"entry_assets": paths, "scene_assets": sorted(dynamic)}

        audit.check("anonymous_home_and_verified_build_assets", home_assets)

        def health():
            body = audit.get("/api/health").json()
            require(body["version"] == RELEASE and body["status"] == "ok", "Health/version mismatch")
            require(body["case_count"] == 1 and body["data_status"] == "historical_case_ready", "Historical case readiness mismatch")
            return {"version": body["version"], "data_status": body["data_status"]}

        audit.check("health_release_and_historical_readiness", health)
        audit.check("unchanged_model_manifest", lambda: same(audit.get(f"/api/cases/{CASE_ID}").json(), json.loads(manifest_path.read_bytes())))

        def catalogue():
            body = audit.get("/api/catalog").json()
            require(len(body["cases"]) == 1 and body["cases"][0]["id"] == CASE_ID, "Model coverage changed or is missing")
            same(audit.get("/api/instruments").json(), instruments.catalog())
            return {"model_cases": 1, "observation_profiles": 13}

        audit.check("model_and_instrument_catalogues", catalogue)

        static_files = {"/privacy": "privacy.html", "/terms": "terms.html", "/favicon.svg": "favicon.svg",
                        "/third-party-notices.txt": "third-party-notices.txt", "/observation-import-guide.txt": "observation-import-guide.txt",
                        "/licenses/GSW.txt": "licenses/GSW.txt", "/licenses/netCDF4.txt": "licenses/netCDF4.txt",
                        "/licenses/NumPy.txt": "licenses/NumPy.txt", "/licenses/cftime.txt": "licenses/cftime.txt"}
        for path, relative in static_files.items():
            def verify_static(path=path, relative=relative):
                public_body = audit.get(path).content
                local_body = (ROOT / "web/dist" / relative).read_bytes()
                if relative.endswith(".html"):
                    require(normalize_html(public_body) == normalize_html(local_body),
                            f"HTML differs beyond generated asset references and CRLF/LF: {path}")
                    for asset in set(re.findall(r'(?:src|href)=["\'](/assets/[^"\']+)["\']', public_body.decode("utf-8"))):
                        verify_asset(asset)
                else:
                    require(public_body == local_body, f"Static file differs: {path}")
            audit.check("static:" + path, verify_static)

        default = MatchSettings()
        for variable in ("temperature", "salinity"):
            settings = default.model_copy(update={"variable": variable})
            for entry in index["profiles"]:
                identifier = entry["id"]

                def verify_comparison(identifier=identifier, settings=settings, variable=variable):
                    path = f"/api/cases/{CASE_ID}/evidence/profiles/{quote(identifier, safe='')}?" + urlencode(settings.model_dump())
                    body = audit.get(path).json()
                    local = evidence.comparison(CASE_ID, identifier, settings).model_dump(mode="json")
                    same(body, local)
                    comparison_accounting(body)
                    reference = references.get(identifier)
                    if reference:
                        scenario = next(s for s in fixture["count_scenarios"] if s["time_index"] == 1 and s["max_time_hours"] == 6
                                        and s["max_distance_km"] == 5 and s["max_vertical_gap_m"] == 500 and s["qc"] == ["1", "2"])
                        position = fixture["profile_order"].index(reference["platform"])
                        expected_count = scenario["review_gated_counts"][variable][position]
                        require(body["matched_count"] == expected_count, "Independent source count mismatch")
                        if expected_count:
                            source = reference["snapshots"]["1"]["columns"][variable]
                            residuals = [value for value in source["model_minus_observation"] if value is not None]
                            require(len(residuals) == expected_count, "Independent default source metric denominator mismatch")
                            expected_metrics = {"count": len(residuals), "bias": math.fsum(residuals) / len(residuals),
                                                "rmse": math.sqrt(math.fsum(r * r for r in residuals) / len(residuals)),
                                                "mae": math.fsum(abs(r) for r in residuals) / len(residuals),
                                                "maximum_abs_residual": max(abs(r) for r in residuals)}
                            same(body["metrics"], expected_metrics, "independent_metrics")
                            for row in body["rows"]:
                                i = row["sample_index"]
                                same(row["model"], source["model_at_observation_depth"][i], f"independent_model[{i}]")
                                same(row["residual"], source["model_minus_observation"][i], f"independent_residual[{i}]")
                            audit.report["independent_metrics"].append({"profile": identifier, "variable": variable, "metrics": expected_metrics})
                    return {"profile": identifier, "variable": variable, "matched_count": body["matched_count"],
                            "excluded_count": body["excluded_count"], "exclusion_counts": body["exclusion_counts"]}

                audit.check(f"comparison:{variable}:{identifier}", verify_comparison)

        scenarios = [("default", {}, 206), ("two_hour_window", {"time_window_hours": 2}, 0),
                     ("100m_bracket", {"max_vertical_gap_m": 100}, 124), ("25m_bracket", {"max_vertical_gap_m": 25}, 50),
                     ("jan8_noon", {"time_index": 3}, 103), ("jan9_noon", {"time_index": 5}, 307)]
        for variable in ("temperature", "salinity"):
            for name, overrides, expected_count in scenarios:

                def verify_coverage(name=name, overrides=overrides, expected_count=expected_count, variable=variable):
                    settings = MatchSettings(variable=variable, **overrides)
                    path = f"/api/cases/{CASE_ID}/evidence/coverage?" + urlencode(settings.model_dump())
                    body = audit.get(path).json()
                    same(body, evidence.coverage(CASE_ID, settings).model_dump(mode="json"))
                    require(body["total_profiles"] == 13 and body["total_samples"] == 5318, "Coverage denominator mismatch")
                    require(body["matched_samples"] == expected_count, "Independent coverage count mismatch")
                    require(sum(p["matched_count"] for p in body["profiles"]) == expected_count, "Coverage profile sum mismatch")
                    require(body["matched_samples"] + body["excluded_samples"] == body["total_samples"], "Coverage sample accounting mismatch")
                    require(sum(body["exclusion_counts"].values()) == body["excluded_samples"], "Coverage exclusion accounting mismatch")
                    require(all(len(p["eligible_depths_m"]) == p["matched_count"] == p["metrics"]["count"] for p in body["profiles"]), "Coverage depth/metric counts disagree")
                    if expected_count == 0:
                        require(all(p["metrics"]["rmse"] is None and not p["eligible_depths_m"] for p in body["profiles"]), "Empty coverage invents a score or depths")
                    detail = {"scenario": name, "variable": variable, "matched_samples": expected_count,
                              "matched_profiles": body["matched_profiles"], "model_time": body["model_time"], "settings": settings.model_dump()}
                    audit.report["coverage_scenarios"].append(detail)
                    return detail

                audit.check(f"coverage:{variable}:{name}", verify_coverage)

        def source_review():
            identifier = next(p["id"] for p in index["profiles"] if p["platform"] == "5907083")
            body = audit.get("/api/instruments/profiles/" + quote(identifier, safe="")).json()
            same(body, instruments.read(identifier).model_dump(mode="json"))
            require(any("verification run" in warning.lower() for warning in body["warnings"]), "Source-review warning missing")
            require("Headless verification run - no calibration comments entered." in json.dumps(body["metadata"]), "Full original calibration text missing")
            require(all(level["readings"]["salinity"]["qc"] == "1" for level in body["levels"]), "Source QC was changed by the review hold")
            return {"profile": identifier, "source_sha256": body["source_sha256"], "held_samples": len(body["levels"]), "original_qc_unchanged": True}

        audit.check("original_source_warning_and_unchanged_qc", source_review)

        invalid = [(f"/api/cases/{CASE_ID}/evidence/profiles/no-such-id", 404, "profile_not_found"),
                   ("/api/cases/unavailable/evidence/coverage", 404, "case_not_found")]
        for key, value in [("variable", "oxygen"), ("time_index", -1), ("time_index", 7),
                           ("time_window_hours", -1), ("time_window_hours", 73), ("time_window_hours", "nan"),
                           ("distance_km", 51), ("distance_km", "inf"), ("max_vertical_gap_m", 0),
                           ("max_vertical_gap_m", 1001), ("qc", "accept_everything")]:
            invalid.append((f"/api/cases/{CASE_ID}/evidence/coverage?" + urlencode({key: value}), 422, "invalid_request"))
        for path, status, code in invalid:
            def verify_error(path=path, status=status, code=code):
                response = audit.get(path, status=status)
                body = response.json()
                require(body["error"]["code"] == code, "Error code mismatch")
                require(body["error"]["request_id"] == response.headers.get("X-Request-ID"), "Error request identity mismatch")
            audit.check("error:" + path, verify_error)

        def unchanged_local_sources():
            require(all(digest(Path(path).read_bytes()) == before for path, before in original_hashes.items()), "Local source bundle changed during read-only audit")
            return {"model_manifest_unchanged": True, "observation_index_unchanged": True}

        audit.check("read_only_source_identity", unchanged_local_sources)
    except Exception as error:
        audit.report["failures"].append({"check": "audit_setup_or_unhandled_error", "error": f"{type(error).__name__}: {error}"})
    finally:
        audit.finish()
    return 1 if audit.report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

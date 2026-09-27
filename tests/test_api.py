"""Integration checks for truthful status, failure contracts and production assets."""

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from api.version import APP_VERSION


def test_liveness_does_not_claim_data_readiness(tmp_path: Path):
    with TestClient(create_app(tmp_path, case_root=tmp_path / "empty-cases")) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["data_status"] == "not_configured"
        assert response.json()["case_count"] == 0
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-ocean-app-version"] == response.json()["version"] == APP_VERSION


def test_catalog_contains_only_planned_regions(tmp_path: Path):
    with TestClient(create_app(tmp_path, case_root=tmp_path / "empty-cases")) as client:
        payload = client.get("/api/catalog").json()
        assert payload["cases"] == []
        assert payload["data_status"] == "not_configured"
        assert {region["id"] for region in payload["regions"]} == {"bay-of-bengal", "arabian-sea", "tropical-pacific"}
        assert all(region["status"] == "planned" for region in payload["regions"])
        pacific = next(region for region in payload["regions"] if region["id"] == "tropical-pacific")
        assert pacific["viewport_bounds"][0] > pacific["viewport_bounds"][2]  # crosses the dateline


def test_unknown_api_and_missing_frontend_have_error_envelopes(tmp_path: Path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/api/nonexistent")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
        assert response.headers["x-ocean-app-version"] == APP_VERSION
        assert client.get("/").status_code == 503


def test_production_frontend_and_asset_serving(tmp_path: Path):
    (tmp_path / "index.html").write_text("<!doctype html><title>test frontend</title>", encoding="utf-8")
    (tmp_path / "privacy.html").write_text("<!doctype html><h1>Privacy Policy</h1>", encoding="utf-8")
    (tmp_path / "terms.html").write_text("<!doctype html><h1>Terms &amp; Conditions</h1>", encoding="utf-8")
    (tmp_path / "about.html").write_text("<!doctype html><h1>About Us</h1>", encoding="utf-8")
    (tmp_path / "startup-recovery.js").write_text("/* startup recovery */", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "sample.js").write_text("console.log('asset');", encoding="utf-8")
    with TestClient(create_app(tmp_path)) as client:
        document = client.get("/")
        assert document.headers["content-type"].startswith("text/html")
        assert document.headers["cache-control"] == "no-store"
        for path in ("/startup-recovery.js", "/assets/workspace-fwVeVJXC.js"):
            bridge = client.get(path)
            assert bridge.status_code == 200
            assert bridge.headers["content-type"].startswith("text/javascript")
            assert bridge.headers["cache-control"] == "no-store"
            assert bridge.text == "/* startup recovery */"
        for path, text in [("/privacy", "Privacy Policy"), ("/privacy/", "Privacy Policy"), ("/terms", "Terms &amp; Conditions"), ("/terms/", "Terms &amp; Conditions"), ("/about", "About Us"), ("/about/", "About Us")]:
            page = client.get(path)
            assert page.status_code == 200
            assert text in page.text
        asset = client.get("/assets/sample.js")
        assert asset.status_code == 200
        assert "immutable" in asset.headers["cache-control"]
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/api/health").json()["status"] == "ok"


def test_unhandled_failure_does_not_expose_internal_details(tmp_path: Path):
    application = create_app(tmp_path)

    @application.get("/api/test-failure")
    def fail():
        raise ValueError("private internal details")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/test-failure")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "private internal details" not in response.text

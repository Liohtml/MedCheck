from fastapi.testclient import TestClient

from medcheck.core.config import Settings
from medcheck.web.app import create_app


def test_app_homepage():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "MedCheck" in resp.text


def test_app_health():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_analyze_open_when_no_api_key_configured():
    # Back-compat: no MEDCHECK_API_KEY -> endpoint stays open (localhost default).
    client = TestClient(create_app(Settings(api_key=None)))
    resp = client.post("/api/analyze")
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_implemented"


def test_analyze_requires_key_when_configured():
    client = TestClient(create_app(Settings(api_key="s3cret")))
    # Missing key.
    assert client.post("/api/analyze").status_code == 401
    # Wrong key.
    assert client.post("/api/analyze", headers={"X-API-Key": "nope"}).status_code == 401
    # Correct key.
    ok = client.post("/api/analyze", headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "not_implemented"


def test_health_open_even_with_api_key():
    # Health check stays public for liveness probes.
    client = TestClient(create_app(Settings(api_key="s3cret")))
    assert client.get("/health").status_code == 200


def test_default_host_is_localhost(monkeypatch):
    monkeypatch.delenv("MEDCHECK_HOST", raising=False)
    assert Settings().host == "127.0.0.1"

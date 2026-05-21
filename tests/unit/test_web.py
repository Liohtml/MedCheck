from fastapi.testclient import TestClient

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

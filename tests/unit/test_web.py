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


_VALID_BODY = {"source": "/data/scans"}


def test_analyze_open_when_no_api_key_configured():
    # Back-compat: no MEDCHECK_API_KEY -> endpoint stays open (localhost default).
    # The pipeline is not wired up yet, so it must report 501 (not a 200 "success").
    client = TestClient(create_app(Settings(api_key=None)))
    resp = client.post("/api/analyze", json=_VALID_BODY)
    assert resp.status_code == 501
    assert "not implemented" in resp.json()["detail"].lower()


def test_analyze_requires_key_when_configured():
    client = TestClient(create_app(Settings(api_key="s3cret")))
    # Missing key.
    assert client.post("/api/analyze", json=_VALID_BODY).status_code == 401
    # Wrong key.
    assert client.post("/api/analyze", json=_VALID_BODY, headers={"X-API-Key": "nope"}).status_code == 401
    # Correct key -> auth passes, endpoint reports the stub as 501 (not yet implemented).
    ok = client.post("/api/analyze", json=_VALID_BODY, headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 501


def test_analyze_validates_request_body():
    client = TestClient(create_app(Settings(api_key=None)))
    # Missing required 'source'.
    assert client.post("/api/analyze", json={}).status_code == 422
    # Invalid report_format.
    assert client.post("/api/analyze", json={"source": "x", "report_format": "docx"}).status_code == 422
    # Unsupported language is rejected.
    assert client.post("/api/analyze", json={"source": "x", "language": "klingon"}).status_code == 422


def test_analyze_accepts_all_supported_languages():
    # Web schema must accept the same locales the CLI and i18n catalogs support;
    # a valid fr/es body should reach the (501) stub, not be rejected with 422.
    client = TestClient(create_app(Settings(api_key=None)))
    for lang in ("en", "de", "fr", "es"):
        resp = client.post("/api/analyze", json={"source": "x", "language": lang})
        assert resp.status_code == 501, lang


def test_health_open_even_with_api_key():
    # Health check stays public for liveness probes.
    client = TestClient(create_app(Settings(api_key="s3cret")))
    assert client.get("/health").status_code == 200


def test_default_host_is_localhost(monkeypatch):
    monkeypatch.delenv("MEDCHECK_HOST", raising=False)
    assert Settings().host == "127.0.0.1"


def test_htmx_is_vendored_locally():
    # #37: htmx must be served locally, not from a third-party CDN.
    client = TestClient(create_app())
    resp = client.get("/static/htmx.min.js")
    assert resp.status_code == 200
    page = client.get("/").text
    assert "/static/htmx.min.js" in page
    assert 'integrity="sha384-' in page
    assert 'crossorigin="anonymous"' in page
    assert "unpkg.com" not in page


# --- Security headers (issue #109) ---

_EXPECTED_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none';"
    ),
}


def test_security_headers_on_health():
    """Every response must carry standard security headers."""
    client = TestClient(create_app())
    resp = client.get("/health")
    for header, expected in _EXPECTED_SECURITY_HEADERS.items():
        assert resp.headers.get(header) == expected, f"Missing or wrong {header}"


def test_security_headers_on_homepage():
    client = TestClient(create_app())
    resp = client.get("/")
    for header, expected in _EXPECTED_SECURITY_HEADERS.items():
        assert resp.headers.get(header) == expected, f"Missing or wrong {header}"


def test_content_security_policy_frame_ancestors():
    """CSP must include frame-ancestors to match X-Frame-Options DENY."""
    client = TestClient(create_app())
    resp = client.get("/health")
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in csp


# --- CSP hardening (issue #120) ---


def test_no_inline_scripts_in_index():
    """script-src excludes 'unsafe-inline', so index.html must not use inline JS."""
    client = TestClient(create_app())
    page = client.get("/").text
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split("style-src")[0]
    for attr in ("onclick=", "onchange=", "ondrop=", "ondragover=", "ondragleave="):
        assert attr not in page
    assert "<script>" not in page  # only src=... script tags allowed
    assert "/static/app.js" in page
    assert client.get("/static/app.js").status_code == 200


# --- CSRF origin check (issue #100) ---


def test_analyze_rejects_cross_origin_post():
    client = TestClient(create_app(Settings(api_key=None)))
    resp = client.post(
        "/api/analyze",
        json=_VALID_BODY,
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403


def test_analyze_allows_same_origin_post():
    client = TestClient(create_app(Settings(api_key=None)))
    resp = client.post(
        "/api/analyze",
        json=_VALID_BODY,
        headers={"Origin": "http://testserver"},
    )
    assert resp.status_code == 501  # passes CSRF check, hits the stub


def test_analyze_rejects_null_origin():
    client = TestClient(create_app(Settings(api_key=None)))
    resp = client.post("/api/analyze", json=_VALID_BODY, headers={"Origin": "null"})
    assert resp.status_code == 403


# --- Rate limiting (issue #110) ---


def test_analyze_rate_limited(monkeypatch):
    monkeypatch.setenv("MEDCHECK_RATE_LIMIT", "3")
    client = TestClient(create_app(Settings(api_key=None)))
    statuses = [client.post("/api/analyze", json=_VALID_BODY).status_code for _ in range(5)]
    assert statuses[:3] == [501, 501, 501]
    assert statuses[3] == 429
    assert statuses[4] == 429


# --- Per-request cloud LLM consent (issue #63) ---


def test_analyze_accepts_allow_cloud_llm_field():
    client = TestClient(create_app(Settings(api_key=None)))
    resp = client.post("/api/analyze", json={"source": "x", "allow_cloud_llm": True})
    assert resp.status_code == 501  # field is accepted by the schema

"""FastAPI web application for MedCheck."""

from __future__ import annotations

import hmac
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from medcheck import __version__
from medcheck.core.config import Settings

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class AnalyzeRequest(BaseModel):
    """Validated request body for POST /api/analyze."""

    source: str = Field(..., min_length=1, description="DICOM folder/ZIP path or portal URL")
    provider: str | None = Field(default=None, description="Data provider name (auto-detected if omitted)")
    anatomy: str | None = Field(default=None, description="Anatomy region hint, e.g. 'knee'")
    report_format: str = Field(default="json", pattern="^(json|pdf|html)$")
    # Keep in sync with the CLI (_REPORT_LANGUAGES) and the i18n catalogs
    # (medcheck/i18n/*.json) so fr/es requests aren't rejected with 422.
    language: str = Field(default="en", pattern="^(en|de|fr|es)$")
    # Per-request consent to transmit patient-derived data to external cloud
    # LLM APIs — mirrors the CLI --allow-cloud-llm flag.
    allow_cloud_llm: bool = Field(
        default=False,
        description="Consent to sending patient-derived data to external cloud LLM APIs",
    )


def _make_api_key_guard(expected_key: str | None) -> Any:
    """Build a dependency that enforces the X-API-Key header when configured.

    When ``MEDCHECK_API_KEY`` is unset the guard is a no-op (preserves the
    out-of-the-box localhost experience). When set, requests to protected
    endpoints must present a matching key.
    """

    def guard(provided: str | None = Depends(_api_key_header)) -> None:
        if not expected_key:
            return
        # Constant-time comparison to avoid leaking the key via timing.
        if not provided or not hmac.compare_digest(provided, expected_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key (set the X-API-Key header).",
            )

    return guard


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard HTTP security headers to every response.

    Defense-in-depth for a web app that handles patient-derived medical
    imaging data (PHI).  Particularly important when the server is exposed
    on the network via ``MEDCHECK_HOST=0.0.0.0``.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        # All JS lives in /static/*.js (no inline scripts or handlers), so
        # script-src does not need 'unsafe-inline'. style-src keeps it for the
        # inline <style> block and style= attributes in index.html.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none';"
        )
        return response


class _OriginCheckMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin state-changing requests (CSRF defence).

    Browsers attach an ``Origin`` header to cross-site POST/PUT/PATCH/DELETE
    requests. When it is present and does not match the request host, the
    request is refused. Same-origin requests and non-browser clients (which
    send no Origin header) are unaffected, so the API stays scriptable.
    """

    _STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.method in self._STATE_CHANGING:
            origin = request.headers.get("origin")
            if origin and origin.lower() != "null":
                origin_host = urlsplit(origin).netloc.lower()
                request_host = request.headers.get("host", "").lower()
                if origin_host != request_host:
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Cross-origin requests are not allowed."},
                    )
            elif origin:
                # 'null' origin (sandboxed iframe, file://) is never legitimate here.
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Cross-origin requests are not allowed."},
                )
        return await call_next(request)


class _RateLimiter:
    """Small in-memory sliding-window rate limiter keyed by client IP.

    Suitable for the single-process deployments this app targets; a reverse
    proxy or dedicated limiter should front any larger deployment.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            # Opportunistically drop empty buckets so the map can't grow unbounded.
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="MedCheck", version=__version__)
    require_api_key = _make_api_key_guard(settings.api_key)
    app.add_middleware(_SecurityHeadersMiddleware)
    app.add_middleware(_OriginCheckMiddleware)

    # DoS guard on the (expensive) analyze endpoint: MEDCHECK_RATE_LIMIT
    # requests per client IP per minute; 0 disables the limiter.
    rate_limiter = _RateLimiter(limit=int(os.environ.get("MEDCHECK_RATE_LIMIT", "10")))

    def enforce_rate_limit(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again later.",
            )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> Any:
        return templates.TemplateResponse(request, "index.html", {"version": __version__})

    @app.post("/api/analyze")
    def analyze(
        req: AnalyzeRequest,
        _: None = Depends(require_api_key),
        __: None = Depends(enforce_rate_limit),
    ) -> dict[str, Any]:
        # Pipeline execution is not wired up yet. Return 501 (not 200) so clients,
        # health checks, and CI can detect that no analysis was performed; the
        # validated source is echoed in the detail so callers can confirm parsing/auth.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Pipeline execution is not implemented yet (source={req.source!r}).",
        )

    return app

"""FastAPI web application for MedCheck."""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

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
    language: str = Field(default="en", pattern="^(en|de)$")


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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="MedCheck", version=__version__)
    require_api_key = _make_api_key_guard(settings.api_key)

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
    def analyze(req: AnalyzeRequest, _: None = Depends(require_api_key)) -> dict[str, Any]:
        # Pipeline execution is not wired up yet; the validated request is echoed
        # back so clients can confirm parsing/auth before the feature lands.
        return {"status": "not_implemented", "source": req.source}

    return app

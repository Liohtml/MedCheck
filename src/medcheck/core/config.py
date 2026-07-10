"""Application configuration via environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _env_int(name: str, default: int) -> int:
    """Parse an integer env var, failing with a clear config error on typos.

    A malformed value (e.g. MEDCHECK_PORT=8080a) must not surface as a raw
    ValueError traceback from inside dataclass construction — and silently
    falling back to the default would hide a misconfigured port or cap.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise SystemExit(f"Invalid {name}={raw!r}: expected an integer") from None


@dataclass
class Settings:
    # Bind to localhost by default; operators must opt into 0.0.0.0 explicitly
    # via MEDCHECK_HOST for network deployments (this app handles patient PHI).
    host: str = field(default_factory=lambda: os.environ.get("MEDCHECK_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("MEDCHECK_PORT", 8080))
    api_key: str | None = field(default_factory=lambda: os.environ.get("MEDCHECK_API_KEY"))
    # Consent gate: patient-derived data is only sent to external cloud LLM APIs
    # when this is explicitly enabled (MEDCHECK_ALLOW_EXTERNAL_LLM=1).
    allow_external_llm: bool = field(default_factory=lambda: _env_flag("MEDCHECK_ALLOW_EXTERNAL_LLM"))
    default_llm_provider: str = field(default_factory=lambda: os.environ.get("MEDCHECK_LLM_PROVIDER", "claude"))
    default_language: str = field(default_factory=lambda: os.environ.get("MEDCHECK_LANGUAGE", "en"))
    # Max slice images sent to the LLM per analysis. Bounds cost/latency and the
    # volume of patient-derived data leaving the host (MEDCHECK_MAX_VISION_IMAGES).
    max_vision_images: int = field(default_factory=lambda: _env_int("MEDCHECK_MAX_VISION_IMAGES", 12))
    # Hard cap on a portal exam-ZIP download, in bytes; guards against an oversized
    # or hostile response exhausting disk (MEDCHECK_MAX_DOWNLOAD_BYTES, default 2 GiB).
    max_download_bytes: int = field(
        default_factory=lambda: _env_int("MEDCHECK_MAX_DOWNLOAD_BYTES", 2 * 1024 * 1024 * 1024)
    )
    anthropic_api_key: str | None = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY"))
    openai_api_key: str | None = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY"))
    google_api_key: str | None = field(default_factory=lambda: os.environ.get("GOOGLE_API_KEY"))

    def available_llm_providers(self) -> list[str]:
        providers: list[str] = []
        if self.anthropic_api_key:
            providers.append("claude")
        if self.openai_api_key:
            providers.append("openai")
        if self.google_api_key:
            providers.append("gemini")
        providers.append("local")
        return providers

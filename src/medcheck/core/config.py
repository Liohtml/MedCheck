"""Application configuration via environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    host: str = field(default_factory=lambda: os.environ.get("MEDCHECK_HOST", "0.0.0.0"))  # nosec B104
    port: int = field(default_factory=lambda: int(os.environ.get("MEDCHECK_PORT", "8080")))
    default_llm_provider: str = field(default_factory=lambda: os.environ.get("MEDCHECK_LLM_PROVIDER", "claude"))
    default_language: str = field(default_factory=lambda: os.environ.get("MEDCHECK_LANGUAGE", "en"))
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

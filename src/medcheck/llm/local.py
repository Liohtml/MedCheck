"""Vision inference through an explicitly configured loopback model server.

MedCheck never downloads models or starts servers. A models listing confirms
availability, not medical accuracy or vision support; the configured model must
support OpenAI-compatible image_url chat messages.
"""

from __future__ import annotations

import base64
import ipaddress
import os
from typing import Any
from urllib.parse import urlsplit

import httpx

from medcheck.core.context import ClinicalContext
from medcheck.llm.base import (
    AnalysisResult,
    AnnotatedImage,
    LLMProvider,
    call_with_retries,
    llm_timeout,
    parse_llm_response,
)


class LocalLLMProvider(LLMProvider):
    """A user-managed OpenAI-compatible vision server on this machine."""

    name = "local"
    supports_vision = True

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or os.environ.get("MEDCHECK_LOCAL_MODEL", "")
        self.base_url = base_url or os.environ.get("MEDCHECK_LOCAL_URL", "")

    def _validated_url(self) -> str:
        parsed = urlsplit(self.base_url)
        try:
            loopback = ipaddress.ip_address(parsed.hostname or "").is_loopback
            valid_port = parsed.port is None or 0 < parsed.port <= 65535
        except ValueError:
            loopback = False
            valid_port = False
        if (
            parsed.scheme not in {"http", "https"}
            or not loopback
            or not valid_port
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not self.model.strip()
        ):
            raise ValueError(
                "Set MEDCHECK_LOCAL_MODEL and MEDCHECK_LOCAL_URL to a loopback IP endpoint "
                "such as http://127.0.0.1:11434/v1. Hostnames and remote endpoints are not allowed."
            )
        return self.base_url.rstrip("/")

    def check_available(self) -> bool:
        try:
            url = self._validated_url()
            with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as client:
                response = client.get(f"{url}/models")
                response.raise_for_status()
                data = response.json()
            return any(item.get("id") == self.model for item in data.get("data", []) if isinstance(item, dict))
        except (ValueError, TypeError, AttributeError, httpx.HTTPError):
            return False

    def analyze_images(
        self,
        images: list[AnnotatedImage],
        prompt: str,
        context: ClinicalContext | None,
    ) -> AnalysisResult:
        url = self._validated_url()
        content: list[dict[str, Any]] = []
        for img in images:
            b64 = base64.standard_b64encode(img.image_bytes).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
            if img.description:
                content.append({"type": "text", "text": img.description})
        content.append({"type": "text", "text": prompt})
        with httpx.Client(timeout=llm_timeout(), trust_env=False, follow_redirects=False) as client:

            def _request() -> str:
                response = client.post(
                    f"{url}/chat/completions",
                    json={"model": self.model, "messages": [{"role": "user", "content": content}], "stream": False},
                )
                response.raise_for_status()
                result = response.json()["choices"][0]["message"]["content"]
                if not isinstance(result, str):
                    raise ValueError("Local model returned no text; configure a vision-capable chat model.")
                return result

            raw = call_with_retries(_request, provider=self.name)
        return parse_llm_response(raw)

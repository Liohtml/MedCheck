from __future__ import annotations

import importlib
import os
from typing import Any

from medcheck.core.context import ClinicalContext
from medcheck.llm.base import (
    AnalysisResult,
    AnnotatedImage,
    LLMProvider,
    call_with_retries,
    llm_timeout,
    parse_llm_response,
)


class GeminiProvider(LLMProvider):
    """Google Gemini provider."""

    name = "gemini"
    supports_vision = True

    def __init__(self, model: str | None = None) -> None:
        # Overridable via MEDCHECK_GEMINI_MODEL.
        self.model = model or os.environ.get("MEDCHECK_GEMINI_MODEL", "gemini-3.5-flash")

    def check_available(self) -> bool:
        if not os.environ.get("GOOGLE_API_KEY"):
            return False
        try:
            importlib.import_module("google.genai")
        except ImportError:
            return False
        return True

    def analyze_images(
        self,
        images: list[AnnotatedImage],
        prompt: str,
        context: ClinicalContext | None,
    ) -> AnalysisResult:
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(llm_timeout() * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

        parts: list[Any] = []
        for img in images:
            parts.append(types.Part.from_bytes(data=img.image_bytes, mime_type="image/png"))
            if img.description:
                parts.append(img.description)

        parts.append(prompt)

        def _request() -> str:
            response = client.models.generate_content(model=self.model, contents=parts)
            return str(response.text or "")

        try:
            raw = call_with_retries(_request, provider=self.name)
            return parse_llm_response(raw)
        finally:
            client.close()

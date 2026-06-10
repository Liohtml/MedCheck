from __future__ import annotations

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
        return bool(os.environ.get("GOOGLE_API_KEY"))

    def analyze_images(
        self,
        images: list[AnnotatedImage],
        prompt: str,
        context: ClinicalContext | None,
    ) -> AnalysisResult:
        import google.generativeai as genai

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(self.model)

        parts: list[Any] = []
        for img in images:
            parts.append({"mime_type": "image/png", "data": img.image_bytes})
            if img.description:
                parts.append(img.description)

        parts.append(prompt)

        def _request() -> str:
            response = model.generate_content(parts, request_options={"timeout": llm_timeout()})
            return str(response.text)

        raw = call_with_retries(_request, provider=self.name)
        return parse_llm_response(raw)

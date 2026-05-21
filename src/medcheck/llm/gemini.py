from __future__ import annotations

import json
import os
import re

from medcheck.core.context import ClinicalContext, StructureFinding
from medcheck.llm.base import AnalysisResult, AnnotatedImage, LLMProvider


class GeminiProvider(LLMProvider):
    """Google Gemini provider."""

    name = "gemini"
    supports_vision = True

    def __init__(self, model: str = "gemini-3.5-flash") -> None:
        self.model = model

    def check_available(self) -> bool:
        return bool(os.environ.get("GOOGLE_API_KEY"))

    def analyze_images(
        self,
        images: list[AnnotatedImage],
        prompt: str,
        context: ClinicalContext,
    ) -> AnalysisResult:
        import google.generativeai as genai

        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        model = genai.GenerativeModel(self.model)

        parts: list = []
        for img in images:
            parts.append({"mime_type": "image/png", "data": img.image_bytes})
            if img.description:
                parts.append(img.description)

        parts.append(prompt)

        response = model.generate_content(parts)
        raw = response.text
        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> AnalysisResult:
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                structures = [StructureFinding(**s) for s in data.get("structures", [])]
                return AnalysisResult(
                    structures=structures,
                    overall_impression=data.get("overall_impression", ""),
                    clinical_correlation=data.get("clinical_correlation", ""),
                    limitations=data.get("limitations", []),
                    raw_response=raw,
                )
            except (json.JSONDecodeError, TypeError):
                pass
        return AnalysisResult(overall_impression=raw, raw_response=raw)

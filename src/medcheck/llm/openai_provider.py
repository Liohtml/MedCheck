from __future__ import annotations

import base64
import json
import os
import re

from medcheck.core.context import ClinicalContext, StructureFinding
from medcheck.llm.base import AnalysisResult, AnnotatedImage, LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider."""

    name = "openai"
    supports_vision = True

    def __init__(self, model: str = "gpt-5.5") -> None:
        self.model = model

    def check_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def analyze_images(
        self,
        images: list[AnnotatedImage],
        prompt: str,
        context: ClinicalContext,
    ) -> AnalysisResult:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        content: list[dict] = []
        for img in images:
            b64 = base64.standard_b64encode(img.image_bytes).decode()
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                }
            )
            if img.description:
                content.append({"type": "text", "text": img.description})

        content.append({"type": "text", "text": prompt})

        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            max_tokens=4096,
        )

        raw = response.choices[0].message.content or ""
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

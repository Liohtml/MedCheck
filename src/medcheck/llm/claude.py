from __future__ import annotations

import base64
import json
import os
import re

from medcheck.core.context import ClinicalContext, StructureFinding
from medcheck.llm.base import AnalysisResult, AnnotatedImage, LLMProvider


class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider."""

    name = "claude"
    supports_vision = True

    def __init__(self, model: str = "claude-opus-4-7") -> None:
        self.model = model

    def check_available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def analyze_images(
        self,
        images: list[AnnotatedImage],
        prompt: str,
        context: ClinicalContext,
    ) -> AnalysisResult:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        content: list[dict] = []
        for img in images:
            b64 = base64.standard_b64encode(img.image_bytes).decode()
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                }
            )
            if img.description:
                content.append({"type": "text", "text": img.description})

        content.append({"type": "text", "text": prompt})

        message = client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )

        raw = message.content[0].text
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

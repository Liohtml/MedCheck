from __future__ import annotations

import base64
import os
from typing import Any

from medcheck.core.context import ClinicalContext
from medcheck.llm.base import AnalysisResult, AnnotatedImage, LLMProvider, parse_llm_response


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
        context: ClinicalContext | None,
    ) -> AnalysisResult:
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        client = OpenAI(api_key=api_key)

        content: list[dict[str, Any]] = []
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
        return parse_llm_response(raw)

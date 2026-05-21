from __future__ import annotations

import base64
import os

from medcheck.core.context import ClinicalContext
from medcheck.llm.base import AnalysisResult, AnnotatedImage, LLMProvider, parse_llm_response


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

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic(api_key=api_key)

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
        return parse_llm_response(raw)

from __future__ import annotations

import base64
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
        context: ClinicalContext | None,
    ) -> AnalysisResult:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        # max_retries=0: call_with_retries is the single retry controller, so we
        # disable the SDK's own retries to avoid stacking (up to 3 x 3 attempts).
        client = anthropic.Anthropic(api_key=api_key, timeout=llm_timeout(), max_retries=0)

        content: list[dict[str, Any]] = []
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

        def _request() -> str:
            message = client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": content}],
            )
            return str(message.content[0].text)

        raw = call_with_retries(_request, provider=self.name)
        return parse_llm_response(raw)

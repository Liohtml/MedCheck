from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from medcheck.core.context import ClinicalContext, StructureFinding


@dataclass
class AnnotatedImage:
    series_name: str
    slice_index: int
    image_bytes: bytes
    description: str


@dataclass
class AnalysisResult:
    overall_impression: str = ""
    raw_response: str = ""
    structures: list[StructureFinding] = field(default_factory=list)
    clinical_correlation: str = ""
    limitations: list[str] = field(default_factory=list)


def parse_llm_json(raw: str) -> dict:
    """Extract and parse the first valid JSON object from *raw* using brace-depth tracking."""
    start = raw.index("{")
    depth = 0
    for i, ch in enumerate(raw[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if depth == 0:
            return json.loads(raw[start : i + 1])
    raise ValueError("No valid JSON found")


def parse_llm_response(raw: str) -> AnalysisResult:
    """Shared response parser used by all LLM providers."""
    try:
        data = parse_llm_json(raw)
        structures = [StructureFinding(**s) for s in data.get("structures", [])]
        return AnalysisResult(
            structures=structures,
            overall_impression=data.get("overall_impression", ""),
            clinical_correlation=data.get("clinical_correlation", ""),
            limitations=data.get("limitations", []),
            raw_response=raw,
        )
    except (ValueError, json.JSONDecodeError, TypeError):
        return AnalysisResult(overall_impression=raw, raw_response=raw)


class LLMProvider(ABC):
    name: str = ""
    supports_vision: bool = False

    @abstractmethod
    def check_available(self) -> bool:
        """Return True if this provider is configured and reachable."""

    @abstractmethod
    def analyze_images(
        self,
        images: list[AnnotatedImage],
        prompt: str,
        context: ClinicalContext,
    ) -> AnalysisResult:
        """Run image analysis and return structured results."""

from __future__ import annotations

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

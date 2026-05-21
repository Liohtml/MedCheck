from __future__ import annotations

from abc import ABC, abstractmethod

from medcheck.core.context import PipelineContext


class PipelineStep(ABC):
    name: str = ""

    @abstractmethod
    def run(self, context: PipelineContext) -> PipelineContext:
        """Execute this step and return the (modified) context."""

    def validate(self, context: PipelineContext) -> bool:
        """Validate preconditions before running. Returns True by default."""
        return True

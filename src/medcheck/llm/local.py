"""Local (offline) LLM provider stub.

The README advertises a fully-offline LLaVA-Med provider. The actual on-device
model is tracked in https://github.com/Liohtml/MedCheck/issues/18; until it lands
this stub keeps the ``"local"`` entry in ``LLMRouter.FALLBACK_ORDER`` honest:
it reports itself as unavailable so the router skips it cleanly instead of the
pipeline failing with a confusing error, and raises an actionable message if it
is ever invoked directly.
"""

from __future__ import annotations

from medcheck.core.context import ClinicalContext
from medcheck.llm.base import AnalysisResult, AnnotatedImage, LLMProvider

_NOT_IMPLEMENTED_MESSAGE = (
    "Local LLM provider (LLaVA-Med) is not yet implemented. "
    "Configure a cloud provider (ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_API_KEY) "
    "or follow https://github.com/Liohtml/MedCheck/issues/18 for offline support."
)


class LocalLLMProvider(LLMProvider):
    """Placeholder for the planned on-device LLaVA-Med vision provider."""

    name = "local"
    supports_vision = True
    model = "llava-med (not installed)"

    def check_available(self) -> bool:
        # Not implemented yet — the router treats this as "skip me".
        return False

    def analyze_images(
        self,
        images: list[AnnotatedImage],
        prompt: str,
        context: ClinicalContext | None,
    ) -> AnalysisResult:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)

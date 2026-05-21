from __future__ import annotations

from medcheck.llm.base import LLMProvider

FALLBACK_ORDER = ["claude", "openai", "gemini", "local"]


class LLMRouter:
    """Register LLM providers and select the best available one."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        """Add a provider to the registry."""
        self._providers[provider.name] = provider

    def select(self, preferred: str) -> LLMProvider:
        """Return the preferred provider if available, else fall back through
        FALLBACK_ORDER, then any registered available provider."""
        # Try the explicitly requested provider first.
        preferred_provider = self._providers.get(preferred)
        if preferred_provider and preferred_provider.check_available():
            return preferred_provider

        # Walk the canonical fallback order.
        for name in FALLBACK_ORDER:
            if name == preferred:
                continue
            provider = self._providers.get(name)
            if provider and provider.check_available():
                return provider

        # Last resort: any registered provider that is available.
        for provider in self._providers.values():
            if provider.check_available():
                return provider

        raise RuntimeError("No LLM provider available")

    def list_available(self) -> list[str]:
        """Return names of all currently available providers."""
        return [name for name, provider in self._providers.items() if provider.check_available()]

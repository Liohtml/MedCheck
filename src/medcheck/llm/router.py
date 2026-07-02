from __future__ import annotations

import logging

from medcheck.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# The only provider that may be substituted automatically: it runs on-device,
# so a fallback never changes where patient-derived data is transmitted.
_SAFE_FALLBACK = "local"


class LLMRouter:
    """Register LLM providers and select the requested one.

    A requested cloud provider is never silently replaced by a *different*
    cloud provider: that would transmit patient-derived data (PHI) to a third
    party the user did not choose. The only permitted automatic fallback is
    the on-device 'local' provider, and even that is logged loudly.
    """

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        """Add a provider to the registry."""
        self._providers[provider.name] = provider

    def select(self, preferred: str) -> LLMProvider:
        """Return the preferred provider if available.

        If it is not available, fall back to the on-device 'local' provider
        (with a warning) — never to another cloud provider. If neither is
        available, raise a descriptive error.
        """
        preferred_provider = self._providers.get(preferred)
        if preferred_provider and preferred_provider.check_available():
            return preferred_provider

        if preferred != _SAFE_FALLBACK:
            local = self._providers.get(_SAFE_FALLBACK)
            if local and local.check_available():
                logger.warning(
                    "Requested LLM provider '%s' is not available; falling back to the "
                    "on-device 'local' provider. No data leaves this machine.",
                    preferred,
                )
                return local

        available = ", ".join(self.list_available()) or "none"
        raise RuntimeError(
            f"Requested LLM provider '{preferred}' is not available (check API key / configuration) "
            f"and no on-device fallback is available. Available providers: {available}. "
            "Cloud-to-cloud fallback is disabled so patient data is never sent to an "
            "unintended third party — set MEDCHECK_LLM_PROVIDER to an available provider."
        )

    def list_available(self) -> list[str]:
        """Return names of all currently available providers."""
        return [name for name, provider in self._providers.items() if provider.check_available()]

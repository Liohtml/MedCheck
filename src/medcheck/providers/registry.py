from __future__ import annotations

import re
from pathlib import Path

from medcheck.providers.base import DataProvider


class ProviderRegistry:
    """Registry for DataProvider implementations with auto-detection support."""

    def __init__(self) -> None:
        self._providers: dict[str, type[DataProvider]] = {}

    def register(self, provider_class: type[DataProvider]) -> None:
        """Register a provider class by its name."""
        self._providers[provider_class.name] = provider_class

    def get(self, name: str) -> DataProvider:
        """Return a provider instance by name."""
        if name not in self._providers:
            raise ValueError(f"Unknown provider: '{name}'")
        return self._providers[name]()

    def detect(self, target: str) -> DataProvider:
        """Auto-detect the appropriate provider for the given target string.

        Tries URL pattern matching first, then falls back to filesystem checks.
        """
        # Try URL pattern matching against registered providers
        for _name, cls in self._providers.items():
            for pattern in cls.url_patterns:
                if re.search(pattern, target):
                    return cls()

        # Fallback: treat as a local path if it resolves to an existing dir or ZIP
        target_path = Path(target)
        if target_path.exists() and (target_path.is_dir() or target_path.suffix.lower() == ".zip"):
            if "local" in self._providers:
                return self._providers["local"]()

        raise ValueError(f"No provider found for target: '{target}'. No provider found matching the given target.")

    def list_providers(self) -> list[str]:
        """Return sorted list of registered provider names."""
        return sorted(self._providers.keys())

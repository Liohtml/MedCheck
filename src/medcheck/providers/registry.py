from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from medcheck.providers.base import DataProvider


def _target_host(target: str) -> str:
    """Best-effort hostname extraction from a target string.

    Returns an empty string when the target has no parseable host (e.g. it is
    a filesystem path). Scheme-less URLs like ``portal.example.net/view/x``
    are only treated as URLs when they do not name an existing local path.
    """
    host = urlparse(target).hostname
    if host:
        return host
    if not Path(target).exists():
        return urlparse("//" + target).hostname or ""
    return ""


def _host_matches(host: str, pattern: str) -> bool:
    """True if *host* equals *pattern* or is a subdomain of it."""
    return host == pattern or host.endswith("." + pattern)


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

        Tries URL hostname matching first, then falls back to filesystem checks.
        """
        # Match the target's hostname against registered providers' domains.
        # Exact-host/subdomain comparison (not regex/substring) so that local
        # paths merely containing a provider name are not mis-detected.
        host = _target_host(target)
        if host:
            for _name, cls in self._providers.items():
                if any(_host_matches(host, pattern) for pattern in cls.url_patterns):
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

import pytest

from medcheck.providers.local import LocalProvider
from medcheck.providers.registry import ProviderRegistry


def test_registry_auto_detect_local(tmp_path):
    registry = ProviderRegistry()
    registry.register(LocalProvider)
    provider = registry.detect(str(tmp_path))
    assert isinstance(provider, LocalProvider)


def test_registry_auto_detect_url_fails():
    registry = ProviderRegistry()
    registry.register(LocalProvider)
    with pytest.raises(ValueError, match="No provider found"):
        registry.detect("https://unknown-portal.com/view/abc")


def test_registry_get_by_name():
    registry = ProviderRegistry()
    registry.register(LocalProvider)
    provider = registry.get("local")
    assert isinstance(provider, LocalProvider)


def test_registry_unknown_name():
    registry = ProviderRegistry()
    with pytest.raises(ValueError, match="Unknown provider"):
        registry.get("nonexistent")

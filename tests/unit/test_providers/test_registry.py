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


def test_registry_detect_matches_provider_host():
    from medcheck.providers.easyradiology import EasyRadiologyProvider

    registry = ProviderRegistry()
    registry.register(LocalProvider)
    registry.register(EasyRadiologyProvider)
    provider = registry.detect("https://portal.easyradiology.net/View/abc123")
    assert isinstance(provider, EasyRadiologyProvider)


def test_registry_detect_schemeless_provider_url():
    from medcheck.providers.easyradiology import EasyRadiologyProvider

    registry = ProviderRegistry()
    registry.register(EasyRadiologyProvider)
    provider = registry.detect("portal.easyradiology.net/View/abc123")
    assert isinstance(provider, EasyRadiologyProvider)


def test_registry_local_path_containing_provider_name_is_not_misdetected(tmp_path):
    from medcheck.providers.easyradiology import EasyRadiologyProvider

    registry = ProviderRegistry()
    registry.register(EasyRadiologyProvider)
    registry.register(LocalProvider)
    # A directory whose name merely contains the provider domain (with "." as
    # regex-wildcard bait) must resolve to the local provider, not the portal.
    trap = tmp_path / "easyradiologyXnet"
    trap.mkdir()
    provider = registry.detect(str(trap))
    assert isinstance(provider, LocalProvider)


def test_registry_detect_unrelated_host_falls_through():
    from medcheck.providers.easyradiology import EasyRadiologyProvider

    registry = ProviderRegistry()
    registry.register(EasyRadiologyProvider)
    with pytest.raises(ValueError, match="No provider found"):
        registry.detect("https://noteasyradiology.net/View/abc123")

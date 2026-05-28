import pytest

from medcheck.llm.local import LocalLLMProvider


def test_local_provider_metadata():
    provider = LocalLLMProvider()
    assert provider.name == "local"
    assert provider.supports_vision is True


def test_local_provider_not_available():
    # Until LLaVA-Med ships, the provider reports unavailable so the router skips it.
    assert LocalLLMProvider().check_available() is False


def test_local_provider_analyze_raises_actionable_error():
    provider = LocalLLMProvider()
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        provider.analyze_images([], "prompt", None)

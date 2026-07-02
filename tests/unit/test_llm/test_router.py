import pytest

from medcheck.llm.base import AnalysisResult, LLMProvider
from medcheck.llm.router import LLMRouter


class FakeLLM(LLMProvider):
    name = "fake"
    supports_vision = True

    def check_available(self) -> bool:
        return True

    def analyze_images(self, images, prompt, context):
        return AnalysisResult(overall_impression="Test", raw_response="{}")


class UnavailableLLM(LLMProvider):
    name = "unavailable"
    supports_vision = True

    def check_available(self) -> bool:
        return False

    def analyze_images(self, images, prompt, context):
        raise RuntimeError("Should not be called")


def test_router_selects_requested():
    router = LLMRouter()
    router.register(FakeLLM())
    assert router.select("fake").name == "fake"


class LocalFakeLLM(FakeLLM):
    name = "local"


def test_router_no_silent_cloud_fallback():
    # A different cloud provider must never be substituted silently (PHI risk).
    router = LLMRouter()
    router.register(UnavailableLLM())
    router.register(FakeLLM())
    with pytest.raises(RuntimeError, match="not available"):
        router.select("unavailable")


def test_router_falls_back_to_local_only():
    router = LLMRouter()
    router.register(UnavailableLLM())
    router.register(LocalFakeLLM())
    assert router.select("unavailable").name == "local"


def test_router_none_available():
    router = LLMRouter()
    router.register(UnavailableLLM())
    with pytest.raises(RuntimeError, match="not available"):
        router.select("unavailable")


def test_router_list_available():
    router = LLMRouter()
    router.register(FakeLLM())
    router.register(UnavailableLLM())
    assert router.list_available() == ["fake"]

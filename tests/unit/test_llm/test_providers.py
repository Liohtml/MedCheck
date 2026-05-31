"""Tests for the cloud LLM providers using fake SDK modules (no network)."""

import sys
import types

import pytest

from medcheck.llm.base import AnnotatedImage
from medcheck.llm.claude import ClaudeProvider
from medcheck.llm.gemini import GeminiProvider
from medcheck.llm.openai_provider import OpenAIProvider

_JSON = '{"overall_impression": "ok", "structures": []}'
# One image exercises each provider's image-encoding loop.
_IMAGES = [AnnotatedImage(series_name="s", slice_index=0, image_bytes=b"\x89PNG", description="Slice 1")]


def _install_fake_anthropic(monkeypatch, captured):
    module = types.ModuleType("anthropic")

    class _Messages:
        def create(self, **kwargs):
            return types.SimpleNamespace(content=[types.SimpleNamespace(text=_JSON)])

    class _Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.messages = _Messages()

    module.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", module)


def _install_fake_openai(monkeypatch, captured):
    module = types.ModuleType("openai")

    class _Completions:
        def create(self, **kwargs):
            msg = types.SimpleNamespace(content=_JSON)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class _Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = types.SimpleNamespace(completions=_Completions())

    module.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", module)


def _install_fake_gemini(monkeypatch, captured):
    genai = types.ModuleType("google.generativeai")
    genai.configure = lambda **kwargs: None

    class _Model:
        def __init__(self, name):
            captured["model"] = name

        def generate_content(self, parts, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(text=_JSON)

    genai.GenerativeModel = _Model
    google_pkg = sys.modules.get("google") or types.ModuleType("google")
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)


def test_claude_analyze_images(monkeypatch):
    captured: dict = {}
    _install_fake_anthropic(monkeypatch, captured)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    monkeypatch.setenv("MEDCHECK_LLM_TIMEOUT", "30")

    result = ClaudeProvider().analyze_images(_IMAGES, "prompt", None)
    assert result.overall_impression == "ok"
    # Timeout is wired in and SDK retries are disabled (call_with_retries owns retries).
    assert captured["timeout"] == 30.0
    assert captured["max_retries"] == 0


def test_claude_missing_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _install_fake_anthropic(monkeypatch, {})
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ClaudeProvider().analyze_images(_IMAGES, "prompt", None)


def test_openai_analyze_images(monkeypatch):
    captured: dict = {}
    _install_fake_openai(monkeypatch, captured)
    monkeypatch.setenv("OPENAI_API_KEY", "key")

    result = OpenAIProvider().analyze_images(_IMAGES, "prompt", None)
    assert result.overall_impression == "ok"
    assert captured["max_retries"] == 0


def test_openai_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _install_fake_openai(monkeypatch, {})
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIProvider().analyze_images(_IMAGES, "prompt", None)


def test_gemini_analyze_images(monkeypatch):
    captured: dict = {}
    _install_fake_gemini(monkeypatch, captured)
    monkeypatch.setenv("GOOGLE_API_KEY", "key")

    result = GeminiProvider().analyze_images(_IMAGES, "prompt", None)
    assert result.overall_impression == "ok"
    # Timeout passed through request_options.
    assert captured["request_options"]["timeout"] > 0


def test_gemini_missing_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    _install_fake_gemini(monkeypatch, {})
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        GeminiProvider().analyze_images(_IMAGES, "prompt", None)

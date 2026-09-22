import json

import httpx
import pytest

from medcheck.llm.base import AnnotatedImage, LLMProviderError
from medcheck.llm.local import LocalLLMProvider


def _mock_client(monkeypatch, handler):
    original = httpx.Client
    captured = {}

    def client(**kwargs):
        captured.update(kwargs)
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("medcheck.llm.local.httpx.Client", client)
    return captured


def test_local_unconfigured(monkeypatch):
    monkeypatch.delenv("MEDCHECK_LOCAL_URL", raising=False)
    monkeypatch.delenv("MEDCHECK_LOCAL_MODEL", raising=False)
    provider = LocalLLMProvider()
    assert provider.name == "local"
    assert provider.supports_vision
    assert not provider.check_available()
    with pytest.raises(ValueError, match="MEDCHECK_LOCAL_MODEL"):
        provider.analyze_images([], "prompt", None)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "http://localhost/v1",
        "http://192.168.1.1/v1",
        "http://127.0.0.1.evil.test/v1",
        "http://127.0.0.1:99999/v1",
        "http://user:pass@127.0.0.1/v1",
        "ftp://127.0.0.1/v1",
        "http://127.0.0.1/v1?target=evil",
        "http://127.0.0.1/v1#fragment",
    ],
)
def test_remote_or_ambiguous_endpoint_never_connects(url, monkeypatch):
    def unexpected(**kwargs):
        pytest.fail("invalid local URL must not create a client")

    monkeypatch.setattr("medcheck.llm.local.httpx.Client", unexpected)
    provider = LocalLLMProvider(model="vision", base_url=url)
    assert not provider.check_available()
    with pytest.raises(ValueError, match="loopback"):
        provider.analyze_images([], "prompt", None)


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434/v1", "http://[::1]:8080/v1"])
def test_probe_and_inference(url, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "vision"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"overall_impression":"ok"}'}}]})

    captured = _mock_client(monkeypatch, handler)
    provider = LocalLLMProvider(model="vision", base_url=url)
    assert provider.check_available()
    result = provider.analyze_images([AnnotatedImage("s", 0, b"png", "slice 0")], "prompt", None)
    assert result.overall_impression == "ok"
    assert captured["trust_env"] is False
    assert captured["follow_redirects"] is False
    payload = json.loads(requests[-1].content)
    assert payload["model"] == "vision"
    assert payload["messages"][0]["content"][0]["image_url"]["url"] == "data:image/png;base64,cG5n"


def test_redirect_not_followed(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(307, headers={"Location": "https://external.invalid"})

    _mock_client(monkeypatch, handler)
    provider = LocalLLMProvider(model="vision", base_url="http://127.0.0.1/v1")
    assert not provider.check_available()
    with pytest.raises(LLMProviderError):
        provider.analyze_images([], "prompt", None)
    assert len(requests) == 2
    assert all(r.url.host == "127.0.0.1" for r in requests)


@pytest.mark.parametrize("body", [{"data": [{"id": "other"}]}, {"data": None}, [], {"data": []}])
def test_missing_model_or_invalid_probe(monkeypatch, body):
    _mock_client(monkeypatch, lambda request: httpx.Response(200, json=body))
    assert not LocalLLMProvider(model="vision", base_url="http://127.0.0.1/v1").check_available()

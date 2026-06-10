import pytest

from medcheck.llm.base import (
    LLMProviderError,
    _llm_attempts,
    call_with_retries,
    is_transient_error,
    llm_timeout,
    parse_llm_response,
)


def test_parse_llm_response_clamps_and_coerces():
    raw = """{"structures": [
        {"name": "ACL", "status": "torn", "confidence": 1.7, "slices_evaluated": "3"},
        {"name": "PCL", "confidence": "high", "bogus_key": 1}
    ], "overall_impression": "x"}"""
    result = parse_llm_response(raw)
    assert len(result.structures) == 2
    acl = result.structures[0]
    assert acl.confidence == 1.0  # clamped from 1.7
    assert acl.slices_evaluated == 3  # coerced from "3"
    pcl = result.structures[1]
    assert pcl.confidence == 0.0  # "high" -> safe default
    assert pcl.name == "PCL"  # unknown key ignored, didn't crash


def test_parse_llm_response_skips_empty_and_nonlist():
    # Entries with neither name nor findings are dropped.
    assert parse_llm_response('{"structures": [{"confidence": 0.9}]}').structures == []
    # Non-list "structures" must not crash.
    assert parse_llm_response('{"structures": "oops"}').structures == []


def test_parse_llm_response_non_json_falls_back():
    result = parse_llm_response("no json here")
    assert result.overall_impression == "no json here"
    assert result.structures == []


def test_call_with_retries_returns_on_first_success():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    assert call_with_retries(fn, provider="x", base_delay=0) == "ok"
    assert calls["n"] == 1


def test_call_with_retries_recovers_after_transient_failures():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    assert call_with_retries(fn, provider="x", attempts=3, base_delay=0) == "ok"
    assert calls["n"] == 3


def test_call_with_retries_wraps_final_failure():
    def fn():
        raise ConnectionError("boom")

    with pytest.raises(LLMProviderError, match="x request failed after 3 attempt"):
        call_with_retries(fn, provider="x", attempts=3, base_delay=0)


def test_llm_timeout_from_env(monkeypatch):
    monkeypatch.setenv("MEDCHECK_LLM_TIMEOUT", "45.5")
    assert llm_timeout() == 45.5
    monkeypatch.setenv("MEDCHECK_LLM_TIMEOUT", "not-a-number")
    assert llm_timeout() == 120.0


def test_llm_attempts_from_env(monkeypatch):
    monkeypatch.setenv("MEDCHECK_LLM_RETRIES", "4")
    assert _llm_attempts() == 5
    monkeypatch.delenv("MEDCHECK_LLM_RETRIES", raising=False)
    assert _llm_attempts() == 3


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


def test_is_transient_error_classification():
    assert is_transient_error(TimeoutError())
    assert is_transient_error(ConnectionError())
    assert is_transient_error(_StatusError(429))
    assert is_transient_error(_StatusError(503))
    # Permanent failures must not be retried.
    assert not is_transient_error(_StatusError(401))
    assert not is_transient_error(_StatusError(400))
    assert not is_transient_error(ValueError("bad request"))


def test_call_with_retries_coerces_invalid_attempts():
    # attempts <= 0 must still run once and wrap the error, not crash.
    def fn():
        raise ConnectionError("boom")

    with pytest.raises(LLMProviderError, match="failed after 1 attempt"):
        call_with_retries(fn, provider="x", attempts=0, base_delay=0)


def test_call_with_retries_fails_fast_on_non_transient():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _StatusError(401)

    with pytest.raises(LLMProviderError, match="x request failed after 1 attempt"):
        call_with_retries(fn, provider="x", attempts=3, base_delay=0)
    # Non-transient error: no retries.
    assert calls["n"] == 1

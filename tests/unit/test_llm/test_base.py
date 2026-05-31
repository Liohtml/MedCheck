import pytest

from medcheck.llm.base import (
    LLMProviderError,
    _llm_attempts,
    call_with_retries,
    is_transient_error,
    llm_timeout,
)


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


def test_call_with_retries_fails_fast_on_non_transient():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _StatusError(401)

    with pytest.raises(LLMProviderError, match="x request failed after 1 attempt"):
        call_with_retries(fn, provider="x", attempts=3, base_delay=0)
    # Non-transient error: no retries.
    assert calls["n"] == 1

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from medcheck.core.context import ClinicalContext, StructureFinding

T = TypeVar("T")


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider call fails after exhausting retries."""


def llm_timeout() -> float:
    """Per-request timeout (seconds) for LLM API calls (MEDCHECK_LLM_TIMEOUT)."""
    try:
        return float(os.environ.get("MEDCHECK_LLM_TIMEOUT", "120"))
    except ValueError:
        return 120.0


def _llm_attempts() -> int:
    """Total attempts = 1 + MEDCHECK_LLM_RETRIES (default 2 retries → 3 attempts)."""
    try:
        return max(1, int(os.environ.get("MEDCHECK_LLM_RETRIES", "2")) + 1)
    except ValueError:
        return 3


def _status_code(exc: BaseException) -> int | None:
    """Best-effort extraction of an HTTP status code from an SDK exception."""
    for attr in ("status_code", "code", "http_status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def is_transient_error(exc: BaseException) -> bool:
    """Return True for errors worth retrying (timeouts, connection drops, 429/5xx).

    Permanent failures (auth, invalid request, 4xx other than 429) should fail
    fast rather than burn retries and inflate cost/latency.
    """
    if isinstance(exc, TimeoutError | ConnectionError):
        return True
    # Many SDKs expose timeout/connection errors only by class name.
    name = type(exc).__name__.lower()
    if any(token in name for token in ("timeout", "connection", "serviceunavailable")):
        return True
    status = _status_code(exc)
    if status is not None:
        return status == 429 or status >= 500
    return False


def call_with_retries(
    fn: Callable[[], T],
    *,
    provider: str,
    attempts: int | None = None,
    base_delay: float = 1.0,
) -> T:
    """Call *fn*, retrying only transient failures with exponential backoff.

    Transient errors (timeouts, connection drops, HTTP 429/5xx) are retried;
    permanent ones (auth, invalid request) fail fast. On the final/permanent
    failure the underlying exception is wrapped in an :class:`LLMProviderError`
    carrying the provider name, so callers get a clear, actionable message
    instead of an opaque SDK traceback crashing the pipeline.
    """
    total = attempts if attempts is not None else _llm_attempts()
    last_exc: Exception | None = None
    for attempt in range(total):
        try:
            return fn()
        except Exception as exc:  # normalise any SDK error into LLMProviderError
            last_exc = exc
            if attempt < total - 1 and is_transient_error(exc):
                time.sleep(base_delay * (2**attempt))
                continue
            break
    raise LLMProviderError(f"{provider} request failed after {attempt + 1} attempt(s): {last_exc}") from last_exc


@dataclass
class AnnotatedImage:
    series_name: str
    slice_index: int
    image_bytes: bytes
    description: str


@dataclass
class AnalysisResult:
    overall_impression: str = ""
    raw_response: str = ""
    structures: list[StructureFinding] = field(default_factory=list)
    clinical_correlation: str = ""
    limitations: list[str] = field(default_factory=list)


def parse_llm_json(raw: str) -> dict[str, Any]:
    """Extract and parse the first valid JSON object from *raw* using brace-depth tracking."""
    start = raw.index("{")
    depth = 0
    for i, ch in enumerate(raw[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if depth == 0:
            result: dict[str, Any] = json.loads(raw[start : i + 1])
            return result
    raise ValueError("No valid JSON found")


def parse_llm_response(raw: str) -> AnalysisResult:
    """Shared response parser used by all LLM providers."""
    try:
        data = parse_llm_json(raw)
        structures = [StructureFinding(**s) for s in data.get("structures", [])]
        return AnalysisResult(
            structures=structures,
            overall_impression=data.get("overall_impression", ""),
            clinical_correlation=data.get("clinical_correlation", ""),
            limitations=data.get("limitations", []),
            raw_response=raw,
        )
    except (ValueError, json.JSONDecodeError, TypeError):
        return AnalysisResult(overall_impression=raw, raw_response=raw)


class LLMProvider(ABC):
    name: str = ""
    supports_vision: bool = False

    @abstractmethod
    def check_available(self) -> bool:
        """Return True if this provider is configured and reachable."""

    @abstractmethod
    def analyze_images(
        self,
        images: list[AnnotatedImage],
        prompt: str,
        context: ClinicalContext | None,
    ) -> AnalysisResult:
        """Run image analysis and return structured results."""

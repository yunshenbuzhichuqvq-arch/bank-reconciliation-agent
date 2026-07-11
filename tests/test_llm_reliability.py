from typing import Literal

import pytest
from pydantic import ValidationError

from bank_reconciliation_agent.core.config import Settings, settings
from bank_reconciliation_agent.core.llm.provider import (
    DeepSeekProvider,
    FakeLLMProvider,
    LLMResult,
    get_llm_provider,
)
from bank_reconciliation_agent.core.llm.reliability import (
    CircuitBreakingLLMProvider,
    LLMAttemptRecord,
    LLMCallError,
    LLMFailureType,
    RetryingLLMProvider,
    classify_llm_exception,
)
from bank_reconciliation_agent.services.circuit_breaker import CircuitBreaker


class FakeTimeout(TimeoutError):
    pass


class FakeStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class FakeConnectionError(Exception):
    pass


class FailingClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.chat = self
        self.completions = self
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        raise self._exc


def _deepseek(exc: Exception) -> DeepSeekProvider:
    return DeepSeekProvider(
        api_key="test-key",
        model="deepseek-v4-pro",
        client=FailingClient(exc),
    )


def _no_secret(reason: str) -> bool:
    lowered = reason.lower()
    return "test-key" not in lowered and "traceback" not in lowered


# --- Step 1: classification -------------------------------------------------


def test_failure_types_are_importable() -> None:
    expected: set[LLMFailureType] = {
        "timeout",
        "rate_limited",
        "provider_5xx",
        "auth_config",
        "invalid_json",
        "schema_invalid",
    }
    assert expected == set(LLMFailureType.__args__)


def test_deepseek_maps_timeout_to_retryable_timeout() -> None:
    with pytest.raises(LLMCallError) as excinfo:
        _deepseek(FakeTimeout("slow")).complete([{"role": "user", "content": "x"}])

    err = excinfo.value
    assert err.failure_type == "timeout"
    assert err.retryable is True
    assert _no_secret(err.sanitized_reason)


def test_deepseek_maps_429_to_retryable_rate_limited() -> None:
    with pytest.raises(LLMCallError) as excinfo:
        _deepseek(FakeStatusError(429)).complete([{"role": "user", "content": "x"}])

    err = excinfo.value
    assert err.failure_type == "rate_limited"
    assert err.retryable is True
    assert _no_secret(err.sanitized_reason)


def test_deepseek_maps_5xx_to_retryable_provider_5xx() -> None:
    for status in (500, 503):
        with pytest.raises(LLMCallError) as excinfo:
            _deepseek(FakeStatusError(status)).complete([{"role": "user", "content": "x"}])
        err = excinfo.value
        assert err.failure_type == "provider_5xx"
        assert err.retryable is True


def test_deepseek_maps_auth_and_missing_key_to_nonretryable_auth_config() -> None:
    with pytest.raises(LLMCallError) as excinfo:
        _deepseek(FakeStatusError(401)).complete([{"role": "user", "content": "x"}])
    assert excinfo.value.failure_type == "auth_config"
    assert excinfo.value.retryable is False

    with pytest.raises(LLMCallError) as missing:
        DeepSeekProvider(api_key=None, model="deepseek-v4-pro").complete(
            [{"role": "user", "content": "x"}]
        )
    assert missing.value.failure_type == "auth_config"
    assert missing.value.retryable is False


def test_deepseek_maps_connection_failure_to_provider_5xx() -> None:
    with pytest.raises(LLMCallError) as excinfo:
        _deepseek(FakeConnectionError("network down")).complete(
            [{"role": "user", "content": "x"}]
        )
    err = excinfo.value
    assert err.failure_type == "provider_5xx"
    assert err.retryable is True


def test_classify_unknown_exception_fails_closed_to_provider_5xx() -> None:
    err = classify_llm_exception(RuntimeError("mystery"))
    assert err.failure_type == "provider_5xx"
    assert err.retryable is True


# --- retry helpers ----------------------------------------------------------


class SequenceProvider:
    model = "seq-model"

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: Literal["text", "json_object"] = "json_object",
        response_validator=None,
    ) -> LLMResult:
        del messages, temperature, response_format, response_validator
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _result() -> LLMResult:
    return LLMResult(
        text='{"ok": true}',
        prompt_tokens=10,
        completion_tokens=5,
        model="seq-model",
    )


def _error(failure_type: LLMFailureType, retryable: bool) -> LLMCallError:
    return LLMCallError(
        failure_type=failure_type,
        retryable=retryable,
        sanitized_reason=f"{failure_type} failure",
    )


def _make_retrying(inner: SequenceProvider, sleeps: list[float]) -> RetryingLLMProvider:
    return RetryingLLMProvider(
        inner,
        max_attempts=3,
        backoff_base_seconds=0.5,
        backoff_max_seconds=2.0,
        sleep_fn=sleeps.append,
        time_fn=lambda: 0.0,
    )


# --- Step 4: retry / backoff / attempt records ------------------------------


def test_retrying_provider_recovers_on_third_attempt() -> None:
    sleeps: list[float] = []
    inner = SequenceProvider([
        _error("timeout", True),
        _error("provider_5xx", True),
        _result(),
    ])
    provider = _make_retrying(inner, sleeps)

    result = provider.complete([{"role": "user", "content": "x"}])

    assert inner.calls == 3
    assert result.text == '{"ok": true}'
    assert sleeps == [0.5, 1.0]
    assert [record.outcome for record in result.attempts] == [
        "failure",
        "failure",
        "success",
    ]


def test_retrying_provider_stops_after_three_failures() -> None:
    sleeps: list[float] = []
    inner = SequenceProvider([
        _error("timeout", True),
        _error("timeout", True),
        _error("provider_5xx", True),
    ])
    provider = _make_retrying(inner, sleeps)

    with pytest.raises(LLMCallError) as excinfo:
        provider.complete([{"role": "user", "content": "x"}])

    assert inner.calls == 3
    assert sleeps == [0.5, 1.0]
    assert excinfo.value.failure_type == "provider_5xx"
    assert len(excinfo.value.attempts) == 3


def test_retrying_provider_does_not_retry_auth_config() -> None:
    sleeps: list[float] = []
    inner = SequenceProvider([_error("auth_config", False)])
    provider = _make_retrying(inner, sleeps)

    with pytest.raises(LLMCallError) as excinfo:
        provider.complete([{"role": "user", "content": "x"}])

    assert inner.calls == 1
    assert sleeps == []
    assert excinfo.value.failure_type == "auth_config"


def test_retrying_provider_uses_bounded_exponential_backoff() -> None:
    sleeps: list[float] = []
    inner = SequenceProvider([
        _error("timeout", True),
        _error("timeout", True),
        _error("timeout", True),
    ])
    provider = RetryingLLMProvider(
        inner,
        max_attempts=3,
        backoff_base_seconds=1.0,
        backoff_max_seconds=1.5,
        sleep_fn=sleeps.append,
        time_fn=lambda: 0.0,
    )

    with pytest.raises(LLMCallError):
        provider.complete([{"role": "user", "content": "x"}])

    assert sleeps == [1.0, 1.5]


def test_retrying_provider_emits_one_attempt_record_per_physical_call() -> None:
    sleeps: list[float] = []
    inner = SequenceProvider([
        _error("timeout", True),
        _error("timeout", True),
        _error("timeout", True),
    ])
    provider = _make_retrying(inner, sleeps)

    with pytest.raises(LLMCallError) as excinfo:
        provider.complete([{"role": "user", "content": "x"}])

    attempts = excinfo.value.attempts
    assert [record.physical_attempt for record in attempts] == [1, 2, 3]
    assert all(isinstance(record, LLMAttemptRecord) for record in attempts)


# --- Step 6: breaker classification and transitions -------------------------


class BreakerInner:
    model = "breaker-inner"

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: Literal["text", "json_object"] = "json_object",
        response_validator=None,
    ) -> LLMResult:
        del messages, temperature, response_format, response_validator
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_llm_breaker_counts_timeout_and_5xx_only() -> None:
    breaker = CircuitBreaker(fail_threshold=2, open_seconds=30, time_fn=lambda: 0.0)
    inner = BreakerInner([_error("timeout", True), _error("provider_5xx", True)])
    provider = CircuitBreakingLLMProvider(inner, breaker, time_fn=lambda: 0.0)

    for _ in range(2):
        with pytest.raises(LLMCallError):
            provider.complete([{"role": "user", "content": "x"}])

    assert breaker.state == "OPEN"


def test_llm_breaker_does_not_count_429_or_auth_config() -> None:
    breaker = CircuitBreaker(fail_threshold=2, open_seconds=30, time_fn=lambda: 0.0)
    inner = BreakerInner([
        _error("rate_limited", True),
        _error("auth_config", False),
        _error("rate_limited", True),
    ])
    provider = CircuitBreakingLLMProvider(inner, breaker, time_fn=lambda: 0.0)

    for _ in range(3):
        with pytest.raises(LLMCallError):
            provider.complete([{"role": "user", "content": "x"}])

    assert breaker.state == "CLOSED"


def test_llm_breaker_open_rejects_without_calling_inner() -> None:
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=30, time_fn=lambda: 0.0)
    inner = BreakerInner([_error("timeout", True)])
    provider = CircuitBreakingLLMProvider(inner, breaker, time_fn=lambda: 0.0)

    with pytest.raises(LLMCallError):
        provider.complete([{"role": "user", "content": "x"}])

    assert breaker.state == "OPEN"

    with pytest.raises(LLMCallError) as rejected:
        provider.complete([{"role": "user", "content": "x"}])

    assert inner.calls == 1
    err = rejected.value
    assert err.retryable is False
    assert err.attempts[0].outcome == "breaker_open"


def test_llm_breaker_half_open_success_closes() -> None:
    clock = [0.0]
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=10, time_fn=lambda: clock[0])
    inner = BreakerInner([_error("timeout", True), _result()])
    provider = CircuitBreakingLLMProvider(inner, breaker, time_fn=lambda: clock[0])

    with pytest.raises(LLMCallError):
        provider.complete([{"role": "user", "content": "x"}])
    assert breaker.state == "OPEN"

    clock[0] = 11.0
    result = provider.complete([{"role": "user", "content": "x"}])

    assert result.text == '{"ok": true}'
    assert breaker.state == "CLOSED"
    assert result.attempts[0].breaker_state_after == "CLOSED"


def test_llm_breaker_half_open_failure_reopens() -> None:
    clock = [0.0]
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=10, time_fn=lambda: clock[0])
    inner = BreakerInner([_error("provider_5xx", True), _error("provider_5xx", True)])
    provider = CircuitBreakingLLMProvider(inner, breaker, time_fn=lambda: clock[0])

    with pytest.raises(LLMCallError):
        provider.complete([{"role": "user", "content": "x"}])
    assert breaker.state == "OPEN"

    clock[0] = 11.0
    with pytest.raises(LLMCallError):
        provider.complete([{"role": "user", "content": "x"}])

    assert breaker.state == "OPEN"


# --- Step 8: config validation and factory nesting --------------------------


def test_llm_reliability_settings_defaults() -> None:
    fresh = Settings()
    assert fresh.llm_timeout_seconds == 30.0
    assert fresh.llm_max_attempts == 3
    assert fresh.llm_backoff_base_seconds == 0.5
    assert fresh.llm_backoff_max_seconds == 2.0
    assert fresh.llm_breaker_fail_threshold == 3
    assert fresh.llm_breaker_open_seconds == 30


def test_llm_reliability_settings_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        Settings(llm_max_attempts=0)
    with pytest.raises(ValidationError):
        Settings(llm_max_attempts=4)
    with pytest.raises(ValidationError):
        Settings(llm_timeout_seconds=-1.0)
    with pytest.raises(ValidationError):
        Settings(llm_backoff_base_seconds=-0.1)
    with pytest.raises(ValidationError):
        Settings(llm_backoff_max_seconds=0.1)


def test_factory_deepseek_nests_caching_retrying_ratelimit_breaker(monkeypatch) -> None:
    from fakeredis import FakeStrictRedis
    import redis

    from bank_reconciliation_agent.core.llm.cache import CachingLLMProvider
    from bank_reconciliation_agent.core.llm.rate_limit import RateLimitedLLMProvider

    redis_client = FakeStrictRedis()
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(settings, "enable_llm_cache", True)
    monkeypatch.setattr(settings, "enable_llm_rate_limit", True)
    monkeypatch.setattr(redis.Redis, "from_url", lambda *a, **k: redis_client)

    provider = get_llm_provider()

    assert isinstance(provider, CachingLLMProvider)
    retrying = provider.inner
    assert isinstance(retrying, RetryingLLMProvider)
    rate_limited = retrying.inner
    assert isinstance(rate_limited, RateLimitedLLMProvider)
    breaking = rate_limited.inner
    assert isinstance(breaking, CircuitBreakingLLMProvider)
    assert isinstance(breaking.inner, DeepSeekProvider)


def test_factory_fake_has_no_retry_or_breaker(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "fake")
    monkeypatch.setattr(settings, "enable_llm_cache", False)
    monkeypatch.setattr(settings, "enable_llm_rate_limit", False)

    provider = get_llm_provider()

    assert isinstance(provider, FakeLLMProvider)


def test_factory_deepseek_without_wrappers_starts_with_retrying(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(settings, "enable_llm_cache", False)
    monkeypatch.setattr(settings, "enable_llm_rate_limit", False)

    provider = get_llm_provider()

    assert isinstance(provider, RetryingLLMProvider)
    assert isinstance(provider.inner, CircuitBreakingLLMProvider)
    assert isinstance(provider.inner.inner, DeepSeekProvider)

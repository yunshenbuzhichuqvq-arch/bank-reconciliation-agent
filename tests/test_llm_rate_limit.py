from typing import Literal

from fakeredis import FakeStrictRedis
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from structlog.testing import capture_logs

from bank_reconciliation_agent.core.llm.provider import LLMResult, LLMUnavailable
from bank_reconciliation_agent.core.llm.rate_limit import RateLimitedLLMProvider


class CountingProvider:
    model = "test-model"

    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: Literal["text", "json_object"] = "json_object",
    ) -> LLMResult:
        del messages, temperature, response_format
        self.calls += 1
        return LLMResult(
            text="limited response",
            prompt_tokens=12,
            completion_tokens=4,
            model=self.model,
        )


class FailingRedis:
    def incr(self, key: str) -> int:
        del key
        raise RedisConnectionError("redis unavailable")


@pytest.fixture(autouse=True)
def reset_metrics() -> None:
    RateLimitedLLMProvider._waits = 0
    RateLimitedLLMProvider._wait_seconds_total = 0.0
    RateLimitedLLMProvider._rejections = 0
    RateLimitedLLMProvider._degraded = 0


def make_provider(
    inner: CountingProvider,
    redis_client,
    *,
    rpm: int = 60,
    max_concurrency: int = 8,
    max_wait_seconds: float = 1.0,
    window_seconds: int = 60,
) -> RateLimitedLLMProvider:
    return RateLimitedLLMProvider(
        inner,
        redis_client,
        rpm=rpm,
        max_concurrency=max_concurrency,
        max_wait_seconds=max_wait_seconds,
        window_seconds=window_seconds,
    )


def test_within_limits_calls_inner_and_releases_concurrency() -> None:
    inner = CountingProvider()
    redis_client = FakeStrictRedis()
    provider = make_provider(inner, redis_client)

    result = provider.complete([{"role": "user", "content": "reconcile"}])

    assert provider.model == "test-model"
    assert result.text == "limited response"
    assert inner.calls == 1
    assert int(redis_client.get("llmratelimit:concurrency")) == 0
    rpm_keys = redis_client.keys("llmratelimit:rpm:*")
    assert len(rpm_keys) == 1
    assert int(redis_client.get(rpm_keys[0])) == 1


def test_rpm_limit_waits_until_next_window(monkeypatch: pytest.MonkeyPatch) -> None:
    inner = CountingProvider()
    redis_client = FakeStrictRedis()
    clock = [100.0]
    monkeypatch.setattr("bank_reconciliation_agent.core.llm.rate_limit.time.time", lambda: clock[0])
    monkeypatch.setattr(
        "bank_reconciliation_agent.core.llm.rate_limit.time.sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    provider = make_provider(inner, redis_client, rpm=1, window_seconds=1)

    provider.complete([])
    with capture_logs() as logs:
        provider.complete([])

    assert inner.calls == 2
    assert int(redis_client.get("llmratelimit:rpm:101")) == 1
    assert any(
        entry["event"] == "llm_rate_limited" and entry["dimension"] == "rpm"
        for entry in logs
    )


def test_concurrency_limit_waits_until_slot_is_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = CountingProvider()
    redis_client = FakeStrictRedis()
    redis_client.set("llmratelimit:concurrency", 1)
    clock = [100.0]

    def release_slot(seconds: float) -> None:
        clock[0] += seconds
        redis_client.decr("llmratelimit:concurrency")

    monkeypatch.setattr("bank_reconciliation_agent.core.llm.rate_limit.time.time", lambda: clock[0])
    monkeypatch.setattr("bank_reconciliation_agent.core.llm.rate_limit.time.sleep", release_slot)
    provider = make_provider(inner, redis_client, max_concurrency=1)

    provider.complete([])

    assert inner.calls == 1
    assert int(redis_client.get("llmratelimit:concurrency")) == 0
    assert redis_client.ttl("llmratelimit:concurrency") > 0


def test_wait_timeout_raises_llm_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    inner = CountingProvider()
    redis_client = FakeStrictRedis()
    redis_client.set("llmratelimit:concurrency", 1)
    clock = [100.0]
    monkeypatch.setattr("bank_reconciliation_agent.core.llm.rate_limit.time.time", lambda: clock[0])
    monkeypatch.setattr(
        "bank_reconciliation_agent.core.llm.rate_limit.time.sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    provider = make_provider(inner, redis_client, max_concurrency=1, max_wait_seconds=0.05)

    with pytest.raises(LLMUnavailable, match="rate limit wait timeout"):
        provider.complete([])

    assert inner.calls == 0
    assert int(redis_client.get("llmratelimit:concurrency")) == 1
    assert RateLimitedLLMProvider.metrics_snapshot()["rejections"] == 1


def test_rpm_wait_timeout_releases_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    inner = CountingProvider()
    redis_client = FakeStrictRedis()
    clock = [100.0]
    monkeypatch.setattr("bank_reconciliation_agent.core.llm.rate_limit.time.time", lambda: clock[0])
    monkeypatch.setattr(
        "bank_reconciliation_agent.core.llm.rate_limit.time.sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    provider = make_provider(inner, redis_client, rpm=1, max_wait_seconds=0.05)
    provider.complete([])

    with pytest.raises(LLMUnavailable, match="rate limit wait timeout"):
        provider.complete([])

    assert int(redis_client.get("llmratelimit:concurrency")) == 0


def test_redis_error_fails_open_and_logs_degraded() -> None:
    inner = CountingProvider()
    provider = make_provider(inner, FailingRedis())

    with capture_logs() as logs:
        result = provider.complete([])

    assert result.text == "limited response"
    assert inner.calls == 1
    assert RateLimitedLLMProvider.metrics_snapshot()["degraded"] == 1
    assert any(entry["event"] == "llm_rate_limit_degraded" for entry in logs)


def test_metrics_snapshot_reports_wait_activity(monkeypatch: pytest.MonkeyPatch) -> None:
    inner = CountingProvider()
    redis_client = FakeStrictRedis()
    redis_client.set("llmratelimit:concurrency", 1)
    clock = [100.0]
    monkeypatch.setattr("bank_reconciliation_agent.core.llm.rate_limit.time.time", lambda: clock[0])
    monkeypatch.setattr(
        "bank_reconciliation_agent.core.llm.rate_limit.time.sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    provider = make_provider(inner, redis_client, max_concurrency=1, max_wait_seconds=0.05)

    with pytest.raises(LLMUnavailable):
        provider.complete([])

    assert RateLimitedLLMProvider.metrics_snapshot() == {
        "waits": 1,
        "wait_seconds_total": pytest.approx(0.1),
        "rejections": 1,
        "degraded": 0,
    }

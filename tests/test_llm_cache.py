from typing import Literal

from fakeredis import FakeStrictRedis
from redis.exceptions import ConnectionError as RedisConnectionError
from structlog.testing import capture_logs

from bank_reconciliation_agent.core.llm.cache import CachingLLMProvider
from bank_reconciliation_agent.core.llm.provider import LLMResult


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
            text="cached response",
            prompt_tokens=12,
            completion_tokens=4,
            model=self.model,
        )


class FailingRedis:
    def __init__(self, inner: FakeStrictRedis, *, failing_op: str) -> None:
        self.inner = inner
        self.failing_op = failing_op

    def get(self, key: str):
        if self.failing_op == "get":
            raise RedisConnectionError("get unavailable")
        return self.inner.get(key)

    def setex(self, key: str, ttl_seconds: int, value: str):
        if self.failing_op == "setex":
            raise RedisConnectionError("setex unavailable")
        return self.inner.setex(key, ttl_seconds, value)


def test_same_messages_hit_cache_on_second_call() -> None:
    inner = CountingProvider()
    redis_client = FakeStrictRedis()
    provider = CachingLLMProvider(inner, redis_client, ttl_seconds=60)
    messages = [{"role": "system", "content": "audit prompt v1"}]

    first = provider.complete(messages)
    second = provider.complete(messages)

    assert first.cached is False
    assert second.cached is True
    assert second.text == first.text
    assert second.prompt_tokens == first.prompt_tokens
    assert second.completion_tokens == first.completion_tokens
    assert inner.calls == 1


def test_message_change_misses_cache() -> None:
    inner = CountingProvider()
    provider = CachingLLMProvider(inner, FakeStrictRedis(), ttl_seconds=60)

    provider.complete([{"role": "system", "content": "audit prompt v1"}])
    changed = provider.complete([{"role": "system", "content": "audit prompt v2"}])

    assert changed.cached is False
    assert inner.calls == 2


def test_cache_entry_has_ttl() -> None:
    redis_client = FakeStrictRedis()
    provider = CachingLLMProvider(CountingProvider(), redis_client, ttl_seconds=60)

    provider.complete([{"role": "user", "content": "reconcile"}])

    keys = redis_client.keys("llmcache:v1:*")
    assert len(keys) == 1
    assert 0 < redis_client.ttl(keys[0]) <= 60


def test_redis_get_error_degrades_to_inner_provider() -> None:
    inner = CountingProvider()
    provider = CachingLLMProvider(
        inner,
        FailingRedis(FakeStrictRedis(), failing_op="get"),
        ttl_seconds=60,
    )

    with capture_logs() as logs:
        result = provider.complete([{"role": "user", "content": "reconcile"}])

    assert result.cached is False
    assert inner.calls == 1
    assert provider.degraded_count == 1
    assert any(
        entry["event"] == "llm_cache_degraded" and entry["op"] == "get"
        for entry in logs
    )


def test_redis_setex_error_degrades_without_repeating_llm_call() -> None:
    inner = CountingProvider()
    provider = CachingLLMProvider(
        inner,
        FailingRedis(FakeStrictRedis(), failing_op="setex"),
        ttl_seconds=60,
    )

    with capture_logs() as logs:
        result = provider.complete([{"role": "user", "content": "reconcile"}])

    assert result.cached is False
    assert inner.calls == 1
    assert provider.degraded_count == 1
    assert any(
        entry["event"] == "llm_cache_degraded" and entry["op"] == "setex"
        for entry in logs
    )

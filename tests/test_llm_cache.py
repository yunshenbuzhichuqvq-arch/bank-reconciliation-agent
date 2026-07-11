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

    def delete(self, key: str):
        if self.failing_op == "delete":
            raise RedisConnectionError("delete unavailable")
        return self.inner.delete(key)


class TextSequenceProvider:
    model = "seq-model"

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
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
            text=self._texts.pop(0),
            prompt_tokens=7,
            completion_tokens=3,
            model=self.model,
        )


def _accepts_valid(text: str) -> bool:
    return text == "valid"


def _seed(redis_client: FakeStrictRedis, provider: CachingLLMProvider, messages, text: str) -> str:
    key = provider._cache_key(messages, temperature=0.0, response_format="json_object")
    redis_client.set(
        key,
        LLMResult(text=text, prompt_tokens=7, completion_tokens=3, model="seq-model").model_dump_json(),
    )
    return key


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


def test_cache_hit_logs_model_and_short_cache_key() -> None:
    provider = CachingLLMProvider(CountingProvider(), FakeStrictRedis(), ttl_seconds=60)
    messages = [{"role": "system", "content": "audit prompt v1"}]
    provider.complete(messages)

    with capture_logs() as logs:
        provider.complete(messages)

    hit = next(entry for entry in logs if entry["event"] == "llm_cache_hit")
    assert hit["model"] == "test-model"
    assert hit["cache_key"].startswith("llmcache:v1:")
    assert len(hit["cache_key"]) < len(provider._cache_key(
        messages,
        temperature=0.0,
        response_format="json_object",
    ))


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


def test_cache_writes_only_when_response_validator_accepts() -> None:
    inner = TextSequenceProvider(["valid"])
    redis_client = FakeStrictRedis()
    provider = CachingLLMProvider(inner, redis_client, ttl_seconds=60)
    messages = [{"role": "user", "content": "reconcile"}]

    result = provider.complete(messages, response_validator=_accepts_valid)

    assert result.text == "valid"
    assert len(redis_client.keys("llmcache:v1:*")) == 1


def test_cache_returns_fresh_invalid_result_without_storing_it() -> None:
    inner = TextSequenceProvider(["invalid"])
    redis_client = FakeStrictRedis()
    provider = CachingLLMProvider(inner, redis_client, ttl_seconds=60)
    messages = [{"role": "user", "content": "reconcile"}]

    result = provider.complete(messages, response_validator=_accepts_valid)

    assert result.text == "invalid"
    assert result.cached is False
    assert inner.calls == 1
    assert redis_client.keys("llmcache:v1:*") == []


def test_invalid_cached_value_is_deleted_and_refetched() -> None:
    inner = TextSequenceProvider(["valid"])
    redis_client = FakeStrictRedis()
    provider = CachingLLMProvider(inner, redis_client, ttl_seconds=60)
    messages = [{"role": "user", "content": "reconcile"}]
    key = _seed(redis_client, provider, messages, "invalid")

    with capture_logs() as logs:
        result = provider.complete(messages, response_validator=_accepts_valid)

    assert result.text == "valid"
    assert inner.calls == 1
    assert any(entry["event"] == "llm_cache_evict_invalid" for entry in logs)
    assert redis_client.get(key) is not None
    hit = provider.complete(messages, response_validator=_accepts_valid)
    assert hit.cached is True
    assert inner.calls == 1


def test_valid_cache_hit_does_not_call_inner() -> None:
    inner = TextSequenceProvider([])
    redis_client = FakeStrictRedis()
    provider = CachingLLMProvider(inner, redis_client, ttl_seconds=60)
    messages = [{"role": "user", "content": "reconcile"}]
    _seed(redis_client, provider, messages, "valid")

    result = provider.complete(messages, response_validator=_accepts_valid)

    assert result.cached is True
    assert result.text == "valid"
    assert inner.calls == 0


def test_cache_delete_failure_degrades_without_returning_invalid_value() -> None:
    backing = FakeStrictRedis()
    inner = TextSequenceProvider(["valid"])
    provider = CachingLLMProvider(
        inner,
        FailingRedis(backing, failing_op="delete"),
        ttl_seconds=60,
    )
    messages = [{"role": "user", "content": "reconcile"}]
    _seed(backing, provider, messages, "invalid")

    with capture_logs() as logs:
        result = provider.complete(messages, response_validator=_accepts_valid)

    assert result.text == "valid"
    assert inner.calls == 1
    assert any(
        entry["event"] == "llm_cache_degraded" and entry["op"] == "delete"
        for entry in logs
    )

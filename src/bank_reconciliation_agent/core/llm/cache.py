import hashlib
import json
from threading import Lock
from typing import Any, ClassVar, Literal

import structlog
from redis.exceptions import RedisError

from bank_reconciliation_agent.core.llm.provider import (
    LLMProvider,
    LLMResult,
    ResponseValidator,
)


log = structlog.get_logger()


class CachingLLMProvider:
    _metrics_lock: ClassVar[Lock] = Lock()
    _hits: ClassVar[int] = 0
    _misses: ClassVar[int] = 0
    _saved_prompt_tokens: ClassVar[int] = 0
    _saved_completion_tokens: ClassVar[int] = 0

    def __init__(
        self,
        inner: LLMProvider,
        redis_client: Any,
        *,
        ttl_seconds: int,
    ) -> None:
        self.inner = inner
        self.redis_client = redis_client
        self.ttl_seconds = ttl_seconds
        self.degraded_count = 0

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: Literal["text", "json_object"] = "json_object",
        response_validator: ResponseValidator | None = None,
    ) -> LLMResult:
        cache_key = self._cache_key(
            messages,
            temperature=temperature,
            response_format=response_format,
        )
        try:
            cached_value = self.redis_client.get(cache_key)
        except RedisError as exc:
            self._log_degraded("get", exc)
            return self._complete_inner(
                messages,
                temperature=temperature,
                response_format=response_format,
            )

        if cached_value is not None:
            result = LLMResult.model_validate_json(cached_value).model_copy(
                update={"cached": True}
            )
            if response_validator is None or response_validator(result.text):
                with self._metrics_lock:
                    type(self)._hits += 1
                    type(self)._saved_prompt_tokens += result.prompt_tokens
                    type(self)._saved_completion_tokens += result.completion_tokens
                log.info(
                    "llm_cache_hit",
                    model=result.model,
                    cache_key=cache_key[:24],
                )
                return result
            self._evict_invalid(cache_key, result.model)

        with self._metrics_lock:
            type(self)._misses += 1
        result = self._complete_inner(
            messages,
            temperature=temperature,
            response_format=response_format,
        )
        if response_validator is None or response_validator(result.text):
            self._store(cache_key, result)
        return result

    @classmethod
    def metrics_snapshot(cls) -> dict[str, int]:
        with cls._metrics_lock:
            return {
                "hits": cls._hits,
                "misses": cls._misses,
                "saved_prompt_tokens": cls._saved_prompt_tokens,
                "saved_completion_tokens": cls._saved_completion_tokens,
            }

    def _cache_key(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        response_format: str,
    ) -> str:
        payload = json.dumps(
            {
                "messages": messages,
                "model": getattr(self.inner, "model", ""),
                "response_format": response_format,
                "temperature": temperature,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"llmcache:v1:{digest}"

    def _complete_inner(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        response_format: Literal["text", "json_object"],
    ) -> LLMResult:
        result = self.inner.complete(
            messages,
            temperature=temperature,
            response_format=response_format,
        )
        return result.model_copy(update={"cached": False})

    def _store(self, cache_key: str, result: LLMResult) -> None:
        try:
            self.redis_client.setex(
                cache_key,
                self.ttl_seconds,
                result.model_copy(update={"attempts": []}).model_dump_json(),
            )
        except RedisError as exc:
            self._log_degraded("setex", exc)

    def _evict_invalid(self, cache_key: str, model: str) -> None:
        try:
            self.redis_client.delete(cache_key)
        except RedisError as exc:
            self._log_degraded("delete", exc)
        log.info(
            "llm_cache_evict_invalid",
            model=model,
            cache_key=cache_key[:24],
        )

    def _log_degraded(self, op: str, exc: RedisError) -> None:
        self.degraded_count += 1
        log.warning(
            "llm_cache_degraded",
            op=op,
            reason=type(exc).__name__,
        )

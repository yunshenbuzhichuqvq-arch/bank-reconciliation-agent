import hashlib
import json
from typing import Any, Literal

import structlog
from redis.exceptions import RedisError

from bank_reconciliation_agent.core.llm.provider import LLMProvider, LLMResult


log = structlog.get_logger()


class CachingLLMProvider:
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
            return LLMResult.model_validate_json(cached_value).model_copy(
                update={"cached": True}
            )

        result = self._complete_inner(
            messages,
            temperature=temperature,
            response_format=response_format,
        )
        try:
            self.redis_client.setex(
                cache_key,
                self.ttl_seconds,
                result.model_dump_json(),
            )
        except RedisError as exc:
            self._log_degraded("setex", exc)
        return result

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

    def _log_degraded(self, op: str, exc: RedisError) -> None:
        self.degraded_count += 1
        log.warning(
            "llm_cache_degraded",
            op=op,
            reason=type(exc).__name__,
        )

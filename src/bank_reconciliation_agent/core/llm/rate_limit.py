import math
from threading import Lock
import time
from typing import Any, ClassVar, Literal

from redis.exceptions import RedisError
import structlog

from bank_reconciliation_agent.core.llm.provider import (
    LLMProvider,
    LLMResult,
    LLMUnavailable,
)


log = structlog.get_logger()


class RateLimitedLLMProvider:
    _metrics_lock: ClassVar[Lock] = Lock()
    _waits: ClassVar[int] = 0
    _wait_seconds_total: ClassVar[float] = 0.0
    _rejections: ClassVar[int] = 0
    _degraded: ClassVar[int] = 0
    _poll_seconds: ClassVar[float] = 0.1

    def __init__(
        self,
        inner: LLMProvider,
        redis_client: Any,
        *,
        rpm: int,
        max_concurrency: int,
        max_wait_seconds: float,
        window_seconds: int = 60,
    ) -> None:
        self.inner = inner
        self.model = getattr(inner, "model", "")
        self.redis_client = redis_client
        self.rpm = rpm
        self.max_concurrency = max_concurrency
        self.max_wait_seconds = max_wait_seconds
        self.window_seconds = window_seconds
        self._concurrency_ttl_seconds = max(60, math.ceil(max_wait_seconds) + 60)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: Literal["text", "json_object"] = "json_object",
    ) -> LLMResult:
        acquired_concurrency = False
        try:
            self._acquire_concurrency()
            acquired_concurrency = True
            self._acquire_rpm()
        except LLMUnavailable:
            if acquired_concurrency:
                self._release_concurrency_degraded()
            raise
        except RedisError as exc:
            if acquired_concurrency:
                self._release_concurrency_degraded()
            self._log_degraded("acquire", exc)
            return self.inner.complete(
                messages,
                temperature=temperature,
                response_format=response_format,
            )

        try:
            return self.inner.complete(
                messages,
                temperature=temperature,
                response_format=response_format,
            )
        finally:
            self._release_concurrency_degraded()

    @classmethod
    def metrics_snapshot(cls) -> dict[str, int | float]:
        with cls._metrics_lock:
            return {
                "waits": cls._waits,
                "wait_seconds_total": cls._wait_seconds_total,
                "rejections": cls._rejections,
                "degraded": cls._degraded,
            }

    def _acquire_concurrency(self) -> None:
        started_at: float | None = None
        while True:
            count = self.redis_client.incr("llmratelimit:concurrency")
            self.redis_client.expire(
                "llmratelimit:concurrency",
                self._concurrency_ttl_seconds,
            )
            if count <= self.max_concurrency:
                if started_at is not None:
                    self._record_wait("concurrency", started_at)
                return

            self.redis_client.decr("llmratelimit:concurrency")
            if started_at is None:
                started_at = time.time()
            self._sleep_or_reject("concurrency", started_at)

    def _acquire_rpm(self) -> None:
        started_at: float | None = None
        denied_window: int | None = None
        while True:
            window_start = self._window_start()
            if denied_window == window_start:
                self._sleep_or_reject("rpm", started_at)
                continue

            key = f"llmratelimit:rpm:{window_start}"
            count = self.redis_client.incr(key)
            if count == 1:
                self.redis_client.expire(key, self.window_seconds)
            if count <= self.rpm:
                if started_at is not None:
                    self._record_wait("rpm", started_at)
                return

            denied_window = window_start
            if started_at is None:
                started_at = time.time()
            self._sleep_or_reject("rpm", started_at)

    def _window_start(self) -> int:
        now = int(time.time())
        return now - (now % self.window_seconds)

    def _sleep_or_reject(self, dimension: str, started_at: float | None) -> None:
        if started_at is None:
            return
        if time.time() - started_at >= self.max_wait_seconds:
            self._record_wait(dimension, started_at, rejected=True)
            raise LLMUnavailable("rate limit wait timeout")
        time.sleep(self._poll_seconds)

    def _record_wait(
        self,
        dimension: str,
        started_at: float,
        *,
        rejected: bool = False,
    ) -> None:
        waited = time.time() - started_at
        with self._metrics_lock:
            type(self)._waits += 1
            type(self)._wait_seconds_total += waited
            if rejected:
                type(self)._rejections += 1
        log.info("llm_rate_limited", dimension=dimension, waited=waited)

    def _release_concurrency_degraded(self) -> None:
        try:
            self.redis_client.decr("llmratelimit:concurrency")
        except RedisError as exc:
            self._log_degraded("release_concurrency", exc)

    def _log_degraded(self, op: str, exc: RedisError) -> None:
        with self._metrics_lock:
            type(self)._degraded += 1
        log.warning(
            "llm_rate_limit_degraded",
            op=op,
            reason=type(exc).__name__,
        )

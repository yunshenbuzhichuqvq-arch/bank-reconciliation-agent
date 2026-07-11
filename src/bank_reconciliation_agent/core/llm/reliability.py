from __future__ import annotations

import time
from typing import Callable
from uuid import uuid4

import structlog

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.llm.provider import (
    LLMAttemptRecord,
    LLMCallError,
    LLMFailureType,
    LLMProvider,
    LLMResult,
    ResponseValidator,
    classify_llm_exception,
)
from bank_reconciliation_agent.services.circuit_breaker import CircuitBreaker


log = structlog.get_logger()


__all__ = [
    "CircuitBreakingLLMProvider",
    "LLMAttemptRecord",
    "LLMCallError",
    "LLMFailureType",
    "RetryingLLMProvider",
    "classify_llm_exception",
    "get_llm_breaker",
]


_BREAKER_FAILURE_TYPES: frozenset[str] = frozenset({"timeout", "provider_5xx"})

_llm_breaker: CircuitBreaker | None = None


def get_llm_breaker() -> CircuitBreaker:
    """Return the process-wide LLM circuit breaker shared by real providers."""

    global _llm_breaker
    if _llm_breaker is None:
        _llm_breaker = CircuitBreaker(
            fail_threshold=settings.llm_breaker_fail_threshold,
            open_seconds=settings.llm_breaker_open_seconds,
        )
    return _llm_breaker


class CircuitBreakingLLMProvider:
    """Wrap the real provider with a shared circuit breaker.

    Only ``timeout`` and ``provider_5xx`` failures count as upstream
    availability failures. Each call that reaches the inner provider gets a
    single attempt record carrying breaker state before/after.
    """

    def __init__(
        self,
        inner: LLMProvider,
        breaker: CircuitBreaker,
        *,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.inner = inner
        self.breaker = breaker
        self.model = getattr(inner, "model", "")
        self._time_fn = time_fn
        self._last_failure_type: LLMFailureType | None = None

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
        response_validator: ResponseValidator | None = None,
    ) -> LLMResult:
        state_before = self.breaker.state
        if not self.breaker.allow_request():
            record = LLMAttemptRecord(
                physical_attempt=1,
                outcome="breaker_open",
                failure_type=self._last_failure_type,
                duration_ms=0,
                breaker_state_before=state_before,
                breaker_state_after=state_before,
            )
            raise LLMCallError(
                failure_type=self._last_failure_type or "provider_5xx",
                retryable=False,
                sanitized_reason="LLM circuit breaker open",
                attempts=[record],
                fallback_reason="breaker_open",
            )

        started_at = self._time_fn()
        try:
            result = self.inner.complete(
                messages,
                temperature=temperature,
                response_format=response_format,
                response_validator=response_validator,
            )
        except LLMCallError as exc:
            duration_ms = self._elapsed_ms(started_at)
            if exc.failure_type in _BREAKER_FAILURE_TYPES:
                self._last_failure_type = exc.failure_type
                state_after = self.breaker.record_failure()
            else:
                state_after = self.breaker.state
            exc.attempts = [
                LLMAttemptRecord(
                    physical_attempt=1,
                    outcome="failure",
                    failure_type=exc.failure_type,
                    duration_ms=duration_ms,
                    breaker_state_before=state_before,
                    breaker_state_after=state_after,
                )
            ]
            raise

        duration_ms = self._elapsed_ms(started_at)
        state_after = self.breaker.record_success()
        record = LLMAttemptRecord(
            physical_attempt=1,
            outcome="success",
            duration_ms=duration_ms,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            breaker_state_before=state_before,
            breaker_state_after=state_after,
        )
        return result.model_copy(update={"attempts": [record]})

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((self._time_fn() - started_at) * 1000))


class RetryingLLMProvider:
    """Bounded retry with exponential backoff for retryable transport errors."""

    def __init__(
        self,
        inner: LLMProvider,
        *,
        max_attempts: int,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
        sleep_fn: Callable[[float], None] = time.sleep,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.inner = inner
        self.model = getattr(inner, "model", "")
        self.max_attempts = max_attempts
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self._sleep_fn = sleep_fn
        self._time_fn = time_fn

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
        response_validator: ResponseValidator | None = None,
    ) -> LLMResult:
        logical_call_id = uuid4().hex[:12]
        aggregated: list[LLMAttemptRecord] = []

        for attempt_no in range(1, self.max_attempts + 1):
            started_at = self._time_fn()
            try:
                result = self.inner.complete(
                    messages,
                    temperature=temperature,
                    response_format=response_format,
                    response_validator=response_validator,
                )
            except LLMCallError as exc:
                duration_ms = max(0, int((self._time_fn() - started_at) * 1000))
                records = list(exc.attempts) or [
                    LLMAttemptRecord(
                        physical_attempt=attempt_no,
                        outcome="failure",
                        failure_type=exc.failure_type,
                        duration_ms=duration_ms,
                    )
                ]
                aggregated.extend(records)

                should_retry = exc.retryable and attempt_no < self.max_attempts
                if should_retry:
                    backoff = min(
                        self.backoff_base_seconds * (2 ** (attempt_no - 1)),
                        self.backoff_max_seconds,
                    )
                    aggregated[-1] = aggregated[-1].model_copy(
                        update={"backoff_seconds": backoff}
                    )
                    self._renumber(aggregated)
                    self._log_attempts(logical_call_id, aggregated[-len(records):])
                    self._sleep_fn(backoff)
                    continue

                self._renumber(aggregated)
                self._log_attempts(logical_call_id, aggregated[-len(records):])
                exc.attempts = aggregated
                raise

            records = list(result.attempts) or [
                LLMAttemptRecord(
                    physical_attempt=attempt_no,
                    outcome="success",
                    duration_ms=max(0, int((self._time_fn() - started_at) * 1000)),
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                )
            ]
            aggregated.extend(records)
            self._renumber(aggregated)
            self._log_attempts(logical_call_id, aggregated[-len(records):])
            return result.model_copy(update={"attempts": aggregated})

        raise LLMCallError(  # pragma: no cover - loop always returns or raises
            failure_type="provider_5xx",
            retryable=False,
            sanitized_reason="LLM retry loop exhausted",
            attempts=aggregated,
        )

    @staticmethod
    def _renumber(records: list[LLMAttemptRecord]) -> None:
        for index, record in enumerate(records, start=1):
            record.physical_attempt = index

    def _log_attempts(
        self, logical_call_id: str, records: list[LLMAttemptRecord]
    ) -> None:
        for record in records:
            log.info(
                "llm_attempt",
                logical_call_id=logical_call_id,
                physical_attempt=record.physical_attempt,
                provider=self.model,
                outcome=record.outcome,
                failure_type=record.failure_type,
                duration_ms=record.duration_ms,
                backoff_seconds=record.backoff_seconds,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                breaker_state_before=record.breaker_state_before,
                breaker_state_after=record.breaker_state_after,
            )

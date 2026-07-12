from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Callable, Mapping

from pydantic import BaseModel, ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.schemas.tools import (
    ConfirmedCasesOutput,
    SearchRulesOutput,
    T1ContextOutput,
    ToolAttemptRecord,
    ToolCallResult,
    ToolContext,
    ToolErrorType,
)


SHARED_EXECUTOR_MAX_WORKERS = 4

_FALLBACK_REASONS: dict[ToolErrorType, str] = {
    "UNKNOWN_TOOL": "TOOL_UNKNOWN",
    "VALIDATION_ERROR": "TOOL_INPUT_INVALID",
    "PERMISSION_DENIED": "TOOL_ACCESS_DENIED",
    "TIMEOUT": "TOOL_TIMEOUT",
    "TRANSIENT_READ_ERROR": "TOOL_TRANSIENT_READ_ERROR",
    "INTERNAL_ERROR": "TOOL_INTERNAL_ERROR",
    "CIRCUIT_OPEN": "RAG_CIRCUIT_OPEN",
}

_RETRYABLE_ERRORS: frozenset[ToolErrorType] = frozenset({"TIMEOUT", "TRANSIENT_READ_ERROR"})


class ToolTransientError(Exception):
    """Raised by an adapter to signal a retryable transient read failure."""


class CircuitOpenError(Exception):
    """Raised by an adapter when a protecting circuit breaker is OPEN."""


@dataclass(frozen=True)
class ToolPolicy:
    timeout_s: float
    max_attempts: int
    backoff_s: float


TOOL_POLICIES: dict[str, ToolPolicy] = {
    "search_rules": ToolPolicy(timeout_s=30.0, max_attempts=2, backoff_s=0.05),
    "load_confirmed_cases": ToolPolicy(timeout_s=5.0, max_attempts=2, backoff_s=0.05),
    "lookup_t1_context": ToolPolicy(timeout_s=5.0, max_attempts=2, backoff_s=0.05),
}


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    adapter: Callable[[BaseModel, ToolContext], object | None]
    scenario_predicate: Callable[[ToolContext], bool]
    policy: ToolPolicy


_shared_executor: ThreadPoolExecutor | None = None


def get_shared_executor() -> ThreadPoolExecutor:
    global _shared_executor
    if _shared_executor is None:
        _shared_executor = ThreadPoolExecutor(
            max_workers=SHARED_EXECUTOR_MAX_WORKERS,
            thread_name_prefix="tool-executor",
        )
    return _shared_executor


class _ToolFailure(Exception):
    def __init__(self, error_type: ToolErrorType) -> None:
        super().__init__(error_type)
        self.error_type = error_type


class ToolExecutor:
    def __init__(
        self,
        registry: Mapping[str, ToolDefinition],
        authorizer: Callable[[ToolContext], bool],
        *,
        executor: ThreadPoolExecutor | None = None,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._registry = dict(registry)
        self._authorizer = authorizer
        self._executor = executor
        self._sleeper = sleeper or time.sleep
        self._clock = clock or time.monotonic

    def execute(
        self,
        name: str,
        args: BaseModel | Mapping[str, object],
        context: ToolContext | Mapping[str, object],
    ) -> ToolCallResult:
        overall_start = self._clock()

        definition = self._registry.get(name)
        if definition is None:
            return self._pre_adapter_failure(name, "UNKNOWN_TOOL", overall_start)

        try:
            ctx = ToolContext.model_validate(context)
        except ValidationError:
            return self._pre_adapter_failure(name, "VALIDATION_ERROR", overall_start)

        try:
            args_model = definition.input_schema.model_validate(args)
        except ValidationError:
            return self._pre_adapter_failure(name, "VALIDATION_ERROR", overall_start)

        if not self._authorizer(ctx) or not definition.scenario_predicate(ctx):
            return self._pre_adapter_failure(name, "PERMISSION_DENIED", overall_start)

        return self._run_attempts(definition, args_model, ctx, overall_start)

    def _run_attempts(
        self,
        definition: ToolDefinition,
        args_model: BaseModel,
        ctx: ToolContext,
        overall_start: float,
    ) -> ToolCallResult:
        policy = definition.policy
        records: list[ToolAttemptRecord] = []

        for attempt in range(1, policy.max_attempts + 1):
            attempt_start = self._clock()
            try:
                raw = self._call_adapter(definition, args_model, ctx, policy.timeout_s)
            except FuturesTimeoutError:
                records.append(
                    self._attempt_record(attempt, "FAILED", attempt_start, "TIMEOUT", True)
                )
                if attempt < policy.max_attempts:
                    self._sleeper(policy.backoff_s)
                    continue
                return self._final_failure(definition.name, "TIMEOUT", records, overall_start)
            except CircuitOpenError:
                records.append(
                    self._attempt_record(attempt, "FAILED", attempt_start, "CIRCUIT_OPEN", False)
                )
                return self._final_failure(definition.name, "CIRCUIT_OPEN", records, overall_start)
            except (OperationalError, RedisConnectionError):
                record = self._attempt_record(
                    attempt, "FAILED", attempt_start, "TRANSIENT_READ_ERROR", True
                )
                records.append(record)
                self._emit_attempt_observation(definition.name, record)
                if attempt < policy.max_attempts:
                    self._sleeper(policy.backoff_s)
                    continue
                raise
            except ToolTransientError:
                records.append(
                    self._attempt_record(
                        attempt, "FAILED", attempt_start, "TRANSIENT_READ_ERROR", True
                    )
                )
                if attempt < policy.max_attempts:
                    self._sleeper(policy.backoff_s)
                    continue
                return self._final_failure(
                    definition.name, "TRANSIENT_READ_ERROR", records, overall_start
                )
            except Exception:
                records.append(
                    self._attempt_record(attempt, "FAILED", attempt_start, "INTERNAL_ERROR", False)
                )
                return self._final_failure(
                    definition.name, "INTERNAL_ERROR", records, overall_start
                )

            try:
                status, result_obj = self._validate_output(definition, raw)
            except ValidationError:
                records.append(
                    self._attempt_record(attempt, "FAILED", attempt_start, "INTERNAL_ERROR", False)
                )
                return self._final_failure(
                    definition.name, "INTERNAL_ERROR", records, overall_start
                )

            records.append(self._attempt_record(attempt, status, attempt_start, None, False))
            return ToolCallResult(
                tool_name=definition.name,
                status=status,
                result=result_obj,
                attempt=attempt,
                retry_recovered=attempt > 1,
                duration_ms=self._elapsed_ms(overall_start),
                attempts=records,
            )

        raise AssertionError("unreachable")  # pragma: no cover

    def _call_adapter(
        self,
        definition: ToolDefinition,
        args_model: BaseModel,
        ctx: ToolContext,
        timeout_s: float,
    ) -> object | None:
        pool = self._executor or get_shared_executor()
        future: Future = pool.submit(definition.adapter, args_model, ctx)
        try:
            return future.result(timeout=timeout_s)
        except FuturesTimeoutError:
            future.cancel()
            raise

    def _validate_output(
        self, definition: ToolDefinition, raw: object | None
    ) -> tuple[str, BaseModel | None]:
        if raw is None:
            return "EMPTY", None
        validated = definition.output_schema.model_validate(raw)
        if _is_empty(validated):
            return "EMPTY", None
        return "SUCCEEDED", validated

    def _attempt_record(
        self,
        attempt: int,
        status: str,
        start: float,
        error_type: ToolErrorType | None,
        retryable: bool,
    ) -> ToolAttemptRecord:
        return ToolAttemptRecord(
            attempt=attempt,
            status=status,
            duration_ms=self._elapsed_ms(start),
            error_type=error_type,
            retryable=retryable,
        )

    def _emit_attempt_observation(self, tool_name: str, record: ToolAttemptRecord) -> None:
        log.warning(
            "tool_attempt",
            tool_name=tool_name,
            attempt=record.attempt,
            status=record.status,
            duration_ms=record.duration_ms,
            error_type=record.error_type,
            retryable=record.retryable,
        )

    def _pre_adapter_failure(
        self, tool_name: str, error_type: ToolErrorType, overall_start: float
    ) -> ToolCallResult:
        retryable = error_type in _RETRYABLE_ERRORS
        record = ToolAttemptRecord(
            attempt=1,
            status="FAILED",
            duration_ms=self._elapsed_ms(overall_start),
            error_type=error_type,
            retryable=retryable,
        )
        return self._failure_result(tool_name, error_type, [record], overall_start)

    def _final_failure(
        self,
        tool_name: str,
        error_type: ToolErrorType,
        records: list[ToolAttemptRecord],
        overall_start: float,
    ) -> ToolCallResult:
        return self._failure_result(tool_name, error_type, records, overall_start)

    def _failure_result(
        self,
        tool_name: str,
        error_type: ToolErrorType,
        records: list[ToolAttemptRecord],
        overall_start: float,
    ) -> ToolCallResult:
        return ToolCallResult(
            tool_name=tool_name,
            status="FAILED",
            error_type=error_type,
            fallback_reason=_FALLBACK_REASONS[error_type],
            retryable=error_type in _RETRYABLE_ERRORS,
            attempt=records[-1].attempt,
            duration_ms=self._elapsed_ms(overall_start),
            attempts=records,
        )

    def _elapsed_ms(self, start: float) -> float:
        return max(0.0, (self._clock() - start) * 1000.0)


def _is_empty(output: BaseModel) -> bool:
    items = getattr(output, "items", None)
    if isinstance(items, (list, tuple)) and len(items) == 0:
        return True
    return False


def safe_tool_projection(result: ToolCallResult) -> dict[str, object]:
    result_count, evidence_ids = _evidence(result.result)
    return {
        "tool_name": result.tool_name,
        "status": result.status,
        "duration_ms": result.duration_ms,
        "attempt": result.attempt,
        "retry_recovered": result.retry_recovered,
        "error_type": result.error_type,
        "fallback_reason": result.fallback_reason,
        "retryable": result.retryable,
        "result_count": result_count,
        "evidence_ids": evidence_ids,
    }


def _evidence(result_obj: object | None) -> tuple[int, list[str]]:
    if isinstance(result_obj, SearchRulesOutput):
        return len(result_obj.items), [item.chunk_id for item in result_obj.items]
    if isinstance(result_obj, ConfirmedCasesOutput):
        return len(result_obj.items), [item.flow_id for item in result_obj.items]
    if isinstance(result_obj, T1ContextOutput):
        return 1, [result_obj.flow_id]
    return 0, []

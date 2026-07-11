from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from bank_reconciliation_agent.core.llm.provider import (
    LLMFailureType,
    LLMProvider,
    LLMResult,
    LLMUnavailable,
    ResponseValidator,
)
from bank_reconciliation_agent.core.logging import log


TModel = TypeVar("TModel", bound=BaseModel)


@dataclass(frozen=True)
class LLMCallSummary:
    transport_attempts: int
    retry_recovered: bool
    structured_repair_attempted: bool
    structured_repair_succeeded: bool
    prompt_tokens: int
    completion_tokens: int
    cached_calls: int
    final_failure_type: LLMFailureType | None
    fallback_reason: str | None


@dataclass(frozen=True)
class StructuredCompletion(Generic[TModel]):
    value: TModel
    last_result: LLMResult
    summary: LLMCallSummary


class StructuredLLMError(RuntimeError):
    """Raised when a structured LLM call cannot yield a valid model.

    Exposes a read-only :class:`LLMCallSummary`; the last parse/validation or
    transport exception is preserved through exception chaining.
    """

    def __init__(
        self,
        message: str,
        *,
        summary: LLMCallSummary,
        last_result: LLMResult | None = None,
    ) -> None:
        super().__init__(message)
        self._summary = summary
        self.last_result = last_result

    @property
    def summary(self) -> LLMCallSummary:
        return self._summary


class _Usage:
    def __init__(self) -> None:
        self.transport_attempts = 0
        self.logical_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_calls = 0
        self.structured_repair_attempted = False
        self.structured_repair_succeeded = False

    def record_result(self, result: LLMResult) -> None:
        self.logical_calls += 1
        if result.cached:
            self.cached_calls += 1
            return
        self.transport_attempts += max(1, len(result.attempts))
        self.prompt_tokens += result.prompt_tokens
        self.completion_tokens += result.completion_tokens

    def record_transport_failure(self, exc: BaseException) -> None:
        attempts = getattr(exc, "attempts", None) or []
        self.transport_attempts += max(1, len(attempts))

    def summary(
        self,
        *,
        success: bool,
        final_failure_type: LLMFailureType | None,
        fallback_reason: str | None,
    ) -> LLMCallSummary:
        return LLMCallSummary(
            transport_attempts=self.transport_attempts,
            retry_recovered=success and self.transport_attempts > self.logical_calls,
            structured_repair_attempted=self.structured_repair_attempted,
            structured_repair_succeeded=self.structured_repair_succeeded,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            cached_calls=self.cached_calls,
            final_failure_type=final_failure_type,
            fallback_reason=fallback_reason,
        )


def complete_structured(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    *,
    schema: type[TModel],
    agent_name: str,
    step: str,
    prompt_version: str,
) -> StructuredCompletion[TModel]:
    """Call ``provider`` for a JSON model, allowing one targeted correction.

    On the first ``invalid_json``/``schema_invalid`` output a single correction
    prompt is appended. A second invalid output or any transport failure raises
    :class:`StructuredLLMError` carrying an accurate :class:`LLMCallSummary`.
    """

    usage = _Usage()
    validator = _make_validator(schema)
    conversation = list(messages)

    result = _invoke(
        provider,
        conversation,
        validator,
        usage,
        agent_name=agent_name,
        step=step,
        prompt_version=prompt_version,
        phase="initial",
        last_result=None,
    )
    usage.record_result(result)
    value, failure_type, parse_exc = _parse(result.text, schema)
    if value is not None:
        return StructuredCompletion(
            value=value,
            last_result=result,
            summary=usage.summary(
                success=True, final_failure_type=None, fallback_reason=None
            ),
        )

    _log_invalid(agent_name, step, prompt_version, failure_type, phase="initial")
    usage.structured_repair_attempted = True
    conversation = conversation + [
        {"role": "assistant", "content": result.text},
        {"role": "user", "content": _correction_prompt(failure_type, parse_exc)},
    ]

    corrected = _invoke(
        provider,
        conversation,
        validator,
        usage,
        agent_name=agent_name,
        step=step,
        prompt_version=prompt_version,
        phase="correction",
        last_result=result,
    )
    usage.record_result(corrected)
    value, failure_type, parse_exc = _parse(corrected.text, schema)
    if value is not None:
        usage.structured_repair_succeeded = True
        return StructuredCompletion(
            value=value,
            last_result=corrected,
            summary=usage.summary(
                success=True, final_failure_type=None, fallback_reason=None
            ),
        )

    _log_invalid(agent_name, step, prompt_version, failure_type, phase="correction")
    raise StructuredLLMError(
        f"structured output invalid for {agent_name}",
        summary=usage.summary(
            success=False,
            final_failure_type=failure_type,
            fallback_reason="structured_output_invalid",
        ),
        last_result=corrected,
    ) from parse_exc


def _invoke(
    provider: LLMProvider,
    conversation: list[dict[str, str]],
    validator: ResponseValidator,
    usage: _Usage,
    *,
    agent_name: str,
    step: str,
    prompt_version: str,
    phase: str,
    last_result: LLMResult | None,
) -> LLMResult:
    log.info(
        "agent_llm_call",
        agent_name=agent_name,
        step=step,
        prompt_version=prompt_version,
        phase=phase,
    )
    try:
        return provider.complete(
            conversation,
            temperature=0.0,
            response_format="json_object",
            response_validator=validator,
        )
    except LLMUnavailable as exc:
        usage.record_transport_failure(exc)
        failure_type = getattr(exc, "failure_type", None)
        fallback_reason = getattr(exc, "fallback_reason", None) or "transport_failure"
        raise StructuredLLMError(
            f"llm transport failure for {agent_name}",
            summary=usage.summary(
                success=False,
                final_failure_type=failure_type,
                fallback_reason=fallback_reason,
            ),
            last_result=last_result,
        ) from exc


def _make_validator(schema: type[BaseModel]) -> ResponseValidator:
    def validate(text: str) -> bool:
        value, _, _ = _parse(text, schema)
        return value is not None

    return validate


def _parse(
    text: str, schema: type[TModel]
) -> tuple[TModel | None, LLMFailureType | None, Exception | None]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, "invalid_json", exc
    try:
        return schema.model_validate(data), None, None
    except ValidationError as exc:
        return None, "schema_invalid", exc


def _correction_prompt(
    failure_type: LLMFailureType | None, exc: Exception | None
) -> str:
    if failure_type == "schema_invalid" and isinstance(exc, ValidationError):
        paths = sorted(
            {".".join(str(part) for part in error["loc"]) for error in exc.errors()}
        )
        detail = (
            f"字段校验失败：{', '.join(paths)}" if paths else "输出结构不符合要求"
        )
    else:
        detail = "输出不是合法 JSON"
    return (
        f"上一次输出无法使用，失败类型：{failure_type}。{detail}。"
        "请只返回修正后的 JSON 对象，不要包含解释、注释或额外文本。"
    )


def _log_invalid(
    agent_name: str,
    step: str,
    prompt_version: str,
    failure_type: LLMFailureType | None,
    *,
    phase: str,
) -> None:
    log.warning(
        "agent_llm_invalid_output",
        agent_name=agent_name,
        step=step,
        prompt_version=prompt_version,
        phase=phase,
        failure_type=failure_type,
    )

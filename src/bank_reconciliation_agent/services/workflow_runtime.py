from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from bank_reconciliation_agent.agents.extraction_agent import ExtractionResult
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.schemas.stream import StreamEventType
from bank_reconciliation_agent.schemas.tools import ToolCallResult
from bank_reconciliation_agent.schemas.trace import SpanStatus, TraceSpanView
from bank_reconciliation_agent.services.stream_emitter import (
    StreamEmitter,
    to_stream_event,
    to_trace_span_event,
)
from bank_reconciliation_agent.services.trace import NoOpRecorder
from bank_reconciliation_agent.services.workflow_types import (
    REVERSAL_HINTS,
    Recorder,
    ReconciliationState,
)


_NOOP_RECORDER = NoOpRecorder()


def recorder_for(state: ReconciliationState) -> Recorder:
    return state.get("recorder") or _NOOP_RECORDER


def emit_trace_span(
    state: ReconciliationState,
    recorder: Recorder,
    emitter: StreamEmitter | None,
) -> None:
    """Best-effort projection of the most recently completed Trace span."""

    if emitter is None:
        return
    try:
        span = recorder.last_completed_span()
        if span is None:
            return
        view = TraceSpanView.from_span(span)
        stream_seq = int(state.get("stream_seq", 0)) + 1
        state["stream_seq"] = stream_seq
        emitter.emit(to_trace_span_event(view, seq=stream_seq))
    except Exception as exc:
        log.warning("trace_span_emit_failed", error_type=type(exc).__name__)


_TOOL_STATUS_MAP: dict[str, tuple[SpanStatus, str | None]] = {
    "SUCCEEDED": (SpanStatus.SUCCEEDED, "RESULT"),
    "EMPTY": (SpanStatus.SUCCEEDED, "EMPTY"),
    "FAILED": (SpanStatus.FAILED, None),
}


def complete_tool_span(
    state: ReconciliationState,
    handle: Any,
    result: ToolCallResult,
    projection: dict[str, Any],
    *,
    emitter: StreamEmitter | None = None,
) -> None:
    recorder = recorder_for(state)
    status, outcome = _TOOL_STATUS_MAP.get(
        str(projection["status"]),
        (SpanStatus.FAILED, None),
    )
    recovered_error_type: str | None = None
    if projection.get("retry_recovered"):
        for attempt in result.attempts:
            if attempt.status == "FAILED" and attempt.error_type is not None:
                recovered_error_type = attempt.error_type
                break
    recorder.finish_tool(
        handle,
        status=status,
        outcome=outcome,
        attempt=int(projection.get("attempt", 1)),
        retry_recovered=bool(projection.get("retry_recovered", False)),
        recovered_error_type=recovered_error_type,
        result_count=int(projection.get("result_count", 0)),
        evidence_ids=list(projection.get("evidence_ids", [])),
        error_type=projection.get("error_type"),
        fallback_reason=projection.get("fallback_reason"),
    )
    emit_trace_span(state, recorder, emitter)


def agent_recovered_error_type(agent: Any, usage: dict[str, Any]) -> str | None:
    if not usage.get("retry_recovered"):
        return None
    result = getattr(agent, "last_llm_result", None)
    attempts = getattr(result, "attempts", None) or []
    for attempt in attempts:
        if getattr(attempt, "outcome", None) == "failure" and attempt.failure_type is not None:
            return attempt.failure_type
    return None


def finish_agent_span(
    state: ReconciliationState,
    handle: Any,
    *,
    agent: Any,
    status: SpanStatus | None,
    emitter: StreamEmitter | None = None,
) -> None:
    recorder = recorder_for(state)
    usage = llm_usage(agent)
    span_status = status
    if span_status is None:
        span_status = SpanStatus.FAILED if usage.get("final_failure_type") else SpanStatus.SUCCEEDED
    model_name = getattr(getattr(agent, "last_llm_result", None), "model", None)
    recorder.finish_agent(
        handle,
        status=span_status,
        model_name=model_name,
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
        cached_calls=int(usage.get("cached_calls", 0)),
        attempt=max(1, int(usage.get("transport_attempts", 1) or 1)),
        retry_recovered=bool(usage.get("retry_recovered", False)),
        recovered_error_type=agent_recovered_error_type(agent, usage),
        structured_repair_attempted=bool(usage.get("structured_repair_attempted", False)),
        structured_repair_succeeded=bool(usage.get("structured_repair_succeeded", False)),
        error_type=usage.get("final_failure_type"),
        fallback_reason=usage.get("fallback_reason"),
    )
    emit_trace_span(state, recorder, emitter)


def append_agent_log(
    state: ReconciliationState,
    row: dict[str, Any],
    emitter: StreamEmitter,
) -> None:
    state["agent_logs"].append(row)
    emit_stream_row(state, row, emitter)


def emit_stream_row(
    state: ReconciliationState,
    row: dict[str, Any],
    emitter: StreamEmitter,
    event_type: StreamEventType | None = None,
) -> None:
    state["stream_seq"] = int(state.get("stream_seq", 0)) + 1
    emitter.emit(
        to_stream_event(
            row,
            seq=state["stream_seq"],
            task_id=state["task_id"],
            event_type=event_type,
        )
    )


def to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def build_rag_query(state: ReconciliationState) -> str:
    math_result = state.get("math_result", {})
    return (
        f"{state.get('error_type') or ''} {state.get('exception_branch') or ''} "
        f"bank_amount={optional_string(math_result.get('bank_amount'))} "
        f"clear_amount={optional_string(math_result.get('clear_amount'))} "
        f"amount_diff={optional_string(math_result.get('amount_diff'))}"
    )


def contains_reversal_hint(summary: str, remark: str | None) -> bool:
    text = f"{summary} {remark or ''}"
    return any(keyword in text for keyword in REVERSAL_HINTS)


def extract_reversal_hint(*, summary: str, remark: str | None) -> ExtractionResult:
    text = " ".join(part.strip() for part in (summary, remark or "") if part.strip())
    if "冲正" in text or "红冲" in text:
        standard_type = "REVERSAL"
    elif "退款" in text:
        standard_type = "REFUND"
    elif "抹账" in text or "撤销" in text:
        standard_type = "CANCEL"
    else:
        standard_type = "UNKNOWN"
    return ExtractionResult(
        standard_type=standard_type,
        original_flow_id=None,
        cleaned_remark=text,
        confidence=1.0,
    )


def flow_id(state: ReconciliationState) -> str:
    return str(
        state["source_a_item"].get("flow_id")
        or state["source_b_item"].get("flow_id")
        or state["current_queue_id"]
        or ""
    )


def combined_text(state: ReconciliationState, key: str) -> str:
    values = [
        str(item.get(key)).strip()
        for item in (state["source_a_item"], state["source_b_item"])
        if item.get(key) is not None and str(item.get(key)).strip()
    ]
    return " ".join(values)


def transaction_date(state: ReconciliationState) -> str | None:
    for key in ("accounting_date", "trade_date", "transaction_date"):
        value = state["source_a_item"].get(key) or state["source_b_item"].get(key)
        if value is not None:
            return str(value)
    return None


def optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def model_or_mapping_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value)


def llm_usage(agent: Any) -> dict[str, Any]:
    summary = getattr(agent, "last_llm_summary", None)
    if summary is not None:
        prompt_tokens = int(summary.prompt_tokens)
        completion_tokens = int(summary.completion_tokens)
        return {
            "transport_attempts": int(summary.transport_attempts),
            "retry_recovered": bool(summary.retry_recovered),
            "structured_repair_attempted": bool(summary.structured_repair_attempted),
            "structured_repair_succeeded": bool(summary.structured_repair_succeeded),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "llm_tokens": prompt_tokens + completion_tokens,
            "cached_calls": int(summary.cached_calls),
            "final_failure_type": summary.final_failure_type,
            "fallback_reason": summary.fallback_reason,
        }

    result = getattr(agent, "last_llm_result", None)
    if result is None:
        return {
            "transport_attempts": 0,
            "retry_recovered": False,
            "structured_repair_attempted": False,
            "structured_repair_succeeded": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "llm_tokens": 0,
            "cached_calls": 0,
            "final_failure_type": None,
            "fallback_reason": None,
        }

    cached = bool(getattr(result, "cached", False))
    prompt_tokens = 0 if cached else int(getattr(result, "prompt_tokens", 0))
    completion_tokens = 0 if cached else int(getattr(result, "completion_tokens", 0))
    return {
        "transport_attempts": 1,
        "retry_recovered": False,
        "structured_repair_attempted": False,
        "structured_repair_succeeded": False,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "llm_tokens": prompt_tokens + completion_tokens,
        "cached_calls": 1 if cached else 0,
        "final_failure_type": None,
        "fallback_reason": None,
    }


def zero_llm_usage() -> dict[str, Any]:
    return llm_usage(object())

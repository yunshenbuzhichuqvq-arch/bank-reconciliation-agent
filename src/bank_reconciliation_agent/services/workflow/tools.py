from __future__ import annotations

from typing import Any

from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.schemas.stream import StreamEventType
from bank_reconciliation_agent.schemas.tools import ToolCallResult, ToolContext
from bank_reconciliation_agent.schemas.trace import SpanStatus
from bank_reconciliation_agent.services.stream_emitter import StreamEmitter
from bank_reconciliation_agent.services.tool_executor import safe_tool_projection
from bank_reconciliation_agent.services.workflow.runtime import (
    append_agent_log,
    complete_tool_span,
    emit_stream_row,
    emit_trace_span,
    flow_id as resolve_flow_id,
    recorder_for,
)
from bank_reconciliation_agent.services.workflow.types import (
    ReconciliationState,
    ToolExecutorProtocol,
)


def build_tool_context(
    state: ReconciliationState,
    *,
    fallback_level: int = 0,
) -> ToolContext:
    return ToolContext(
        user_id=state["user_id"],
        task_id=state["task_id"],
        flow_id=resolve_flow_id(state),
        scenario_type=state["scenario_type"],
        exception_branch=state.get("exception_branch") or "",
        fallback_level=fallback_level,
    )


def execute_tool(
    tool_executor: ToolExecutorProtocol,
    name: str,
    args: Any,
    state: ReconciliationState,
    emitter: StreamEmitter,
    *,
    fallback_level: int = 0,
) -> ToolCallResult:
    context = build_tool_context(state, fallback_level=fallback_level)
    handle = recorder_for(state).start_tool(name)
    try:
        result = tool_executor.execute(name, args, context)
    except (OperationalError, RedisConnectionError):
        finish_tool_span_failed(
            state,
            handle,
            error_type="TRANSIENT_READ_ERROR",
            fallback_reason="TOOL_TRANSIENT_READ_ERROR",
            emitter=emitter,
        )
        raise
    except Exception:
        finish_tool_span_failed(
            state,
            handle,
            error_type="INTERNAL_ERROR",
            fallback_reason="TOOL_INTERNAL_ERROR",
            emitter=emitter,
        )
        raise
    projection = safe_tool_projection(result)
    complete_tool_span(state, handle, result, projection, emitter=emitter)
    append_agent_log(
        state,
        {
            "agent_name": "ToolExecutor",
            "step": "tool_call",
            "flow_id": resolve_flow_id(state),
            **projection,
        },
        emitter,
    )
    return result


def finish_tool_span_failed(
    state: ReconciliationState,
    handle: Any,
    *,
    error_type: str,
    fallback_reason: str,
    emitter: StreamEmitter | None = None,
) -> None:
    try:
        recorder = recorder_for(state)
        recorder.finish_tool(
            handle,
            status=SpanStatus.FAILED,
            outcome=None,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            result_count=0,
            evidence_ids=[],
            error_type=error_type,
            fallback_reason=fallback_reason,
        )
        emit_trace_span(state, recorder, emitter)
    except Exception as exc:
        log.warning("tool_span_close_failed", error_type=type(exc).__name__)


def tool_fail_closed_item(
    state: ReconciliationState,
    *,
    flow_id: str,
    tool_result: ToolCallResult,
    emitter: StreamEmitter,
) -> ReconciliationState:
    decision = AuditDecision(
        flow_id=flow_id,
        decision="PENDING_HUMAN",
        risk_level="HIGH",
        reason="关键证据缺失，自动转人工。",
        ai_suggestion="PENDING_HUMAN",
        evidence=[],
        confidence=0.0,
        fallback_applied=True,
        fallback_level=0,
        next_action="PENDING_HUMAN",
    )
    state["audit_decision"] = decision.model_dump(mode="json")
    state["confidence"] = 0.0
    state["fallback_level"] = 0
    state["fallback_path"] = "HUMAN"
    state["next_action"] = "PENDING_HUMAN"
    if tool_result.status == "FAILED":
        state["error_message"] = tool_result.fallback_reason
    emit_stream_row(
        state,
        {
            "agent_name": "Workflow",
            "step": "item_done",
            "flow_id": flow_id,
            "status": state["next_action"],
            "decision": state["audit_decision"]["decision"],
            "confidence": state["audit_decision"]["confidence"],
        },
        emitter,
        StreamEventType.ITEM_DONE,
    )
    return state

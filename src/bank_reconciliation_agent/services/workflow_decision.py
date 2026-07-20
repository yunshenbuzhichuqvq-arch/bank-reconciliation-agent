from __future__ import annotations

from typing import Any

from bank_reconciliation_agent.agents.audit_agent import AuditAgent, AuditDecision
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.schemas.rag import RagSearchItem
from bank_reconciliation_agent.schemas.stream import StreamEventType
from bank_reconciliation_agent.schemas.trace import GuardOutcome, SpanStatus, SpanType
from bank_reconciliation_agent.services.fallback import mark_fallback
from bank_reconciliation_agent.services.hooks import (
    SchemaValidationError,
    constraint_hook,
    decision_hook,
    schema_hook,
)
from bank_reconciliation_agent.services.stream_emitter import StreamEmitter
from bank_reconciliation_agent.services.workflow_runtime import (
    append_agent_log,
    emit_stream_row,
    emit_trace_span,
    finish_agent_span,
    llm_usage,
    recorder_for,
    to_decimal,
)
from bank_reconciliation_agent.services.workflow_types import (
    BANK_ENTERPRISE_LLM_AUDIT_BRANCHES,
    ReconciliationState,
)


def fail_closed_item(
    state: ReconciliationState,
    *,
    flow_id: str,
    agent: Any,
    agent_name: str,
    step: str,
    emitter: StreamEmitter,
) -> ReconciliationState:
    usage = llm_usage(agent)
    decision = AuditDecision(
        flow_id=flow_id,
        decision="PENDING_HUMAN",
        risk_level="HIGH",
        reason="AI 处理异常，自动转人工。",
        ai_suggestion="PENDING_HUMAN",
        evidence=[],
        confidence=0.0,
        fallback_applied=True,
        fallback_level=1,
        next_action="PENDING_HUMAN",
    )
    state["audit_decision"] = decision.model_dump(mode="json")
    state["confidence"] = 0.0
    state["fallback_level"] = 1
    state["fallback_path"] = "AI_ERROR->HUMAN"
    state["next_action"] = "PENDING_HUMAN"
    state["error_message"] = usage.get("fallback_reason") or "structured_output_invalid"
    append_agent_log(
        state,
        {
            "agent_name": agent_name,
            "step": step,
            "flow_id": flow_id,
            "fallback_level": 1,
            **usage,
        },
        emitter,
    )
    emit_item_done(state, flow_id=flow_id, emitter=emitter)
    return state


def audit_decision_once(
    *,
    state: ReconciliationState,
    audit_agent: AuditAgent,
    audit_kwargs: dict[str, Any],
    emitter: StreamEmitter,
) -> AuditDecision:
    state["error_message"] = None
    state["retry_count"] = 0
    audit_handle = recorder_for(state).start_agent("AuditAgent")
    try:
        decision = schema_hook(audit_agent.decide_with_llm(**audit_kwargs))
    except SchemaValidationError:
        finish_agent_span(
            state,
            audit_handle,
            agent=audit_agent,
            status=SpanStatus.FAILED,
            emitter=emitter,
        )
        log.warning(
            "schema_hook_failed",
            hook_name="SchemaHook",
            flow_id=audit_kwargs.get("flow_id"),
        )
        append_agent_log(
            state,
            {
                "agent_name": "SchemaHook",
                "step": "schema_validate",
                "flow_id": audit_kwargs.get("flow_id"),
                "retry_count": 0,
                "error_message": "schema validation failed",
            },
            emitter,
        )
        state["error_message"] = "schema validation failed"
        return AuditDecision(
            flow_id=str(audit_kwargs.get("flow_id") or ""),
            decision="PENDING_HUMAN",
            risk_level="HIGH",
            reason="SchemaHook 校验失败，转人工。",
            ai_suggestion="PENDING_HUMAN",
            evidence=[],
            confidence=0.0,
            fallback_applied=True,
            fallback_level=1,
            next_action="PENDING_HUMAN",
        )

    finish_agent_span(
        state,
        audit_handle,
        agent=audit_agent,
        status=None,
        emitter=emitter,
    )
    return decision


def audit_decision_for_state(
    *,
    state: ReconciliationState,
    audit_agent: AuditAgent,
    audit_kwargs: dict[str, Any],
    emitter: StreamEmitter,
) -> tuple[AuditDecision, str]:
    exception_branch = str(audit_kwargs.get("exception_branch") or "")
    use_rule_first = (
        state["scenario_type"] == "BANK_ENTERPRISE"
        and exception_branch not in BANK_ENTERPRISE_LLM_AUDIT_BRANCHES
    )
    if not use_rule_first:
        return (
            audit_decision_once(
                state=state,
                audit_agent=audit_agent,
                audit_kwargs=audit_kwargs,
                emitter=emitter,
            ),
            "LLM",
        )

    state["error_message"] = None
    state["retry_count"] = 0
    audit_agent.last_llm_result = None
    audit_agent.last_llm_summary = None
    recorder = recorder_for(state)
    with recorder.span(SpanType.ROUTE, "RuleAudit"):
        decision = schema_hook(audit_agent.decide(**audit_kwargs))
    emit_trace_span(state, recorder, emitter)
    return decision, "DETERMINISTIC"


def apply_post_hooks(
    state: ReconciliationState,
    audit_decision: AuditDecision,
    emitter: StreamEmitter,
) -> None:
    rag_items = [RagSearchItem.model_validate(item) for item in state["rag_context"]]
    constraint = constraint_hook(
        audit_decision,
        amount_diff=to_decimal(state.get("math_result", {}).get("amount_diff")),
        rag_best_score=max((item.score for item in rag_items), default=None),
    )
    guard_outcome = GuardOutcome.PASSED if constraint.ok else GuardOutcome.BLOCKED
    recorder = recorder_for(state)
    with recorder.span(SpanType.GUARD, "ConstraintGuard", outcome=guard_outcome):
        pass
    emit_trace_span(state, recorder, emitter)
    if not constraint.ok:
        violated_suffix = f"；违反约束: {', '.join(constraint.violated)}"
        audit_decision.reason = (
            f"{audit_decision.reason}{violated_suffix}"
            if audit_decision.reason
            else f"违反约束: {', '.join(constraint.violated)}"
        )
        audit_decision = mark_fallback(
            audit_decision,
            fallback_level=max(audit_decision.fallback_level, 1),
            next_action="PENDING_HUMAN",
        )
    route = decision_hook(audit_decision, constraint)
    audit_decision.next_action = route
    if not constraint.ok:
        audit_decision.decision = "PENDING_HUMAN"
        audit_decision.ai_suggestion = "PENDING_HUMAN"
    state["audit_decision"] = audit_decision.model_dump(mode="json")
    state["confidence"] = audit_decision.confidence
    state["fallback_level"] = audit_decision.fallback_level
    state["next_action"] = route
    append_agent_log(
        state,
        {
            "agent_name": "DecisionHook",
            "step": "post_hook_route",
            "flow_id": audit_decision.flow_id,
            "violated": constraint.violated,
            "next_action": route,
        },
        emitter,
    )


def emit_item_done(
    state: ReconciliationState,
    *,
    flow_id: str,
    emitter: StreamEmitter,
) -> None:
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

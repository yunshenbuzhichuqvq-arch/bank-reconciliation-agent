from __future__ import annotations

import json
from decimal import Decimal
from typing import Callable

from pydantic import ValidationError

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgentError
from bank_reconciliation_agent.agents.trace_agent import TraceAgentError
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.llm.provider import LLMUnavailable
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.rag.retriever import rule_retriever
from bank_reconciliation_agent.schemas.ledger import LedgerRow
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from bank_reconciliation_agent.schemas.reconciliation import (
    ReconciliationAuditDecision,
    ReconciliationRagEvidence,
)
from bank_reconciliation_agent.schemas.trace import (
    SpanStatus,
    SpanType,
    TraceSpan,
    TraceSpanView,
    WorkflowOutcome,
)
from bank_reconciliation_agent.services.agent_log import agent_log_service
from bank_reconciliation_agent.services.rag_log import rag_log_service
from bank_reconciliation_agent.services.reconciliation_types import (
    ReconciliationFlowBundle,
    ReconciliationMatchResult,
)
from bank_reconciliation_agent.services.stream_emitter import (
    StreamEmitter,
    to_trace_span_event,
)
from bank_reconciliation_agent.services.trace import NoOpRecorder, TraceRecorder
from bank_reconciliation_agent.services.workflow import ReconciliationState


WorkflowRunner = Callable[..., ReconciliationState]

_WORKFLOW_OUTCOME_BY_DECISION: dict[str, WorkflowOutcome] = {
    "AUTO_FIXED": WorkflowOutcome.AUTO_FIXED,
    "PENDING_HUMAN": WorkflowOutcome.PENDING_HUMAN,
    "UNRESOLVED": WorkflowOutcome.UNRESOLVED,
}

AGENT_PROCESSING_ERRORS = (
    LLMUnavailable,
    ExtractionAgentError,
    TraceAgentError,
    ValidationError,
    json.JSONDecodeError,
)


def build_flow_bundle(
    result: ReconciliationMatchResult,
    *,
    user_id: str,
    task_id: str,
    scenario_type: str,
    run_workflow: WorkflowRunner,
    emitter: StreamEmitter | None,
    stream_seq_start: int,
) -> ReconciliationFlowBundle:
    rag_query = build_rag_query(result)
    rule_hit = {
        "error_type": result.error_type or "",
        "exception_branch": result.exception_branch,
    }
    recorder = new_recorder(user_id=user_id, task_id=task_id, result=result)
    stream_seq = stream_seq_start
    try:
        workflow_kwargs = {
            "user_id": user_id,
            "task_id": task_id,
            "scenario_type": scenario_type,
            "result": result,
            "rag_query": rag_query,
            "recorder": recorder,
        }
        if emitter is not None:
            workflow_kwargs["emitter"] = emitter
            workflow_kwargs["stream_seq_start"] = stream_seq
        workflow_state = run_workflow(**workflow_kwargs)
        if emitter is not None:
            stream_seq = int(workflow_state.get("stream_seq", stream_seq))
    except AGENT_PROCESSING_ERRORS as exc:
        log.warning(
            "reconciliation_row_agent_fallback",
            flow_id=result.flow_id,
            task_id=task_id,
            error_type=type(exc).__name__,
        )
        workflow_state = agent_error_workflow_state(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            result=result,
            error=exc,
        )

    rag_items = [RagSearchItem.model_validate(item) for item in workflow_state["rag_context"]]
    rag_response = RagSearchResponse.model_validate(
        workflow_state.get("rag_response", {"items": rag_items})
    )
    rag_hit = {
        "chunk_ids": [item.chunk_id for item in rag_items],
        "best_score": max((item.score for item in rag_items), default=None),
    }
    rag_log_row = rag_log_service.build_row(
        user_id=user_id,
        task_id=task_id,
        query_text=rag_query,
        top_k=settings.rag_rerank_top_k,
        items=rag_items,
        response=rag_response,
    )
    audit_decision = AuditDecision.model_validate(workflow_state["audit_decision"])
    fallback_path = workflow_state.get("fallback_path")
    consumed_logs = [row for row in workflow_state["agent_logs"] if not row.get("cached", False)]
    cached_logs = [row for row in workflow_state["agent_logs"] if row.get("cached", False)]
    prompt_tokens = sum(int(row.get("prompt_tokens", 0)) for row in consumed_logs)
    completion_tokens = sum(int(row.get("completion_tokens", 0)) for row in consumed_logs)
    saved_prompt_tokens = sum(int(row.get("prompt_tokens", 0)) for row in cached_logs)
    saved_completion_tokens = sum(int(row.get("completion_tokens", 0)) for row in cached_logs)
    agent_output = {
        "decision": audit_decision.decision,
        "risk_level": audit_decision.risk_level,
        "ai_suggestion": audit_decision.ai_suggestion,
        "reason": audit_decision.reason,
        "confidence": audit_decision.confidence,
        "fallback_applied": audit_decision.fallback_applied,
        "fallback_level": audit_decision.fallback_level,
        "next_action": audit_decision.next_action,
        "fallback_path": fallback_path,
    }
    input_payload = {
        "flow_id": result.flow_id,
        "rule_hit": rule_hit,
        "rag_hit": rag_hit,
        "bank_amount": format_optional_decimal(result.bank_amount),
        "clear_amount": format_optional_decimal(result.clear_amount),
        "amount_diff": format_optional_decimal(result.amount_diff),
    }
    agent_log_row = agent_log_service.build_row(
        user_id=user_id,
        task_id=task_id,
        queue_id=None,
        agent_name="AuditAgent",
        event_type="AUDIT_DECISION",
        input_payload=input_payload,
        output_payload=agent_output,
        post_hook_results=post_hook_results(workflow_state),
        prompt_version=prompt_version_from_logs(workflow_state["agent_logs"]),
        fallback_level=audit_decision.fallback_level,
        llm_tokens=prompt_tokens + completion_tokens,
    )
    trace_spans = finalize_recorder(recorder, audit_decision)
    trace_snapshot = None
    if trace_spans:
        trace_snapshot = (result.flow_id, recorder.trace_id or "", trace_spans)
        if emitter is not None:
            stream_seq = emit_terminal_and_root(
                trace_spans,
                emitter=emitter,
                stream_seq=stream_seq,
            )
    ledger_row = LedgerRow(
        id=0,
        task_id=task_id,
        flow_id=result.flow_id,
        error_type=result.error_type or "",
        exception_branch=result.exception_branch,
        bank_amount=result.bank_amount,
        clear_amount=result.clear_amount,
        discrepancy_amount=ledger_discrepancy_amount(result),
        ai_audit_opinion=audit_decision.reason,
        ai_confidence=Decimal(str(audit_decision.confidence)).quantize(Decimal("0.0001")),
        rag_source=", ".join(item.chunk_id for item in rag_items) or None,
        fallback_path=fallback_path,
        handle_status=audit_decision.decision,
    )
    return ReconciliationFlowBundle(
        ledger_row=ledger_row,
        rag_log_row=rag_log_row,
        agent_log_row=agent_log_row,
        trace_snapshot=trace_snapshot,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        saved_prompt_tokens=saved_prompt_tokens,
        saved_completion_tokens=saved_completion_tokens,
        fallback_l2_rows=int(bool(fallback_path and "L2" in fallback_path)),
        fallback_l3_rows=int(bool(fallback_path and "L3" in fallback_path)),
        stream_seq=stream_seq,
    )


def format_optional_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value:.2f}"


def build_rag_query(result: ReconciliationMatchResult) -> str:
    query_prefix_by_error_type = {
        "AMOUNT_MISMATCH": "金额不一致 对账差异 处理规则",
        "BANK_UNARRIVED": "银行未到账 企业已记账 单边 查询查复",
        "BOOK_UNRECORDED": "银行已到账 企业未入账 补登 单边",
        "NARRATIVE_NAME_MISMATCH": "摘要 客户名 不一致 冲正 退款 核对",
        "DUPLICATE_BOOKING": "重复记账 重复入账 一端多记 排查",
    }
    prefix = query_prefix_by_error_type.get(
        result.error_type or "",
        f"{result.error_type or ''} reconciliation exception",
    )
    return (
        f"{result.error_type or ''} {prefix} "
        f"bank_amount={format_optional_decimal(result.bank_amount)} "
        f"clear_amount={format_optional_decimal(result.clear_amount)} "
        f"amount_diff={format_optional_decimal(result.amount_diff)}"
    )


def evidence_from_rag_source(
    rag_source: str | None,
    *,
    scenario_type: str = "BANK_ENTERPRISE",
) -> list[ReconciliationRagEvidence]:
    if not rag_source:
        return []
    chunk_ids = [chunk_id.strip() for chunk_id in rag_source.split(",") if chunk_id.strip()]
    return [
        to_reconciliation_evidence(item)
        for item in rule_retriever.get_by_chunk_ids(
            chunk_ids,
            scenario_type=scenario_type,
        )
    ]


def to_reconciliation_evidence(item: RagSearchItem) -> ReconciliationRagEvidence:
    return ReconciliationRagEvidence(
        chunk_id=item.chunk_id,
        source=item.source,
        source_name=item.source_name,
        source_url=item.source_url,
        source_file=item.source_file,
        section_title=item.section_title,
        element_type=item.element_type,
        business_tags=item.business_tags,
        score=item.score,
        content=item.content,
    )


def to_reconciliation_audit_decision(decision: AuditDecision) -> ReconciliationAuditDecision:
    return ReconciliationAuditDecision(
        flow_id=decision.flow_id,
        decision=decision.decision,
        risk_level=decision.risk_level,
        reason=decision.reason,
        evidence=[to_reconciliation_evidence(item) for item in decision.evidence],
        confidence=decision.confidence,
        fallback_applied=decision.fallback_applied,
        fallback_level=decision.fallback_level,
        next_action=decision.next_action,
    )


def new_recorder(
    *,
    user_id: str,
    task_id: str,
    result: ReconciliationMatchResult,
) -> TraceRecorder | NoOpRecorder:
    try:
        return TraceRecorder(user_id=user_id, task_id=task_id, flow_id=result.flow_id)
    except Exception as exc:
        log.warning(
            "trace_recorder_init_failed",
            task_id=task_id,
            flow_id=result.flow_id,
            error_type=type(exc).__name__,
        )
        return NoOpRecorder()


def finalize_recorder(
    recorder: TraceRecorder | NoOpRecorder,
    audit_decision: AuditDecision,
) -> list[TraceSpan]:
    outcome = _WORKFLOW_OUTCOME_BY_DECISION.get(
        audit_decision.decision,
        WorkflowOutcome.PENDING_HUMAN,
    )
    if audit_decision.fallback_applied and audit_decision.decision != "AUTO_FIXED":
        terminal_type = SpanType.FALLBACK
        outcome = WorkflowOutcome.PENDING_HUMAN
    else:
        terminal_type = SpanType.FINAL
    try:
        recorder.close_root(
            status=SpanStatus.SUCCEEDED,
            outcome=outcome,
            terminal_type=terminal_type,
        )
        return list(recorder.snapshot())
    except Exception as exc:
        log.warning(
            "trace_recorder_finalize_failed",
            trace_id=recorder.trace_id,
            error_type=type(exc).__name__,
        )
        recorder.disable()
        return []


def emit_terminal_and_root(
    spans: list[TraceSpan],
    *,
    emitter: StreamEmitter | None,
    stream_seq: int,
) -> int:
    if emitter is None or not spans:
        return stream_seq
    root = spans[0]
    terminal = next(
        (span for span in spans if span.span_type in (SpanType.FINAL, SpanType.FALLBACK)),
        None,
    )
    for span in (terminal, root):
        if span is None:
            continue
        stream_seq += 1
        emit_trace_span_safe(emitter, span, stream_seq)
    return stream_seq


def emit_trace_span_safe(emitter: StreamEmitter, span: TraceSpan, seq: int) -> None:
    try:
        emitter.emit(to_trace_span_event(TraceSpanView.from_span(span), seq=seq))
    except Exception as exc:
        log.warning("trace_span_emit_failed", error_type=type(exc).__name__)


def agent_error_workflow_state(
    *,
    user_id: str,
    task_id: str,
    scenario_type: str,
    result: ReconciliationMatchResult,
    error: Exception,
) -> ReconciliationState:
    reason = f"AI 处理异常，自动转人工：{type(error).__name__}"
    decision = AuditDecision(
        flow_id=result.flow_id,
        decision="PENDING_HUMAN",
        risk_level="HIGH",
        reason=reason,
        ai_suggestion="PENDING_HUMAN",
        evidence=[],
        confidence=0.0,
        fallback_applied=True,
        fallback_level=1,
        next_action="PENDING_HUMAN",
    )
    return {
        "task_id": task_id,
        "user_id": user_id,
        "thread_id": task_id,
        "scenario_type": scenario_type,
        "current_queue_id": None,
        "source_a_item": {"flow_id": result.flow_id},
        "source_b_item": {"flow_id": result.flow_id},
        "error_type": result.error_type,
        "exception_branch": result.exception_branch,
        "math_result": {
            "bank_amount": format_optional_decimal(result.bank_amount),
            "clear_amount": format_optional_decimal(result.clear_amount),
            "amount_diff": format_optional_decimal(result.amount_diff),
        },
        "extraction_result": {},
        "rag_context": [],
        "audit_decision": decision.model_dump(mode="json"),
        "confidence": 0.0,
        "retry_count": 0,
        "fallback_level": 1,
        "next_action": "PENDING_HUMAN",
        "error_message": reason,
        "agent_logs": [
            {
                "agent_name": "AuditAgent",
                "step": "agent_error_fallback",
                "flow_id": result.flow_id,
                "fallback_level": 1,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "llm_tokens": 0,
                "error_message": reason,
            }
        ],
        "fallback_path": "AI_ERROR->HUMAN",
        "t1_candidate": result.t1_candidate,
        "fuzzy_candidate": result.fuzzy_candidate,
    }


def ledger_discrepancy_amount(result: ReconciliationMatchResult) -> Decimal:
    if result.amount_diff is not None:
        return abs(result.amount_diff)
    if result.bank_amount is not None:
        return result.bank_amount
    if result.clear_amount is not None:
        return result.clear_amount
    return Decimal("0.00")


def prompt_version_from_logs(logs: list[dict[str, object]]) -> str | None:
    for row in reversed(logs):
        prompt_version = row.get("prompt_version")
        if prompt_version is not None:
            return str(prompt_version)
    return None


def post_hook_results(workflow_state: ReconciliationState) -> dict[str, object]:
    decision_log = next(
        (
            row
            for row in reversed(workflow_state["agent_logs"])
            if row.get("agent_name") == "DecisionHook"
        ),
        {},
    )
    return {
        "schema_retries": int(workflow_state.get("retry_count", 0)),
        "constraint_violated": list(decision_log.get("violated", [])),
        "decision_route": str(
            decision_log.get("next_action", workflow_state.get("next_action", ""))
        ),
    }

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, NotRequired, Protocol, TypedDict

from bank_reconciliation_agent.agents.audit_agent import AuditAgent, AuditDecision, audit_agent
from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgent, extraction_agent
from bank_reconciliation_agent.agents.trace_agent import TraceAgent, trace_agent
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.logging import bind_trace_context, log
from bank_reconciliation_agent.rag.retriever import rule_retriever
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchRequest, RagSearchResponse
from bank_reconciliation_agent.schemas.stream import StreamEventType
from bank_reconciliation_agent.services.circuit_breaker import CircuitBreaker
from bank_reconciliation_agent.services.fallback import (
    FallbackCaseProvider,
    confidence_is_low,
    l1_requires_l2,
    ledger_fallback_case_provider,
    mark_fallback,
)
from bank_reconciliation_agent.services.hooks import (
    SchemaValidationError,
    constraint_hook,
    decision_hook,
    memory_hook,
    schema_hook,
)
from bank_reconciliation_agent.services.stream_emitter import NullEmitter, StreamEmitter, to_stream_event


REVERSAL_HINTS = ("冲正", "红冲", "退款", "抹账", "撤销")
TRACE_BRANCHES = {"BE-R005", "BE-R006", "BC-R003"}
rag_circuit_breaker = CircuitBreaker(
    fail_threshold=settings.rag_breaker_fail_threshold,
    open_seconds=settings.rag_breaker_open_seconds,
)


class ReconciliationState(TypedDict):
    task_id: str
    user_id: str
    thread_id: str
    scenario_type: str
    current_queue_id: int | None
    source_a_item: dict[str, Any]
    source_b_item: dict[str, Any]
    error_type: str | None
    exception_branch: str | None
    math_result: dict[str, Any]
    extraction_result: dict[str, Any]
    rag_context: list[dict[str, Any]]
    audit_decision: dict[str, Any]
    confidence: float | None
    retry_count: int
    fallback_level: int
    next_action: str
    error_message: str | None
    agent_logs: list[dict[str, Any]]
    stream_seq: NotRequired[int]
    rag_query: NotRequired[str]
    rag_response: NotRequired[dict[str, Any]]
    fallback_path: NotRequired[str]
    fallback_cases: NotRequired[list[dict[str, Any]]]
    t1_candidate: NotRequired[dict[str, str] | None]
    fuzzy_candidate: NotRequired[dict[str, str] | None]
    long_term_memory: NotRequired[list[dict[str, Any]]]
    short_term_memory: NotRequired[list[dict[str, Any]]]
    summary_buffer: NotRequired[dict[str, Any] | None]
    memory_context: NotRequired[str | None]


class Retriever(Protocol):
    def search(self, request: RagSearchRequest) -> RagSearchResponse: ...


def run_item(
    state: ReconciliationState,
    *,
    extraction_agent: ExtractionAgent = extraction_agent,
    trace_agent: TraceAgent = trace_agent,
    audit_agent: AuditAgent = audit_agent,
    retriever: Retriever = rule_retriever,
    fallback_case_provider: FallbackCaseProvider = ledger_fallback_case_provider,
    emitter: StreamEmitter | None = None,
) -> ReconciliationState:
    emitter = emitter or NullEmitter()
    bind_trace_context(
        trace_id=state["task_id"],
        user_id=state["user_id"],
        thread_id=state["thread_id"],
    )
    log.info(
        "workflow_node_start",
        agent_name="Workflow",
        step="run_item",
        exception_branch=state.get("exception_branch"),
    )
    state = memory_hook(state)

    flow_id = _flow_id(state)
    summary = _combined_text(state, "summary")
    remark = _combined_text(state, "remark") or None
    exception_branch = state.get("exception_branch")
    math_result = state.get("math_result", {})
    trace_payload: dict[str, Any] | None = None

    if exception_branch == "BE-R004" and _contains_reversal_hint(summary, remark):
        extraction_result = extraction_agent.extract(
            flow_id=flow_id,
            summary=summary,
            remark=remark,
        )
        state["extraction_result"] = _model_or_mapping_dump(extraction_result)
        _append_agent_log(state, {
            "agent_name": "ExtractionAgent",
            "step": "extract",
            "flow_id": flow_id,
            "prompt_version": getattr(extraction_agent, "prompt_version", None),
            **_llm_usage(extraction_agent),
        }, emitter)

    if exception_branch in TRACE_BRANCHES:
        trace_kwargs = {
            "flow_id": flow_id,
            "summary": summary,
            "transaction_date": _transaction_date(state),
            "amount": _optional_string(math_result.get("bank_amount") or math_result.get("clear_amount")),
            "remark": remark,
        }
        if exception_branch == "BC-R003":
            trace_kwargs["cutoff_t1_context"] = state.get("t1_candidate")
        trace_result = trace_agent.trace(**trace_kwargs)
        trace_payload = _model_or_mapping_dump(trace_result)
        _append_agent_log(state, {
            "agent_name": "TraceAgent",
            "step": "trace",
            "flow_id": flow_id,
            "output": trace_payload,
            "prompt_version": getattr(trace_agent, "prompt_version", None),
            **_llm_usage(trace_agent),
        }, emitter)

    rag_response = _retrieve_rag_response(state, retriever, emitter)
    rag_items = rag_response.items
    state["rag_context"] = [item.model_dump(mode="json") for item in rag_items]
    state["rag_response"] = rag_response.model_dump(mode="json")
    _emit_stream_row(
        state,
        {
            "agent_name": "RuleRetriever",
            "step": "retrieve",
            "flow_id": flow_id,
            "query": state.get("rag_query") or _build_rag_query(state),
            "chunk_ids": [item.chunk_id for item in rag_items],
            "best_score": max((item.score for item in rag_items), default=None),
        },
        emitter,
        StreamEventType.RAG_RETRIEVED,
    )

    if state.get("error_type") == "FUZZY_MATCH_CANDIDATE":
        return _run_fuzzy_candidate_confirmation(
            state=state,
            audit_agent=audit_agent,
            rag_items=rag_items,
            emitter=emitter,
        )

    audit_kwargs = {
        "flow_id": flow_id,
        "error_type": state.get("error_type") or "",
        "exception_branch": exception_branch,
        "bank_amount": _optional_string(math_result.get("bank_amount")),
        "clear_amount": _optional_string(math_result.get("clear_amount")),
        "amount_diff": _optional_string(math_result.get("amount_diff")),
        "evidence": rag_items,
    }
    if exception_branch == "BC-R003":
        audit_kwargs["trace_context"] = trace_payload

    audit_decision = _audit_with_schema_retry(
        state=state,
        audit_agent=audit_agent,
        audit_kwargs=audit_kwargs,
        emitter=emitter,
    )
    _append_agent_log(state, {
        "agent_name": "AuditAgent",
        "step": "decide_with_llm",
        "flow_id": flow_id,
        "fallback_level": 1,
        "output_payload": audit_decision.model_dump(mode="json"),
        "prompt_version": getattr(audit_agent, "prompt_version", None),
        **_llm_usage(audit_agent),
    }, emitter)

    fallback_path = "L1"
    if state.get("error_message") == "schema validation failed":
        fallback_path = "HUMAN"
    elif not rag_items:
        audit_decision = mark_fallback(audit_decision, fallback_level=0, next_action="PENDING_HUMAN")
        fallback_path = "HUMAN"
    elif l1_requires_l2(audit_decision, rag_items):
        fallback_path = "L1->L2"
        state["fallback_cases"] = fallback_case_provider.confirmed_cases(
            user_id=state["user_id"],
            exception_branch=exception_branch,
        )
        audit_decision = _audit_with_schema_retry(
            state=state,
            audit_agent=audit_agent,
            audit_kwargs={
                "flow_id": flow_id,
                "error_type": state.get("error_type") or "",
                "exception_branch": exception_branch,
                "bank_amount": _optional_string(math_result.get("bank_amount")),
                "clear_amount": _optional_string(math_result.get("clear_amount")),
                "amount_diff": _optional_string(math_result.get("amount_diff")),
                "evidence": rag_items,
                "few_shot_cases": state["fallback_cases"],
            },
            emitter=emitter,
        )
        if state.get("error_message") == "schema validation failed":
            fallback_path = "L1->L2->HUMAN"
            state["audit_decision"] = audit_decision.model_dump(mode="json")
            state["confidence"] = audit_decision.confidence
            state["fallback_level"] = audit_decision.fallback_level
            state["fallback_path"] = fallback_path
            state["next_action"] = audit_decision.next_action
            return state
        audit_decision = mark_fallback(audit_decision, fallback_level=2)
        _append_agent_log(state, {
            "agent_name": "AuditAgent",
            "step": "decide_with_llm",
            "flow_id": flow_id,
            "fallback_level": 2,
            "few_shot_rows": len(state["fallback_cases"]),
            "output_payload": audit_decision.model_dump(mode="json"),
            "prompt_version": getattr(audit_agent, "prompt_version", None),
            **_llm_usage(audit_agent),
        }, emitter)
        if confidence_is_low(audit_decision.confidence):
            fallback_path = "L1->L2->L3"
            trace_kwargs = {
                "flow_id": flow_id,
                "summary": summary,
                "transaction_date": _transaction_date(state),
                "amount": _optional_string(
                    math_result.get("bank_amount") or math_result.get("clear_amount")
                ),
                "remark": remark,
            }
            if exception_branch == "BC-R003":
                trace_kwargs["cutoff_t1_context"] = state.get("t1_candidate")
            trace_result = trace_agent.trace(**trace_kwargs)
            trace_payload = _model_or_mapping_dump(trace_result)
            _append_agent_log(state, {
                "agent_name": "TraceAgent",
                "step": "trace",
                "flow_id": flow_id,
                "output": trace_payload,
                "fallback_level": 3,
                "prompt_version": getattr(trace_agent, "prompt_version", None),
                **_llm_usage(trace_agent),
            }, emitter)
            audit_decision = _audit_with_schema_retry(
                state=state,
                audit_agent=audit_agent,
                audit_kwargs={
                    "flow_id": flow_id,
                    "error_type": state.get("error_type") or "",
                    "exception_branch": exception_branch,
                    "bank_amount": _optional_string(math_result.get("bank_amount")),
                    "clear_amount": _optional_string(math_result.get("clear_amount")),
                    "amount_diff": _optional_string(math_result.get("amount_diff")),
                    "evidence": rag_items,
                    "few_shot_cases": state["fallback_cases"],
                    "trace_context": trace_payload,
                },
                emitter=emitter,
            )
            if state.get("error_message") == "schema validation failed":
                fallback_path = "L1->L2->L3->HUMAN"
                state["audit_decision"] = audit_decision.model_dump(mode="json")
                state["confidence"] = audit_decision.confidence
                state["fallback_level"] = audit_decision.fallback_level
                state["fallback_path"] = fallback_path
                state["next_action"] = audit_decision.next_action
                return state
            audit_decision = mark_fallback(audit_decision, fallback_level=3)
            _append_agent_log(state, {
                "agent_name": "AuditAgent",
                "step": "decide_with_llm",
                "flow_id": flow_id,
                "fallback_level": 3,
                "output_payload": audit_decision.model_dump(mode="json"),
                "prompt_version": getattr(audit_agent, "prompt_version", None),
                **_llm_usage(audit_agent),
            }, emitter)
            if confidence_is_low(float(trace_payload.get("confidence", 0.0))):
                fallback_path = "L1->L2->L3->HUMAN"
                audit_decision.reason = f"{audit_decision.reason}；L3 追溯置信度不足，转人工。"
                audit_decision = mark_fallback(
                    audit_decision,
                    fallback_level=3,
                    next_action="PENDING_HUMAN",
                )
    state["audit_decision"] = audit_decision.model_dump(mode="json")
    state["confidence"] = audit_decision.confidence
    state["fallback_level"] = audit_decision.fallback_level
    state["fallback_path"] = fallback_path
    _apply_post_hooks(state, audit_decision, emitter)
    _emit_stream_row(
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


def _run_fuzzy_candidate_confirmation(
    *,
    state: ReconciliationState,
    audit_agent: AuditAgent,
    rag_items: list[RagSearchItem],
    emitter: StreamEmitter,
) -> ReconciliationState:
    flow_id = _flow_id(state)
    math_result = state.get("math_result", {})
    candidate = state.get("fuzzy_candidate") or {}
    audit_kwargs = {
        "flow_id": flow_id,
        "error_type": "FUZZY_MATCH_CANDIDATE",
        "exception_branch": "BE-R007",
        "bank_amount": _optional_string(math_result.get("bank_amount")),
        "clear_amount": _optional_string(math_result.get("clear_amount")),
        "amount_diff": _optional_string(math_result.get("amount_diff")),
        "evidence": rag_items,
        "match_candidate_context": candidate,
    }
    decision = _audit_with_schema_retry(
        state=state,
        audit_agent=audit_agent,
        audit_kwargs=audit_kwargs,
        emitter=emitter,
    )
    _append_agent_log(state, {
        "agent_name": "AuditAgent",
        "step": "confirm_match",
        "flow_id": flow_id,
        "fallback_level": 0,
        "output_payload": decision.model_dump(mode="json"),
        "prompt_version": getattr(audit_agent, "prompt_version", None),
        **_llm_usage(audit_agent),
    }, emitter)

    current_amount = _to_decimal(math_result.get("bank_amount")) or _to_decimal(
        math_result.get("clear_amount")
    )
    candidate_amount = _to_decimal(candidate.get("amount"))
    fallback_path = "L1"
    if not rag_items or confidence_is_low(decision.confidence):
        decision.decision = "PENDING_HUMAN"
        decision.ai_suggestion = "PENDING_HUMAN"
        decision.next_action = "PENDING_HUMAN"
        decision.fallback_level = 0
        fallback_path = "HUMAN"
    elif decision.decision == "AUTO_FIXED" and current_amount != candidate_amount:
        state["error_type"] = "AMOUNT_MISMATCH"
        state["exception_branch"] = "BE-R002"
        difference = None
        if current_amount is not None and candidate_amount is not None:
            difference = abs(current_amount - candidate_amount)
        state["math_result"] = {
            "bank_amount": _optional_string(current_amount),
            "clear_amount": _optional_string(candidate_amount),
            "amount_diff": _optional_string(difference),
        }
        decision = _audit_with_schema_retry(
            state=state,
            audit_agent=audit_agent,
            audit_kwargs={
                "flow_id": flow_id,
                "error_type": "AMOUNT_MISMATCH",
                "exception_branch": "BE-R002",
                "bank_amount": _optional_string(current_amount),
                "clear_amount": _optional_string(candidate_amount),
                "amount_diff": _optional_string(difference),
                "evidence": rag_items,
            },
            emitter=emitter,
        )
        _append_agent_log(state, {
            "agent_name": "AuditAgent",
            "step": "decide_with_llm",
            "flow_id": flow_id,
            "fallback_level": 0,
            "output_payload": decision.model_dump(mode="json"),
            "prompt_version": getattr(audit_agent, "prompt_version", None),
            **_llm_usage(audit_agent),
        }, emitter)
    elif decision.decision == "UNRESOLVED":
        if math_result.get("bank_amount") is not None:
            state["error_type"] = "BOOK_UNRECORDED"
            state["exception_branch"] = "BE-R006"
        else:
            state["error_type"] = "BANK_UNARRIVED"
            state["exception_branch"] = "BE-R005"
        decision.decision = "PENDING_HUMAN"
        decision.ai_suggestion = "PENDING_HUMAN"
        decision.next_action = "PENDING_HUMAN"

    state["audit_decision"] = decision.model_dump(mode="json")
    state["confidence"] = decision.confidence
    state["fallback_level"] = decision.fallback_level
    state["fallback_path"] = fallback_path
    _apply_post_hooks(state, decision, emitter)
    _emit_stream_row(
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


def _audit_with_schema_retry(
    *,
    state: ReconciliationState,
    audit_agent: AuditAgent,
    audit_kwargs: dict[str, Any],
    emitter: StreamEmitter,
) -> AuditDecision:
    max_attempts = 3
    state["error_message"] = None
    audit_kwargs = dict(audit_kwargs)
    audit_kwargs["memory_context"] = state.get("memory_context")
    for attempt in range(1, max_attempts + 1):
        try:
            decision = schema_hook(audit_agent.decide_with_llm(**audit_kwargs))
            state["retry_count"] = attempt - 1
            return decision
        except SchemaValidationError as exc:
            del exc
            log.warning(
                "schema_hook_retry",
                hook_name="SchemaHook",
                retry_count=attempt,
                flow_id=audit_kwargs.get("flow_id"),
            )
            _append_agent_log(state, {
                "agent_name": "SchemaHook",
                "step": "schema_validate",
                "flow_id": audit_kwargs.get("flow_id"),
                "retry_count": attempt,
                "error_message": "schema validation failed",
            }, emitter)

    state["retry_count"] = max_attempts
    state["error_message"] = "schema validation failed"
    return AuditDecision(
        flow_id=str(audit_kwargs.get("flow_id") or ""),
        decision="PENDING_HUMAN",
        risk_level="HIGH",
        reason="SchemaHook 校验失败，重试 3 次后转人工。",
        ai_suggestion="PENDING_HUMAN",
        evidence=[],
        confidence=0.0,
        fallback_applied=True,
        fallback_level=1,
        next_action="PENDING_HUMAN",
    )


def _retrieve_rag_response(
    state: ReconciliationState,
    retriever: Retriever,
    emitter: StreamEmitter,
) -> RagSearchResponse:
    query = state.get("rag_query") or _build_rag_query(state)
    previous_state = rag_circuit_breaker.state
    if not rag_circuit_breaker.allow_request():
        _append_rag_breaker_log(
            state,
            breaker_state=rag_circuit_breaker.state,
            reason="breaker open, skip rag retrieval",
            query=query,
            emitter=emitter,
        )
        log.warning(
            "rag_circuit_breaker_open",
            breaker_state=rag_circuit_breaker.state,
            scenario_type=state["scenario_type"],
            query=query,
        )
        return RagSearchResponse(items=[], rewritten_query=None)

    request = RagSearchRequest(
        query=query,
        top_k=settings.rag_rerank_top_k,
        min_score=0.0,
        scenario_type=state["scenario_type"],
        enable_rewrite=settings.enable_rag_rewrite,
        enable_hybrid=settings.enable_rag_hybrid,
        enable_reranker=settings.enable_rag_reranker,
    )
    try:
        response = retriever.search(request)
    except Exception as exc:
        breaker_state = rag_circuit_breaker.record_failure()
        _append_rag_breaker_log(
            state,
            breaker_state=breaker_state,
            reason=str(exc),
            query=query,
            emitter=emitter,
        )
        log.warning(
            "rag_circuit_breaker_failure",
            breaker_state=breaker_state,
            scenario_type=state["scenario_type"],
            query=query,
            error=str(exc),
        )
        return RagSearchResponse(items=[], rewritten_query=None)

    breaker_state = rag_circuit_breaker.record_success()
    if previous_state == "HALF_OPEN":
        _append_rag_breaker_log(
            state,
            breaker_state=breaker_state,
            reason="half-open probe succeeded",
            query=query,
            emitter=emitter,
        )
        log.warning(
            "rag_circuit_breaker_recovered",
            breaker_state=breaker_state,
            scenario_type=state["scenario_type"],
            query=query,
        )
    return response


def _append_rag_breaker_log(
    state: ReconciliationState,
    *,
    breaker_state: str,
    reason: str,
    query: str,
    emitter: StreamEmitter,
) -> None:
    _append_agent_log(state, {
        "agent_name": "RAGCircuitBreaker",
        "step": "retrieve",
        "hook_name": "RAGCircuitBreaker",
        "breaker_state": breaker_state,
        "reason": reason,
        "query": query,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }, emitter)


def _apply_post_hooks(
    state: ReconciliationState,
    audit_decision: AuditDecision,
    emitter: StreamEmitter,
) -> None:
    rag_items = [RagSearchItem.model_validate(item) for item in state["rag_context"]]
    constraint = constraint_hook(
        audit_decision,
        amount_diff=_to_decimal(state.get("math_result", {}).get("amount_diff")),
        rag_best_score=max((item.score for item in rag_items), default=None),
    )
    if not constraint.ok:
        violated_suffix = f"；违反约束: {', '.join(constraint.violated)}"
        audit_decision.reason = f"{audit_decision.reason}{violated_suffix}" if audit_decision.reason else (
            f"违反约束: {', '.join(constraint.violated)}"
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
    _append_agent_log(state, {
        "agent_name": "DecisionHook",
        "step": "post_hook_route",
        "flow_id": audit_decision.flow_id,
        "violated": constraint.violated,
        "next_action": route,
    }, emitter)


def _append_agent_log(
    state: ReconciliationState,
    row: dict[str, Any],
    emitter: StreamEmitter,
) -> None:
    state["agent_logs"].append(row)
    _emit_stream_row(state, row, emitter)


def _emit_stream_row(
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


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _build_rag_query(state: ReconciliationState) -> str:
    math_result = state.get("math_result", {})
    return (
        f"{state.get('error_type') or ''} {state.get('exception_branch') or ''} "
        f"bank_amount={_optional_string(math_result.get('bank_amount'))} "
        f"clear_amount={_optional_string(math_result.get('clear_amount'))} "
        f"amount_diff={_optional_string(math_result.get('amount_diff'))}"
    )


def _contains_reversal_hint(summary: str, remark: str | None) -> bool:
    text = f"{summary} {remark or ''}"
    return any(keyword in text for keyword in REVERSAL_HINTS)


def _flow_id(state: ReconciliationState) -> str:
    return str(
        state["source_a_item"].get("flow_id")
        or state["source_b_item"].get("flow_id")
        or state["current_queue_id"]
        or ""
    )


def _combined_text(state: ReconciliationState, key: str) -> str:
    values = [
        str(item.get(key)).strip()
        for item in (state["source_a_item"], state["source_b_item"])
        if item.get(key) is not None and str(item.get(key)).strip()
    ]
    return " ".join(values)


def _transaction_date(state: ReconciliationState) -> str | None:
    for key in ("accounting_date", "trade_date", "transaction_date"):
        value = state["source_a_item"].get(key) or state["source_b_item"].get(key)
        if value is not None:
            return str(value)
    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _model_or_mapping_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value)


def _llm_usage(agent: Any) -> dict[str, int | bool]:
    result = getattr(agent, "last_llm_result", None)
    if result is None:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "llm_tokens": 0,
            "cached": False,
        }
    prompt_tokens = int(getattr(result, "prompt_tokens", 0))
    completion_tokens = int(getattr(result, "completion_tokens", 0))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "llm_tokens": prompt_tokens + completion_tokens,
        "cached": bool(getattr(result, "cached", False)),
    }

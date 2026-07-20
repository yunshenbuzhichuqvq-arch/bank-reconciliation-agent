from __future__ import annotations

from decimal import Decimal, InvalidOperation
from threading import local
from typing import Any, NamedTuple, NotRequired, Protocol, TypedDict

from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from bank_reconciliation_agent.agents.audit_agent import AuditAgent, AuditDecision
from bank_reconciliation_agent.agents.extraction_agent import (
    ExtractionAgent,
    ExtractionResult,
)
from bank_reconciliation_agent.agents.trace_agent import TraceAgent, TraceAgentError
from bank_reconciliation_agent.core.llm.provider import get_llm_provider
from bank_reconciliation_agent.core.logging import bind_trace_context, log
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from bank_reconciliation_agent.schemas.stream import StreamEventType
from bank_reconciliation_agent.schemas.tools import (
    ConfirmedCasesOutput,
    LoadConfirmedCasesArgs,
    LookupT1ContextArgs,
    SearchRulesArgs,
    SearchRulesOutput,
    T1ContextOutput,
    ToolCallResult,
    ToolContext,
)
from bank_reconciliation_agent.services.fallback import (
    confidence_is_low,
    l1_requires_l2,
    mark_fallback,
)
from bank_reconciliation_agent.services.hooks import (
    SchemaValidationError,
    constraint_hook,
    decision_hook,
    schema_hook,
)
from bank_reconciliation_agent.services.stream_emitter import (
    NullEmitter,
    StreamEmitter,
    to_stream_event,
    to_trace_span_event,
)
from bank_reconciliation_agent.services.tool_adapters import default_tool_executor
from bank_reconciliation_agent.services.tool_executor import safe_tool_projection
from bank_reconciliation_agent.services.trace import NoOpRecorder, TraceRecorder
from bank_reconciliation_agent.schemas.trace import (
    GuardOutcome,
    SpanStatus,
    SpanType,
)


Recorder = TraceRecorder | NoOpRecorder


class WorkflowAgentSuite(NamedTuple):
    audit_agent: AuditAgent
    extraction_agent: ExtractionAgent
    trace_agent: TraceAgent


_WORKFLOW_AGENT_LOCAL = local()


def _thread_agent_suite() -> WorkflowAgentSuite:
    suite = getattr(_WORKFLOW_AGENT_LOCAL, "suite", None)
    provider_factory = get_llm_provider
    if (
        suite is None
        or getattr(_WORKFLOW_AGENT_LOCAL, "provider_factory", None) is not provider_factory
    ):
        provider = provider_factory()
        suite = WorkflowAgentSuite(
            audit_agent=AuditAgent(provider=provider),
            extraction_agent=ExtractionAgent(provider=provider),
            trace_agent=TraceAgent(provider=provider),
        )
        _WORKFLOW_AGENT_LOCAL.suite = suite
        _WORKFLOW_AGENT_LOCAL.provider_factory = provider_factory
    return suite


REVERSAL_HINTS = ("冲正", "红冲", "退款", "抹账", "撤销")
TRACE_BRANCHES = {"BE-R005", "BE-R006", "BC-R003"}
BANK_ENTERPRISE_LLM_AUDIT_BRANCHES = {"BE-R007"}


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
    recorder: NotRequired[Recorder]


class ToolExecutorProtocol(Protocol):
    def execute(
        self,
        name: str,
        args: Any,
        context: ToolContext,
    ) -> ToolCallResult: ...


_NOOP_RECORDER = NoOpRecorder()


def _recorder(state: ReconciliationState) -> Recorder:
    return state.get("recorder") or _NOOP_RECORDER


def _emit_trace_span(
    state: ReconciliationState,
    recorder: Recorder,
    emitter: StreamEmitter | None,
) -> None:
    """Emit a ``trace_span`` SSE event for the most recently completed span.

    The whole projection path — reading the last completed span, building the
    canonical ``TraceSpanView``, advancing the SSE seq and calling
    ``emitter.emit`` — runs inside a single best-effort boundary. Any failure
    only produces a sanitized warning and never affects the business decision,
    ledger state, recorder snapshot or the later batch persistence.
    """
    if emitter is None:
        return
    from bank_reconciliation_agent.schemas.trace import TraceSpanView

    try:
        span = recorder.last_completed_span()
        if span is None:
            return
        view = TraceSpanView.from_span(span)
        stream_seq = int(state.get("stream_seq", 0)) + 1
        state["stream_seq"] = stream_seq
        event = to_trace_span_event(view, seq=stream_seq)
        emitter.emit(event)
    except Exception as exc:
        log.warning(
            "trace_span_emit_failed",
            error_type=type(exc).__name__,
        )


_TOOL_STATUS_MAP: dict[str, tuple[SpanStatus, str | None]] = {
    "SUCCEEDED": (SpanStatus.SUCCEEDED, "RESULT"),
    "EMPTY": (SpanStatus.SUCCEEDED, "EMPTY"),
    "FAILED": (SpanStatus.FAILED, None),
}


def _complete_tool_span(
    state: ReconciliationState,
    handle: Any,
    result: ToolCallResult,
    projection: dict[str, Any],
    *,
    emitter: StreamEmitter | None = None,
) -> None:
    """Complete the pending TOOL span allocated before ``execute()``."""
    recorder = _recorder(state)
    status, outcome = _TOOL_STATUS_MAP.get(str(projection["status"]), (SpanStatus.FAILED, None))
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
    _emit_trace_span(state, recorder, emitter)


def _agent_recovered_error_type(agent: Any, usage: dict[str, Any]) -> str | None:
    """Return the first failed transport ``failure_type`` when a retry recovered.

    Sourced from the safe ``LLMResult.attempts`` metadata; ``None`` when there
    was no retry recovery or no recorded failure attempt.
    """
    if not usage.get("retry_recovered"):
        return None
    result = getattr(agent, "last_llm_result", None)
    attempts = getattr(result, "attempts", None) or []
    for attempt in attempts:
        if getattr(attempt, "outcome", None) == "failure" and attempt.failure_type is not None:
            return attempt.failure_type
    return None


def _finish_agent_span(
    state: ReconciliationState,
    handle: Any,
    *,
    agent: Any,
    status: SpanStatus | None,
    emitter: StreamEmitter | None = None,
) -> None:
    """Complete the pending AGENT span allocated before the Agent call.

    When *status* is ``None`` it is inferred from the safe LLM usage summary.
    """
    recorder = _recorder(state)
    usage = _llm_usage(agent)
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
        recovered_error_type=_agent_recovered_error_type(agent, usage),
        structured_repair_attempted=bool(usage.get("structured_repair_attempted", False)),
        structured_repair_succeeded=bool(usage.get("structured_repair_succeeded", False)),
        error_type=usage.get("final_failure_type"),
        fallback_reason=usage.get("fallback_reason"),
    )
    _emit_trace_span(state, recorder, emitter)


def run_item(
    state: ReconciliationState,
    *,
    extraction_agent: ExtractionAgent | None = None,
    trace_agent: TraceAgent | None = None,
    audit_agent: AuditAgent | None = None,
    tool_executor: ToolExecutorProtocol = default_tool_executor,
    emitter: StreamEmitter | None = None,
) -> ReconciliationState:
    if extraction_agent is None or trace_agent is None or audit_agent is None:
        suite = _thread_agent_suite()
        extraction_agent = extraction_agent or suite.extraction_agent
        trace_agent = trace_agent or suite.trace_agent
        audit_agent = audit_agent or suite.audit_agent
    emitter = emitter or NullEmitter()
    recorder = _recorder(state)
    bind_trace_context(
        trace_id=recorder.trace_id or state["task_id"],
        user_id=state["user_id"],
        thread_id=state["thread_id"],
        task_id=state["task_id"],
        flow_id=_flow_id(state),
    )
    log.info(
        "workflow_node_start",
        agent_name="Workflow",
        step="run_item",
        exception_branch=state.get("exception_branch"),
    )
    flow_id = _flow_id(state)
    exception_branch = state.get("exception_branch")
    if exception_branch:
        with recorder.span(SpanType.ROUTE, str(exception_branch)):
            pass
        _emit_trace_span(state, recorder, emitter)
    summary = _combined_text(state, "summary")
    remark = _combined_text(state, "remark") or None
    math_result = state.get("math_result", {})
    trace_payload: dict[str, Any] | None = None

    if exception_branch == "BE-R004" and _contains_reversal_hint(summary, remark):
        with recorder.span(SpanType.ROUTE, "RuleExtraction"):
            extraction_result = _extract_reversal_hint(summary=summary, remark=remark)
        _emit_trace_span(state, recorder, emitter)
        state["extraction_result"] = _model_or_mapping_dump(extraction_result)
        _append_agent_log(
            state,
            {
                "agent_name": "RuleExtractor",
                "step": "extract_deterministic",
                "flow_id": flow_id,
                "execution_mode": "DETERMINISTIC",
                "output": state["extraction_result"],
                **_zero_llm_usage(),
            },
            emitter,
        )

    cutoff_t1_context: dict[str, str] | None = None
    if exception_branch == "BC-R003":
        t1_result = _execute_tool(
            tool_executor,
            "lookup_t1_context",
            LookupT1ContextArgs(),
            state,
            emitter,
        )
        if t1_result.status == "FAILED":
            return _tool_fail_closed_item(
                state,
                flow_id=flow_id,
                tool_result=t1_result,
                emitter=emitter,
            )
        if t1_result.status == "SUCCEEDED" and isinstance(t1_result.result, T1ContextOutput):
            cutoff_t1_context = {
                "flow_id": t1_result.result.flow_id,
                "accounting_date": t1_result.result.accounting_date.isoformat(),
            }

    if exception_branch in TRACE_BRANCHES and not (
        state["scenario_type"] == "BANK_ENTERPRISE"
        and exception_branch in {"BE-R005", "BE-R006"}
    ):
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
            trace_kwargs["cutoff_t1_context"] = cutoff_t1_context
        _trace_handle = recorder.start_agent("TraceAgent")
        try:
            trace_result = trace_agent.trace(**trace_kwargs)
        except TraceAgentError:
            _finish_agent_span(
                state,
                _trace_handle,
                agent=trace_agent,
                status=SpanStatus.FAILED,
                emitter=emitter,
            )
            return _fail_closed_item(
                state,
                flow_id=flow_id,
                agent=trace_agent,
                agent_name="TraceAgent",
                step="trace",
                emitter=emitter,
            )
        _finish_agent_span(
            state,
            _trace_handle,
            agent=trace_agent,
            status=SpanStatus.SUCCEEDED,
            emitter=emitter,
        )
        trace_payload = _model_or_mapping_dump(trace_result)
        _append_agent_log(
            state,
            {
                "agent_name": "TraceAgent",
                "step": "trace",
                "flow_id": flow_id,
                "output": trace_payload,
                "prompt_version": getattr(trace_agent, "prompt_version", None),
                **_llm_usage(trace_agent),
            },
            emitter,
        )

    search_result = _execute_tool(
        tool_executor,
        "search_rules",
        SearchRulesArgs(query=state.get("rag_query") or _build_rag_query(state)),
        state,
        emitter,
    )
    if search_result.status != "SUCCEEDED":
        return _tool_fail_closed_item(
            state,
            flow_id=flow_id,
            tool_result=search_result,
            emitter=emitter,
        )

    rag_output: SearchRulesOutput = search_result.result
    rag_items = list(rag_output.items)
    rag_response = RagSearchResponse(items=rag_items, rewritten_query=rag_output.rewritten_query)
    state["rag_context"] = [item.model_dump(mode="json") for item in rag_items]
    state["rag_response"] = rag_response.model_dump(mode="json")
    _emit_stream_row(
        state,
        {
            "agent_name": "RuleRetriever",
            "step": "retrieve",
            "flow_id": flow_id,
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

    audit_decision, audit_execution_mode = _audit_decision_for_state(
        state=state,
        audit_agent=audit_agent,
        audit_kwargs=audit_kwargs,
        emitter=emitter,
    )
    _append_agent_log(
        state,
        {
            "agent_name": "AuditAgent",
            "step": (
                "decide_with_llm"
                if audit_execution_mode == "LLM"
                else "decide_deterministic"
            ),
            "flow_id": flow_id,
            "fallback_level": 1,
            "execution_mode": audit_execution_mode,
            "output_payload": audit_decision.model_dump(mode="json"),
            "prompt_version": (
                getattr(audit_agent, "prompt_version", None)
                if audit_execution_mode == "LLM"
                else None
            ),
            **_llm_usage(audit_agent),
        },
        emitter,
    )

    fallback_path = "L1"
    if audit_execution_mode == "DETERMINISTIC":
        fallback_path = "RULE"
    elif state.get("error_message") == "schema validation failed":
        fallback_path = "HUMAN"
    elif l1_requires_l2(audit_decision):
        fallback_path = "L1->L2"
        cases_result = _execute_tool(
            tool_executor,
            "load_confirmed_cases",
            LoadConfirmedCasesArgs(),
            state,
            emitter,
            fallback_level=2,
        )
        if cases_result.status != "SUCCEEDED":
            audit_decision = mark_fallback(
                audit_decision,
                fallback_level=2,
                next_action="PENDING_HUMAN",
            )
            audit_decision.decision = "PENDING_HUMAN"
            audit_decision.ai_suggestion = "PENDING_HUMAN"
            fallback_path = "L1->L2->HUMAN"
            state["audit_decision"] = audit_decision.model_dump(mode="json")
            state["confidence"] = audit_decision.confidence
            state["fallback_level"] = audit_decision.fallback_level
            state["fallback_path"] = fallback_path
            state["next_action"] = audit_decision.next_action
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
        cases_output: ConfirmedCasesOutput = cases_result.result
        state["fallback_cases"] = [case.model_dump(mode="json") for case in cases_output.items]
        audit_decision = _audit_decision_once(
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
        _append_agent_log(
            state,
            {
                "agent_name": "AuditAgent",
                "step": "decide_with_llm",
                "flow_id": flow_id,
                "fallback_level": 2,
                "few_shot_rows": len(state["fallback_cases"]),
                "output_payload": audit_decision.model_dump(mode="json"),
                "prompt_version": getattr(audit_agent, "prompt_version", None),
                **_llm_usage(audit_agent),
            },
            emitter,
        )
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
                trace_kwargs["cutoff_t1_context"] = cutoff_t1_context
            _l3_trace_handle = recorder.start_agent("TraceAgent")
            try:
                trace_result = trace_agent.trace(**trace_kwargs)
            except TraceAgentError:
                _finish_agent_span(
                    state,
                    _l3_trace_handle,
                    agent=trace_agent,
                    status=SpanStatus.FAILED,
                    emitter=emitter,
                )
                return _fail_closed_item(
                    state,
                    flow_id=flow_id,
                    agent=trace_agent,
                    agent_name="TraceAgent",
                    step="trace",
                    emitter=emitter,
                )
            _finish_agent_span(
                state,
                _l3_trace_handle,
                agent=trace_agent,
                status=SpanStatus.SUCCEEDED,
                emitter=emitter,
            )
            trace_payload = _model_or_mapping_dump(trace_result)
            _append_agent_log(
                state,
                {
                    "agent_name": "TraceAgent",
                    "step": "trace",
                    "flow_id": flow_id,
                    "output": trace_payload,
                    "fallback_level": 3,
                    "prompt_version": getattr(trace_agent, "prompt_version", None),
                    **_llm_usage(trace_agent),
                },
                emitter,
            )
            audit_decision = _audit_decision_once(
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
            _append_agent_log(
                state,
                {
                    "agent_name": "AuditAgent",
                    "step": "decide_with_llm",
                    "flow_id": flow_id,
                    "fallback_level": 3,
                    "output_payload": audit_decision.model_dump(mode="json"),
                    "prompt_version": getattr(audit_agent, "prompt_version", None),
                    **_llm_usage(audit_agent),
                },
                emitter,
            )
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
    decision, audit_execution_mode = _audit_decision_for_state(
        state=state,
        audit_agent=audit_agent,
        audit_kwargs=audit_kwargs,
        emitter=emitter,
    )
    _append_agent_log(
        state,
        {
            "agent_name": "AuditAgent",
            "step": "confirm_match",
            "flow_id": flow_id,
            "fallback_level": 0,
            "execution_mode": audit_execution_mode,
            "output_payload": decision.model_dump(mode="json"),
            "prompt_version": getattr(audit_agent, "prompt_version", None),
            **_llm_usage(audit_agent),
        },
        emitter,
    )

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
        decision, audit_execution_mode = _audit_decision_for_state(
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
        if audit_execution_mode == "DETERMINISTIC":
            fallback_path = "RULE"
        _append_agent_log(
            state,
            {
                "agent_name": "AuditAgent",
                "step": (
                    "decide_with_llm"
                    if audit_execution_mode == "LLM"
                    else "decide_deterministic"
                ),
                "flow_id": flow_id,
                "fallback_level": 0,
                "execution_mode": audit_execution_mode,
                "output_payload": decision.model_dump(mode="json"),
                "prompt_version": (
                    getattr(audit_agent, "prompt_version", None)
                    if audit_execution_mode == "LLM"
                    else None
                ),
                **_llm_usage(audit_agent),
            },
            emitter,
        )
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


def _fail_closed_item(
    state: ReconciliationState,
    *,
    flow_id: str,
    agent: Any,
    agent_name: str,
    step: str,
    emitter: StreamEmitter,
) -> ReconciliationState:
    """Close the current item to PENDING_HUMAN after a final LLM failure.

    Only the current item is failed closed; no task terminal state is written,
    no ARQ exception is raised, and Audit is not invoked so no auto-fix can slip
    through. A sanitized failure summary is appended for observability.
    """
    usage = _llm_usage(agent)
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
    _append_agent_log(
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


def _audit_decision_once(
    *,
    state: ReconciliationState,
    audit_agent: AuditAgent,
    audit_kwargs: dict[str, Any],
    emitter: StreamEmitter,
) -> AuditDecision:
    state["error_message"] = None
    state["retry_count"] = 0
    recorder = _recorder(state)
    _audit_handle = recorder.start_agent("AuditAgent")
    try:
        decision = schema_hook(audit_agent.decide_with_llm(**audit_kwargs))
    except SchemaValidationError:
        _finish_agent_span(
            state,
            _audit_handle,
            agent=audit_agent,
            status=SpanStatus.FAILED,
            emitter=emitter,
        )
        log.warning(
            "schema_hook_failed",
            hook_name="SchemaHook",
            flow_id=audit_kwargs.get("flow_id"),
        )
        _append_agent_log(
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

    _finish_agent_span(
        state,
        _audit_handle,
        agent=audit_agent,
        status=None,
        emitter=emitter,
    )
    return decision


def _audit_decision_for_state(
    *,
    state: ReconciliationState,
    audit_agent: AuditAgent,
    audit_kwargs: dict[str, Any],
    emitter: StreamEmitter,
) -> tuple[AuditDecision, str]:
    """Use rules for BANK_ENTERPRISE, retaining LLM confirmation only for R007.

    BANK_CLEARING intentionally keeps its existing LLM-backed behaviour.  The
    deterministic branch is still represented in Trace, but as a ROUTE span so
    Agent-span/token metrics continue to mean an actual model invocation.
    """
    exception_branch = str(audit_kwargs.get("exception_branch") or "")
    use_rule_first = (
        state["scenario_type"] == "BANK_ENTERPRISE"
        and exception_branch not in BANK_ENTERPRISE_LLM_AUDIT_BRANCHES
    )
    if not use_rule_first:
        return (
            _audit_decision_once(
                state=state,
                audit_agent=audit_agent,
                audit_kwargs=audit_kwargs,
                emitter=emitter,
            ),
            "LLM",
        )

    state["error_message"] = None
    state["retry_count"] = 0
    # Thread-local agents are reused across flows.  Clear stale usage only for
    # a fresh rule decision; the LLM path must retain invalid-call telemetry
    # when ``decide_with_llm`` falls back through ``AuditAgent.decide``.
    audit_agent.last_llm_result = None
    audit_agent.last_llm_summary = None
    recorder = _recorder(state)
    with recorder.span(SpanType.ROUTE, "RuleAudit"):
        decision = schema_hook(audit_agent.decide(**audit_kwargs))
    _emit_trace_span(state, recorder, emitter)
    return decision, "DETERMINISTIC"


def _build_tool_context(
    state: ReconciliationState,
    *,
    fallback_level: int = 0,
) -> ToolContext:
    return ToolContext(
        user_id=state["user_id"],
        task_id=state["task_id"],
        flow_id=_flow_id(state),
        scenario_type=state["scenario_type"],
        exception_branch=state.get("exception_branch") or "",
        fallback_level=fallback_level,
    )


def _execute_tool(
    tool_executor: ToolExecutorProtocol,
    name: str,
    args: Any,
    state: ReconciliationState,
    emitter: StreamEmitter,
    *,
    fallback_level: int = 0,
) -> ToolCallResult:
    context = _build_tool_context(state, fallback_level=fallback_level)
    handle = _recorder(state).start_tool(name)
    try:
        result = tool_executor.execute(name, args, context)
    except (OperationalError, RedisConnectionError):
        # Infrastructure read failure that escaped the Tool Executor (e.g. retry
        # exhaustion). Close the already-open span as FAILED with the Stage 28
        # stable tokens, then re-raise so the item is not falsely fail-closed.
        _finish_tool_span_failed(
            state,
            handle,
            error_type="TRANSIENT_READ_ERROR",
            fallback_reason="TOOL_TRANSIENT_READ_ERROR",
            emitter=emitter,
        )
        raise
    except Exception:
        _finish_tool_span_failed(
            state,
            handle,
            error_type="INTERNAL_ERROR",
            fallback_reason="TOOL_INTERNAL_ERROR",
            emitter=emitter,
        )
        raise
    projection = safe_tool_projection(result)
    _complete_tool_span(state, handle, result, projection, emitter=emitter)
    _append_agent_log(
        state,
        {
            "agent_name": "ToolExecutor",
            "step": "tool_call",
            "flow_id": _flow_id(state),
            **projection,
        },
        emitter,
    )
    return result


def _finish_tool_span_failed(
    state: ReconciliationState,
    handle: Any,
    *,
    error_type: str,
    fallback_reason: str,
    emitter: StreamEmitter | None = None,
) -> None:
    """Close a pending TOOL span as FAILED after ``execute()`` raised.

    Uses Stage 28 stable error/fallback tokens and never stores the exception
    text. ``attempt`` defaults to 1 because no safe physical-attempt metadata is
    available from a raised exception. The whole close + emit is best-effort:
    any fault here is swallowed so the original business exception keeps
    propagating unchanged via the caller's bare ``raise``.
    """
    try:
        recorder = _recorder(state)
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
        _emit_trace_span(state, recorder, emitter)
    except Exception as exc:
        log.warning("tool_span_close_failed", error_type=type(exc).__name__)


def _tool_fail_closed_item(
    state: ReconciliationState,
    *,
    flow_id: str,
    tool_result: ToolCallResult,
    emitter: StreamEmitter,
) -> ReconciliationState:
    """Close the current item to PENDING_HUMAN after a Tool EMPTY/FAILED outcome.

    Only the current item is failed closed; downstream Tools and LLM agents are
    not invoked. A stable fallback_reason is recorded, never an exception string.
    """
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
    guard_outcome = GuardOutcome.PASSED if constraint.ok else GuardOutcome.BLOCKED
    with _recorder(state).span(SpanType.GUARD, "ConstraintGuard", outcome=guard_outcome):
        pass
    _emit_trace_span(state, _recorder(state), emitter)
    if not constraint.ok:
        violated_suffix = f"；违反约束: {', '.join(constraint.violated)}"
        audit_decision.reason = (
            f"{audit_decision.reason}{violated_suffix}"
            if audit_decision.reason
            else (f"违反约束: {', '.join(constraint.violated)}")
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
    _append_agent_log(
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


def _extract_reversal_hint(*, summary: str, remark: str | None) -> ExtractionResult:
    """Classify explicit reversal keywords without a model call.

    This path runs only after ``_contains_reversal_hint`` succeeds.  It never
    guesses an original flow id; an id that is not supplied as a structured
    input remains ``None``.
    """
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


def _llm_usage(agent: Any) -> dict[str, Any]:
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


def _zero_llm_usage() -> dict[str, Any]:
    return _llm_usage(object())

"""Single-item workflow orchestration and compatibility exports.

State contracts, runtime observability, Tool execution and audit decisions live
in ``workflow_types``, ``workflow_runtime``, ``workflow_tools`` and
``workflow_decision``. This module should describe execution order only.
"""

from __future__ import annotations

from threading import local
from typing import Any, NamedTuple

from bank_reconciliation_agent.agents.audit_agent import AuditAgent
from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgent
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
)
from bank_reconciliation_agent.services.fallback import (
    confidence_is_low,
    l1_requires_l2,
    mark_fallback,
)
from bank_reconciliation_agent.services.stream_emitter import (
    NullEmitter,
    StreamEmitter,
)
from bank_reconciliation_agent.services.tool_adapters import default_tool_executor
from bank_reconciliation_agent.schemas.trace import (
    SpanStatus,
    SpanType,
)
from bank_reconciliation_agent.services.workflow_decision import (
    apply_post_hooks as _apply_post_hooks_impl,
    audit_decision_for_state as _audit_decision_for_state_impl,
    audit_decision_once as _audit_decision_once_impl,
    fail_closed_item as _fail_closed_item_impl,
)
from bank_reconciliation_agent.services.workflow_runtime import (
    append_agent_log as _append_agent_log_impl,
    build_rag_query as _build_rag_query_impl,
    combined_text as _combined_text_impl,
    contains_reversal_hint as _contains_reversal_hint_impl,
    emit_stream_row as _emit_stream_row_impl,
    emit_trace_span as _emit_trace_span,
    extract_reversal_hint as _extract_reversal_hint_impl,
    finish_agent_span as _finish_agent_span,
    flow_id as _flow_id_impl,
    llm_usage as _llm_usage_impl,
    model_or_mapping_dump as _model_or_mapping_dump_impl,
    optional_string as _optional_string_impl,
    recorder_for as _recorder,
    to_decimal as _to_decimal_impl,
    transaction_date as _transaction_date_impl,
    zero_llm_usage as _zero_llm_usage_impl,
)
from bank_reconciliation_agent.services.workflow_tools import (
    build_tool_context as _build_tool_context_impl,
    execute_tool as _execute_tool_impl,
    finish_tool_span_failed as _finish_tool_span_failed_impl,
    tool_fail_closed_item as _tool_fail_closed_item_impl,
)
from bank_reconciliation_agent.services.workflow_types import (
    TRACE_BRANCHES,
    ReconciliationState,
    ToolExecutorProtocol,
)


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


_fail_closed_item = _fail_closed_item_impl
_audit_decision_once = _audit_decision_once_impl
_audit_decision_for_state = _audit_decision_for_state_impl
_build_tool_context = _build_tool_context_impl
_execute_tool = _execute_tool_impl
_finish_tool_span_failed = _finish_tool_span_failed_impl
_tool_fail_closed_item = _tool_fail_closed_item_impl
_apply_post_hooks = _apply_post_hooks_impl
_append_agent_log = _append_agent_log_impl
_emit_stream_row = _emit_stream_row_impl
_to_decimal = _to_decimal_impl
_build_rag_query = _build_rag_query_impl
_contains_reversal_hint = _contains_reversal_hint_impl
_extract_reversal_hint = _extract_reversal_hint_impl
_flow_id = _flow_id_impl
_combined_text = _combined_text_impl
_transaction_date = _transaction_date_impl
_optional_string = _optional_string_impl
_model_or_mapping_dump = _model_or_mapping_dump_impl
_llm_usage = _llm_usage_impl
_zero_llm_usage = _zero_llm_usage_impl

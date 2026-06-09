from __future__ import annotations

from typing import Any, NotRequired, Protocol, TypedDict

from bank_reconciliation_agent.agents.audit_agent import AuditAgent, audit_agent
from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgent, extraction_agent
from bank_reconciliation_agent.agents.trace_agent import TraceAgent, trace_agent
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.logging import bind_trace_context, log
from bank_reconciliation_agent.rag.retriever import rule_retriever
from bank_reconciliation_agent.schemas.rag import RagSearchRequest, RagSearchResponse
from bank_reconciliation_agent.services.fallback import (
    FallbackCaseProvider,
    confidence_is_low,
    l1_requires_l2,
    ledger_fallback_case_provider,
    mark_fallback,
)


REVERSAL_HINTS = ("冲正", "红冲", "退款", "抹账", "撤销")
TRACE_BRANCHES = {"BE-R005", "BE-R006", "BC-R003"}


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
    rag_query: NotRequired[str]
    rag_response: NotRequired[dict[str, Any]]
    fallback_path: NotRequired[str]
    fallback_cases: NotRequired[list[dict[str, Any]]]
    t1_candidate: NotRequired[dict[str, str] | None]


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
) -> ReconciliationState:
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
        state["agent_logs"].append(
            {
                "agent_name": "ExtractionAgent",
                "step": "extract",
                "flow_id": flow_id,
                "prompt_version": getattr(extraction_agent, "prompt_version", None),
                **_llm_usage(extraction_agent),
            }
        )

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
        state["agent_logs"].append(
            {
                "agent_name": "TraceAgent",
                "step": "trace",
                "flow_id": flow_id,
                "output": trace_payload,
                "prompt_version": getattr(trace_agent, "prompt_version", None),
                **_llm_usage(trace_agent),
            }
        )

    rag_response = _retrieve_rag_response(state, retriever)
    rag_items = rag_response.items
    state["rag_context"] = [item.model_dump(mode="json") for item in rag_items]
    state["rag_response"] = rag_response.model_dump(mode="json")

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

    audit_decision = audit_agent.decide_with_llm(
        **audit_kwargs,
    )
    state["agent_logs"].append(
        {
            "agent_name": "AuditAgent",
            "step": "decide_with_llm",
            "flow_id": flow_id,
            "fallback_level": 1,
            "prompt_version": getattr(audit_agent, "prompt_version", None),
            **_llm_usage(audit_agent),
        }
    )

    fallback_path = "L1"
    if not rag_items:
        audit_decision = mark_fallback(audit_decision, fallback_level=0, next_action="PENDING_HUMAN")
        fallback_path = "HUMAN"
    elif l1_requires_l2(audit_decision, rag_items):
        fallback_path = "L1->L2"
        state["fallback_cases"] = fallback_case_provider.confirmed_cases(
            user_id=state["user_id"],
            exception_branch=exception_branch,
        )
        audit_decision = audit_agent.decide_with_llm(
            flow_id=flow_id,
            error_type=state.get("error_type") or "",
            exception_branch=exception_branch,
            bank_amount=_optional_string(math_result.get("bank_amount")),
            clear_amount=_optional_string(math_result.get("clear_amount")),
            amount_diff=_optional_string(math_result.get("amount_diff")),
            evidence=rag_items,
            few_shot_cases=state["fallback_cases"],
        )
        audit_decision = mark_fallback(audit_decision, fallback_level=2)
        state["agent_logs"].append(
            {
                "agent_name": "AuditAgent",
                "step": "decide_with_llm",
                "flow_id": flow_id,
                "fallback_level": 2,
                "few_shot_rows": len(state["fallback_cases"]),
                "prompt_version": getattr(audit_agent, "prompt_version", None),
                **_llm_usage(audit_agent),
            }
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
                trace_kwargs["cutoff_t1_context"] = state.get("t1_candidate")
            trace_result = trace_agent.trace(**trace_kwargs)
            trace_payload = _model_or_mapping_dump(trace_result)
            state["agent_logs"].append(
                {
                    "agent_name": "TraceAgent",
                    "step": "trace",
                    "flow_id": flow_id,
                    "output": trace_payload,
                    "fallback_level": 3,
                    "prompt_version": getattr(trace_agent, "prompt_version", None),
                    **_llm_usage(trace_agent),
                }
            )
            audit_decision = audit_agent.decide_with_llm(
                flow_id=flow_id,
                error_type=state.get("error_type") or "",
                exception_branch=exception_branch,
                bank_amount=_optional_string(math_result.get("bank_amount")),
                clear_amount=_optional_string(math_result.get("clear_amount")),
                amount_diff=_optional_string(math_result.get("amount_diff")),
                evidence=rag_items,
                few_shot_cases=state["fallback_cases"],
                trace_context=trace_payload,
            )
            audit_decision = mark_fallback(audit_decision, fallback_level=3)
            state["agent_logs"].append(
                {
                    "agent_name": "AuditAgent",
                    "step": "decide_with_llm",
                    "flow_id": flow_id,
                    "fallback_level": 3,
                    "prompt_version": getattr(audit_agent, "prompt_version", None),
                    **_llm_usage(audit_agent),
                }
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
    state["next_action"] = audit_decision.next_action
    return state


def _retrieve_rag_response(state: ReconciliationState, retriever: Retriever) -> RagSearchResponse:
    query = state.get("rag_query") or _build_rag_query(state)
    return retriever.search(
        RagSearchRequest(
            query=query,
            top_k=settings.rag_rerank_top_k,
            min_score=0.0,
            scenario_type=state["scenario_type"],
            enable_rewrite=settings.enable_rag_rewrite,
            enable_hybrid=settings.enable_rag_hybrid,
            enable_reranker=settings.enable_rag_reranker,
        )
    )


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


def _llm_usage(agent: Any) -> dict[str, int]:
    result = getattr(agent, "last_llm_result", None)
    if result is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "llm_tokens": 0}
    prompt_tokens = int(getattr(result, "prompt_tokens", 0))
    completion_tokens = int(getattr(result, "completion_tokens", 0))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "llm_tokens": prompt_tokens + completion_tokens,
    }

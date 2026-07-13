from decimal import Decimal

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.rag import query_enrichment
from bank_reconciliation_agent.schemas.rag import RagSearchRequest, RagSearchResponse
from bank_reconciliation_agent.services.reconciliation import (
    ReconciliationMatchResult,
    ReconciliationService,
)
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item
from tests.tool_workflow_helpers import RetrieverBackedToolExecutor


def _profile_terms() -> list[str]:
    config = query_enrichment.load_config(query_enrichment.DEFAULT_PROFILE_PATH)
    return list(config.profiles[0].terms)


def _profile_terms_suffix() -> str:
    return " ".join(_profile_terms())


def _service() -> ReconciliationService:
    return ReconciliationService.__new__(ReconciliationService)


def _match_result(*, error_type, exception_branch) -> ReconciliationMatchResult:
    return ReconciliationMatchResult(
        flow_id="FLOW-30-4",
        status="PENDING_AI",
        error_type=error_type,
        exception_branch=exception_branch,
        bank_amount=Decimal("100.00"),
        clear_amount=None,
        amount_diff=None,
    )


def test_build_rag_query_enriches_clearing_single_side_via_shared_helper() -> None:
    service = _service()
    result = _match_result(error_type="CLEARING_SINGLE_SIDE", exception_branch="BC-R001")
    query = service._build_rag_query(result, "BANK_CLEARING")
    assert query.endswith(" " + _profile_terms_suffix())


def test_build_rag_query_branch_only_bc_r001_enriches() -> None:
    service = _service()
    result = _match_result(error_type=None, exception_branch="BC-R001")
    query = service._build_rag_query(result, "BANK_CLEARING")
    assert query.endswith(" " + _profile_terms_suffix())


def test_build_rag_query_bank_enterprise_not_enriched() -> None:
    service = _service()
    result = _match_result(error_type="SINGLE_SIDE_MISSING", exception_branch=None)
    query = service._build_rag_query(result, "BANK_ENTERPRISE")
    for term in _profile_terms():
        assert term not in query


def test_build_rag_query_clearing_cutoff_bc_r003_not_enriched() -> None:
    service = _service()
    result = _match_result(error_type="CUTOFF_CROSS_DAY", exception_branch="BC-R003")
    query = service._build_rag_query(result, "BANK_CLEARING")
    for term in _profile_terms():
        assert term not in query


def test_runtime_and_eval_produce_same_appended_terms() -> None:
    service = _service()
    runtime_result = _match_result(error_type="CLEARING_SINGLE_SIDE", exception_branch="BC-R001")
    runtime_query = service._build_rag_query(runtime_result, "BANK_CLEARING")

    eval_query = query_enrichment.enrich("base", "BANK_CLEARING", "SINGLE_SIDE_MISSING")

    suffix = _profile_terms_suffix()
    assert runtime_query.endswith(" " + suffix)
    assert eval_query.endswith(" " + suffix)


def test_rule_retriever_search_returns_bank_clearing_chunks() -> None:
    from bank_reconciliation_agent.rag.retriever import rule_retriever

    response = rule_retriever.search(
        RagSearchRequest(
            query="T+1 补记 跨日切 单边核查",
            top_k=2,
            scenario_type="BANK_CLEARING",
        )
    )

    assert response.items
    assert any("bank_clearing" in item.source_file for item in response.items)


def test_workflow_falls_back_to_human_when_bank_clearing_rag_has_no_hits() -> None:
    state = _state()

    result = run_item(
        state,
        extraction_agent=NoopExtractionAgent(),
        trace_agent=NoopTraceAgent(),
        audit_agent=StaticAuditAgent(),
        tool_executor=RetrieverBackedToolExecutor(retriever=EmptyRetriever()),
    )

    assert result["scenario_type"] == "BANK_CLEARING"
    assert result["rag_context"] == []
    assert result["fallback_path"] == "HUMAN"
    assert result["next_action"] == "PENDING_HUMAN"
    assert result["fallback_level"] == 0


def test_workflow_keeps_bank_clearing_state_intact() -> None:
    state = _state()

    result = run_item(
        state,
        extraction_agent=NoopExtractionAgent(),
        trace_agent=NoopTraceAgent(),
        audit_agent=StaticAuditAgent(),
        tool_executor=RetrieverBackedToolExecutor(retriever=EmptyRetriever()),
    )

    assert result["scenario_type"] == "BANK_CLEARING"
    assert result["source_a_item"]["flow_id"] == "FLOW-2A37-001"


def _state() -> ReconciliationState:
    return {
        "task_id": "TASK-2A37-001",
        "user_id": "demo_user",
        "thread_id": "THREAD-2A37-001",
        "scenario_type": "BANK_CLEARING",
        "current_queue_id": None,
        "source_a_item": {"flow_id": "FLOW-2A37-001", "summary": "核心侧未记账"},
        "source_b_item": {"flow_id": "FLOW-2A37-001", "summary": "清算侧跨日切待核查"},
        "error_type": "SINGLE_SIDE_MISSING",
        "exception_branch": "BC-R003",
        "math_result": {
            "bank_amount": "100.00",
            "clear_amount": None,
            "amount_diff": None,
        },
        "extraction_result": {},
        "rag_context": [],
        "audit_decision": {},
        "confidence": None,
        "retry_count": 0,
        "fallback_level": 0,
        "next_action": "",
        "error_message": None,
        "agent_logs": [],
        "rag_query": "BC-R003 T+1 补记 跨日切 清算单边",
        "t1_candidate": None,
    }


class EmptyRetriever:
    def search(self, request: RagSearchRequest) -> RagSearchResponse:
        del request
        return RagSearchResponse(items=[], rewritten_query=None)


class NoopExtractionAgent:
    pass


class NoopTraceAgent:
    def trace(self, **kwargs):
        del kwargs
        return {"summary": "待补齐", "confidence": 0.2}


class StaticAuditAgent:
    def decide_with_llm(self, **kwargs) -> AuditDecision:
        del kwargs
        return AuditDecision(
            flow_id="FLOW-2A37-001",
            decision="PENDING_HUMAN",
            risk_level="HIGH",
            reason="无规则依据，需人工复核。",
            ai_suggestion="PENDING_HUMAN",
            confidence=0.2,
            evidence=[],
            next_action="PENDING_HUMAN",
            fallback_level=1,
        )

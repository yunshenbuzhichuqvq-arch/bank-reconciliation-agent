from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.schemas.rag import RagSearchRequest, RagSearchResponse
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item


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
        retriever=EmptyRetriever(),
    )

    assert result["scenario_type"] == "BANK_CLEARING"
    assert result["rag_context"] == []
    assert result["fallback_path"] == "HUMAN"
    assert result["next_action"] == "PENDING_HUMAN"
    assert result["fallback_level"] == 0


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

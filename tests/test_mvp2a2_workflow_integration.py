from __future__ import annotations

from fastapi.testclient import TestClient

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchRequest, RagSearchResponse
from bank_reconciliation_agent.services.rag_log import rag_log_service
from bank_reconciliation_agent.services.reconciliation import (
    ReconciliationMatchResult,
    ReconciliationService,
)
from bank_reconciliation_agent.services.task import task_service
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item


client = TestClient(app)


def test_run_item_passes_scenario_and_feature_flags_to_retriever(monkeypatch) -> None:
    monkeypatch.setattr("bank_reconciliation_agent.services.workflow.settings.enable_rag_rewrite", True)
    monkeypatch.setattr("bank_reconciliation_agent.services.workflow.settings.enable_rag_hybrid", True)
    monkeypatch.setattr("bank_reconciliation_agent.services.workflow.settings.enable_rag_reranker", True)
    monkeypatch.setattr("bank_reconciliation_agent.services.workflow.settings.rag_rerank_top_k", 5)

    retriever = CaptureRetriever()
    result = run_item(
        _state(),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=NoopTraceAgent(),
        audit_agent=StaticAuditAgent(),
        retriever=retriever,
    )

    assert retriever.requests == [
        RagSearchRequest(
            query=_state()["rag_query"],
            top_k=5,
            min_score=0.0,
            scenario_type="BANK_CLEARING",
            enable_rewrite=True,
            enable_hybrid=True,
            enable_reranker=True,
        )
    ]
    assert result["rag_response"]["rewritten_query"] == "金额差异 对账 规则"
    assert result["rag_context"][0]["reranker_score"] == 0.87


def test_write_ledger_entries_persists_hybrid_fields_from_rag_response(monkeypatch) -> None:
    service = ReconciliationService()
    task_id = "TASK-2A28-LOG"
    task_service.replace_task(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )

    rag_item = _evidence()
    rag_response = RagSearchResponse(items=[rag_item], rewritten_query="金额差异 对账 规则")

    def fake_run_workflow_for_result(*, user_id, task_id, scenario_type, result, rag_query):
        del user_id, task_id, scenario_type, result, rag_query
        return _workflow_state(rag_item, rag_response)

    monkeypatch.setattr(service, "_run_workflow_for_result", fake_run_workflow_for_result)

    service._write_ledger_entries(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        results=[
            ReconciliationMatchResult(
                flow_id="FLOW-2A28-001",
                status="PENDING_HUMAN",
                error_type="AMOUNT_MISMATCH",
                exception_branch="BE-R002",
                bank_amount=None,
                clear_amount=None,
                amount_diff=None,
            )
        ],
    )

    row = rag_log_service.get_latest_row(
        user_id="demo_user",
        task_id=task_id,
        query_marker="金额不一致 对账差异 处理规则",
    )

    assert row is not None
    assert row["rewritten_query"] == "金额差异 对账 规则"
    assert row["selected_chunk_id"] == "rule-2a28"
    assert float(row["dense_score"]) == 0.61
    assert float(row["bm25_score"]) == 7.5
    assert float(row["reranker_score"]) == 0.87
    assert row["fusion_rank"] == 1


def test_rag_search_api_accepts_new_request_fields_and_returns_hybrid_fields() -> None:
    response = client.post(
        "/api/v1/rag/search",
        headers={"X-User-ID": "demo_user"},
        json={
            "query": "金额差异 对账不平",
            "top_k": 3,
            "scenario_type": "BANK_ENTERPRISE",
            "enable_hybrid": True,
            "enable_reranker": True,
        },
    )

    assert response.status_code == 200
    first_item = response.json()["data"]["items"][0]
    assert "dense_score" in first_item
    assert "bm25_score" in first_item
    assert "reranker_score" in first_item
    assert "fusion_rank" in first_item


def _state() -> ReconciliationState:
    return {
        "task_id": "TASK-2A28-001",
        "user_id": "demo_user",
        "thread_id": "THREAD-2A28-001",
        "scenario_type": "BANK_CLEARING",
        "current_queue_id": None,
        "source_a_item": {"flow_id": "FLOW-2A28-001", "summary": "普通摘要"},
        "source_b_item": {"flow_id": "FLOW-2A28-001", "summary": "普通摘要"},
        "error_type": "AMOUNT_MISMATCH",
        "exception_branch": "BE-R002",
        "math_result": {
            "bank_amount": "100.00",
            "clear_amount": "99.00",
            "amount_diff": "1.00",
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
        "rag_query": "AMOUNT_MISMATCH 金额不一致 对账差异 处理规则 bank_amount=100.00 clear_amount=99.00 amount_diff=1.00",
    }


def _workflow_state(item: RagSearchItem, response: RagSearchResponse) -> ReconciliationState:
    decision = StaticAuditAgent().decide_with_llm(
        flow_id="FLOW-2A28-001",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount=None,
        clear_amount=None,
        amount_diff=None,
        evidence=[item],
    )
    return {
        **_state(),
        "scenario_type": "BANK_ENTERPRISE",
        "rag_context": [item.model_dump(mode="json")],
        "rag_response": response.model_dump(mode="json"),
        "audit_decision": decision.model_dump(mode="json"),
        "confidence": decision.confidence,
        "fallback_level": 0,
        "next_action": decision.next_action,
        "fallback_path": "L1",
    }


def _evidence() -> RagSearchItem:
    return RagSearchItem(
        chunk_id="rule-2a28",
        source="rules.md#rule-2a28",
        source_name="规则",
        source_url="https://example.com/rule-2a28",
        source_file="rules.md",
        section_title="rule-2a28",
        element_type="paragraph",
        business_tags=["bank_enterprise"],
        score=0.87,
        content="规则证据",
        dense_score=0.61,
        bm25_score=7.5,
        reranker_score=0.87,
        fusion_rank=1,
    )


class CaptureRetriever:
    def __init__(self) -> None:
        self.requests: list[RagSearchRequest] = []

    def search(self, request: RagSearchRequest) -> RagSearchResponse:
        self.requests.append(request)
        item = _evidence()
        return RagSearchResponse(items=[item], rewritten_query="金额差异 对账 规则")


class StaticAuditAgent:
    def decide_with_llm(
        self,
        flow_id: str,
        error_type: str,
        exception_branch: str | None,
        bank_amount: str | None,
        clear_amount: str | None,
        amount_diff: str | None,
        evidence: list[RagSearchItem],
    ) -> AuditDecision:
        del error_type, exception_branch, bank_amount, clear_amount, amount_diff
        return AuditDecision(
            flow_id=flow_id,
            decision="PENDING_HUMAN",
            risk_level="MEDIUM",
            reason="static audit",
            ai_suggestion="PENDING_HUMAN",
            evidence=evidence,
            confidence=0.88,
            fallback_applied=False,
            fallback_level=0,
            next_action="PENDING_HUMAN",
        )


class NoopExtractionAgent:
    pass


class NoopTraceAgent:
    pass

from fastapi.testclient import TestClient

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.rag.fusion import FusedHit
from bank_reconciliation_agent.rag.retriever import _passes_threshold
from bank_reconciliation_agent.schemas.rag import RagSearchRequest, RagSearchResponse
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item
from tests.auth_helpers import demo_bearer_headers


def _state() -> ReconciliationState:
    return {
        "task_id": "TASK-RH5",
        "user_id": "demo_user",
        "thread_id": "TASK-RH5",
        "scenario_type": "BANK_ENTERPRISE",
        "current_queue_id": None,
        "source_a_item": {"flow_id": "FLOW-RH5", "summary": "金额差异"},
        "source_b_item": {"flow_id": "FLOW-RH5", "summary": "金额差异"},
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
        "rag_query": "今天天气如何",
    }


class FloorAwareRetriever:
    def __init__(self) -> None:
        self.requests: list[RagSearchRequest] = []

    def search(self, request: RagSearchRequest) -> RagSearchResponse:
        self.requests.append(request)
        return RagSearchResponse(items=[])


class RecordingAuditAgent:
    def __init__(self) -> None:
        self.calls = 0

    def decide_with_llm(self, flow_id: str, **kwargs) -> AuditDecision:
        self.calls += 1
        evidence = kwargs["evidence"]
        return AuditDecision(
            flow_id=flow_id,
            decision="PENDING_HUMAN",
            risk_level="HIGH",
            reason="无规则依据，转人工。",
            ai_suggestion="PENDING_HUMAN",
            evidence=evidence,
            confidence=0.0,
            next_action="PENDING_HUMAN",
        )


class NoopAgent:
    def extract(self, **kwargs):
        raise AssertionError("extraction must not run")

    def trace(self, **kwargs):
        raise AssertionError("trace must not run")


def test_workflow_uses_dense_floor_and_rag_miss_defers_without_fallback() -> None:
    retriever = FloorAwareRetriever()
    audit_agent = RecordingAuditAgent()

    result = run_item(
        _state(),
        extraction_agent=NoopAgent(),
        trace_agent=NoopAgent(),
        audit_agent=audit_agent,
        retriever=retriever,
    )

    assert retriever.requests[0].min_score == 0.34
    assert audit_agent.calls == 1
    assert result["rag_context"] == []
    assert result["next_action"] == "PENDING_HUMAN"
    assert result["fallback_level"] == 0
    assert result["fallback_path"] == "HUMAN"


def test_dense_score_equal_to_floor_is_kept() -> None:
    hit = FusedHit(
        chunk_id="floor-hit",
        dense_score=0.34,
        bm25_score=None,
        fusion_score=0.34,
        fusion_rank=1,
        metadata={"chunk_id": "floor-hit"},
        content="边界证据",
    )

    assert _passes_threshold(hit, threshold=0.34, reranker_enabled=False) is True


def test_debug_rag_api_keeps_zero_default_threshold(monkeypatch) -> None:
    captured: list[RagSearchRequest] = []

    def capture(request: RagSearchRequest) -> RagSearchResponse:
        captured.append(request)
        return RagSearchResponse(items=[])

    monkeypatch.setattr(
        "bank_reconciliation_agent.api.v1.rag.rule_retriever.search",
        capture,
    )

    response = TestClient(app).post(
        "/api/v1/rag/search",
        headers=demo_bearer_headers(),
        json={"query": "调试检索", "top_k": 3},
    )

    assert response.status_code == 200
    assert captured[0].min_score == 0.0

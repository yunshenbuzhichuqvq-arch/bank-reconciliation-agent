from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.schemas.rag import RagSearchRequest, RagSearchResponse
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item
from scripts import eval_rag


def _state() -> ReconciliationState:
    return {
        "task_id": "TASK-RE3",
        "user_id": "demo_user",
        "thread_id": "TASK-RE3",
        "scenario_type": "BANK_ENTERPRISE",
        "current_queue_id": None,
        "source_a_item": {"flow_id": "FLOW-RE3", "summary": "金额差异"},
        "source_b_item": {"flow_id": "FLOW-RE3", "summary": "金额差异"},
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


class RecordingRetriever:
    def __init__(self) -> None:
        self.requests: list[RagSearchRequest] = []

    def search(self, request: RagSearchRequest) -> RagSearchResponse:
        self.requests.append(request)
        return RagSearchResponse(items=[])


class RecordingAuditAgent:
    def decide_with_llm(self, flow_id: str, **kwargs) -> AuditDecision:
        return AuditDecision(
            flow_id=flow_id,
            decision="PENDING_HUMAN",
            risk_level="HIGH",
            reason="无规则依据，转人工。",
            ai_suggestion="PENDING_HUMAN",
            evidence=kwargs["evidence"],
            confidence=0.0,
            fallback_level=0,
            next_action="PENDING_HUMAN",
        )


class NoopAgent:
    def extract(self, **kwargs):
        raise AssertionError("extraction must not run")

    def trace(self, **kwargs):
        raise AssertionError("trace must not run")


class EvalRetriever:
    def __init__(self) -> None:
        self.requests: list[RagSearchRequest] = []

    def search(self, request: RagSearchRequest) -> RagSearchResponse:
        self.requests.append(request)
        return RagSearchResponse(items=[])


def test_workflow_uses_dense_floor_for_configured_embedding_backend(monkeypatch) -> None:
    retriever = RecordingRetriever()
    retriever.store = type("Store", (), {"embedding_backend": "bge_m3"})()
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.settings.embedding_backend",
        "bge_m3",
    )

    result = run_item(
        _state(),
        extraction_agent=NoopAgent(),
        trace_agent=NoopAgent(),
        audit_agent=RecordingAuditAgent(),
        retriever=retriever,
    )

    assert retriever.requests[0].min_score == 0.5
    assert result["next_action"] == "PENDING_HUMAN"
    assert result["fallback_level"] == 0


def test_workflow_uses_dense_floor_for_effective_store_backend() -> None:
    retriever = RecordingRetriever()
    retriever.store = type("Store", (), {"embedding_backend": "hash"})()

    run_item(
        _state(),
        extraction_agent=NoopAgent(),
        trace_agent=NoopAgent(),
        audit_agent=RecordingAuditAgent(),
        retriever=retriever,
    )

    assert retriever.requests[0].min_score == 0.341


def test_eval_rag_uses_dense_floor_for_embedding_backend() -> None:
    retriever = EvalRetriever()

    eval_rag.evaluate_eval_set(
        [
            eval_rag.EvalCase(
                id="case-1",
                scenario_type="BANK_ENTERPRISE",
                error_type="AMOUNT_MISMATCH",
                query="q1",
                expected_chunk_ids=["chunk-1"],
            )
        ],
        retriever=retriever,
        embedding_backend="bge_small",
    )

    assert retriever.requests[0].min_score == 0.5

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item
from bank_reconciliation_agent.services.reconciliation import (
    ReconciliationMatchResult,
    ReconciliationService,
)
from decimal import Decimal


def _evidence() -> RagSearchItem:
    return RagSearchItem(
        chunk_id="rule-fuzzy",
        source="rules/bank_enterprise.yaml#BE-R007",
        source_name="银企规则",
        source_url="https://example.com/BE-R007",
        source_file="rules/bank_enterprise.yaml",
        section_title="候选确认",
        element_type="rule",
        business_tags=["fuzzy_match"],
        score=0.9,
        content="候选需依据金额、日期和对手方确认。",
    )


def _state(*, bank_amount: str | None = "100.00", candidate_amount: str = "100.00") -> ReconciliationState:
    return {
        "task_id": "TASK-RH4",
        "user_id": "demo_user",
        "thread_id": "TASK-RH4",
        "scenario_type": "BANK_ENTERPRISE",
        "current_queue_id": None,
        "source_a_item": {"flow_id": "BANK-001", "summary": "收款"},
        "source_b_item": {"flow_id": "BANK-001"},
        "error_type": "FUZZY_MATCH_CANDIDATE",
        "exception_branch": "BE-R007",
        "math_result": {
            "bank_amount": bank_amount,
            "clear_amount": None if bank_amount is not None else "100.00",
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
        "fuzzy_candidate": {
            "flow_id": "CLEAR-009",
            "amount": candidate_amount,
            "trade_date": "2026-06-22",
            "counterparty": "示例公司",
        },
    }


class StaticRetriever:
    def __init__(self, *, with_evidence: bool = True) -> None:
        self.with_evidence = with_evidence

    def search(self, request) -> RagSearchResponse:
        del request
        return RagSearchResponse(items=[_evidence()] if self.with_evidence else [])


class NoopAgent:
    def extract(self, **kwargs):
        raise AssertionError("extraction must not run")

    def trace(self, **kwargs):
        raise AssertionError("trace must not run")


class CandidateAuditAgent:
    prompt_version = "v2"

    def __init__(self, decisions: list[tuple[str, float]]) -> None:
        self.decisions = decisions
        self.calls: list[dict[str, object]] = []

    def decide_with_llm(self, flow_id: str, **kwargs) -> AuditDecision:
        self.calls.append(kwargs)
        decision, confidence = self.decisions[len(self.calls) - 1]
        return AuditDecision(
            flow_id=flow_id,
            decision=decision,
            risk_level="LOW" if decision == "AUTO_FIXED" else "MEDIUM",
            reason="候选确认结果",
            ai_suggestion=decision,
            evidence=kwargs["evidence"],
            confidence=confidence if kwargs["evidence"] else 0.0,
            next_action=decision,
        )


def _run(state: ReconciliationState, agent: CandidateAuditAgent, *, with_evidence: bool = True):
    return run_item(
        state,
        extraction_agent=NoopAgent(),
        trace_agent=NoopAgent(),
        audit_agent=agent,
        retriever=StaticRetriever(with_evidence=with_evidence),
    )


def test_confirmed_equal_candidate_auto_fixes_and_passes_context() -> None:
    agent = CandidateAuditAgent([("AUTO_FIXED", 0.92)])

    result = _run(_state(), agent)

    assert len(agent.calls) == 1
    assert agent.calls[0]["match_candidate_context"]["flow_id"] == "CLEAR-009"
    assert result["next_action"] == "AUTO_FIXED"
    assert result["audit_decision"]["decision"] == "AUTO_FIXED"
    assert any(row["step"] == "confirm_match" for row in result["agent_logs"])


def test_confirmed_unequal_candidate_becomes_amount_mismatch_without_fallback_loop() -> None:
    agent = CandidateAuditAgent([("AUTO_FIXED", 0.92), ("PENDING_HUMAN", 0.90)])

    result = _run(_state(candidate_amount="101.00"), agent)

    assert len(agent.calls) == 2
    assert agent.calls[1]["error_type"] == "AMOUNT_MISMATCH"
    assert agent.calls[1].get("match_candidate_context") is None
    assert result["error_type"] == "AMOUNT_MISMATCH"
    assert result["exception_branch"] == "BE-R002"
    assert result["fallback_path"] == "L1"


def test_rejected_candidate_restores_true_single_side() -> None:
    result = _run(_state(), CandidateAuditAgent([("UNRESOLVED", 0.91)]))

    assert result["error_type"] == "BOOK_UNRECORDED"
    assert result["exception_branch"] == "BE-R006"
    assert result["next_action"] == "PENDING_HUMAN"


def test_low_confidence_or_missing_evidence_defers_without_fallback() -> None:
    low_agent = CandidateAuditAgent([("AUTO_FIXED", 0.70)])
    low_result = _run(_state(), low_agent)
    no_evidence_agent = CandidateAuditAgent([("PENDING_HUMAN", 0.0)])
    no_evidence_result = _run(_state(), no_evidence_agent, with_evidence=False)

    assert len(low_agent.calls) == 1
    assert low_result["next_action"] == "PENDING_HUMAN"
    assert low_result["fallback_path"] == "HUMAN"
    assert len(no_evidence_agent.calls) == 1
    assert no_evidence_result["next_action"] == "PENDING_HUMAN"
    assert no_evidence_result["fallback_level"] == 0


def test_reconciliation_state_passes_fuzzy_candidate_to_workflow(monkeypatch) -> None:
    service = ReconciliationService()
    candidate = {
        "flow_id": "CLEAR-009",
        "amount": "100.00",
        "trade_date": "2026-06-22",
        "counterparty": "示例公司",
    }
    result = ReconciliationMatchResult(
        flow_id="BANK-001",
        status="PENDING_AI",
        error_type="FUZZY_MATCH_CANDIDATE",
        exception_branch="BE-R007",
        bank_amount=Decimal("100.00"),
        clear_amount=None,
        amount_diff=None,
        fuzzy_candidate=candidate,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.transaction_service.get_bank_row",
        lambda **kwargs: {"flow_id": "BANK-001"},
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.transaction_service.get_clear_row",
        lambda **kwargs: None,
    )

    def capture_state(state):
        captured.update(state)
        return state

    monkeypatch.setattr("bank_reconciliation_agent.services.reconciliation.run_item", capture_state)

    service._run_workflow_for_result(
        user_id="demo_user",
        task_id="TASK-RH4",
        scenario_type="BANK_ENTERPRISE",
        result=result,
        rag_query="candidate query",
    )

    assert captured["fuzzy_candidate"] == candidate

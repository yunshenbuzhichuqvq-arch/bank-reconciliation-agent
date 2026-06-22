import json

from bank_reconciliation_agent.agents.audit_agent import AuditAgent
from bank_reconciliation_agent.core.llm.provider import LLMResult
from bank_reconciliation_agent.schemas.rag import RagSearchItem


def _evidence() -> list[RagSearchItem]:
    return [
        RagSearchItem(
            chunk_id="rule-fuzzy-match",
            source="rules/bank_enterprise.yaml#BE-R007",
            source_name="银企对账规则",
            source_url="https://example.com/rules/BE-R007",
            source_file="rules/bank_enterprise.yaml",
            section_title="疑似同一笔",
            element_type="rule",
            business_tags=["fuzzy_match"],
            score=0.9,
            content="金额、日期及对手方一致时，可作为疑似同一笔候选并核验。",
        )
    ]


class RecordingProvider:
    def __init__(self, decision: str = "AUTO_FIXED") -> None:
        self.decision = decision
        self.messages: list[dict[str, str]] | None = None

    def complete(self, messages, **kwargs) -> LLMResult:
        self.messages = messages
        return LLMResult(
            text=json.dumps(
                {
                    "decision": self.decision,
                    "risk_level": "LOW",
                    "reason": "规则证据支持候选判断。",
                    "ai_suggestion": self.decision,
                    "evidence": ["rule-fuzzy-match"],
                    "confidence": 0.92,
                }
            ),
            model="fake",
            prompt_tokens=10,
            completion_tokens=8,
        )

    def user_payload(self) -> dict[str, object]:
        assert self.messages is not None
        return json.loads(self.messages[-1]["content"])


class FailingProvider:
    def complete(self, messages, **kwargs) -> LLMResult:
        raise AssertionError("provider must not be called without evidence")


def _decide(provider, *, evidence=None, error_type="FUZZY_MATCH_CANDIDATE"):
    return AuditAgent(provider=provider).decide_with_llm(
        flow_id="BANK-001",
        error_type=error_type,
        exception_branch="BE-R007",
        bank_amount="100.00",
        clear_amount=None,
        amount_diff=None,
        evidence=_evidence() if evidence is None else evidence,
        match_candidate_context={
            "flow_id": "CLEAR-009",
            "amount": "100.00",
            "trade_date": "2026-06-22",
            "counterparty": "示例公司",
        },
    )


def test_candidate_context_selects_confirm_match_task_and_includes_both_sides() -> None:
    provider = RecordingProvider()

    decision = _decide(provider)

    payload = provider.user_payload()
    assert payload["task"] == "confirm_match"
    assert payload["current_transaction"]["flow_id"] == "BANK-001"
    assert payload["current_transaction"]["bank_amount"] == "100.00"
    assert payload["match_candidate"]["flow_id"] == "CLEAR-009"
    assert decision.decision == "AUTO_FIXED"
    assert decision.confidence == 0.92
    assert decision.evidence == _evidence()


def test_candidate_rejection_preserves_existing_decision_schema() -> None:
    decision = _decide(RecordingProvider(decision="UNRESOLVED"))

    assert decision.decision == "UNRESOLVED"
    assert decision.next_action == "UNRESOLVED"
    assert decision.evidence == _evidence()


def test_candidate_without_evidence_short_circuits_to_pending_human() -> None:
    decision = _decide(FailingProvider(), evidence=[])

    assert decision.decision == "PENDING_HUMAN"
    assert decision.confidence == 0.0
    assert decision.evidence == []


def test_non_candidate_keeps_audit_task() -> None:
    provider = RecordingProvider(decision="PENDING_HUMAN")

    _decide(provider, error_type="AMOUNT_MISMATCH")

    payload = provider.user_payload()
    assert payload["task"] == "audit"
    assert "current_transaction" not in payload
    assert "match_candidate" not in payload

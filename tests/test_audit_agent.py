import pytest
from pydantic import ValidationError

from bank_reconciliation_agent.agents.audit_agent import AuditAgent, AuditDecision
from bank_reconciliation_agent.core.llm.provider import FakeLLMProvider, LLMResult, LLMUnavailable
from bank_reconciliation_agent.schemas.rag import RagSearchItem
from bank_reconciliation_agent.services.reconciliation import ReconciliationService


def _evidence() -> list[RagSearchItem]:
    return [
        RagSearchItem(
            chunk_id="unionpay_reconciliation_faq_001",
            source="data/rag/raw_sources/bank_enterprise/unionpay_reconciliation_faq.md#清算文件流水与资金核对不平",
            source_name="银联一窗办清算对账公开 FAQ 摘录",
            source_url="https://pcs.unionpay.com/example",
            source_file="data/rag/raw_sources/bank_enterprise/unionpay_reconciliation_faq.md",
            section_title="清算文件流水与资金核对不平",
            element_type="paragraph",
            business_tags=["amount_mismatch"],
            score=12.0,
            content="金额差异应保留银行端金额、清算端金额和差异金额。",
        )
    ]


@pytest.mark.parametrize(
    ("exception_branch", "risk_level", "ai_suggestion", "reason_keyword"),
    [
        ("BE-R002", "MEDIUM", "PENDING_HUMAN", "金额不一致"),
        ("BE-R004", "LOW", "APPROVED_MATCH", "摘要/客户名不一致"),
        ("BE-R005", "MEDIUM", "PENDING_HUMAN", "企业已记账、银行未到账"),
        ("BE-R006", "MEDIUM", "PENDING_HUMAN", "银行已到账、企业未入账"),
        ("BE-R008", "HIGH", "FORCE_HOLD", "重复记账"),
    ],
)
def test_audit_agent_returns_branch_profile_decision_with_evidence(
    exception_branch: str,
    risk_level: str,
    ai_suggestion: str,
    reason_keyword: str,
) -> None:
    evidence = _evidence()

    decision = AuditAgent().decide(
        flow_id="F1004",
        error_type="AMOUNT_MISMATCH",
        exception_branch=exception_branch,
        bank_amount="300.00",
        clear_amount="295.00",
        amount_diff="5.00",
        evidence=evidence,
    )

    assert decision.flow_id == "F1004"
    assert decision.decision == "PENDING_HUMAN"
    assert decision.risk_level == risk_level
    assert decision.ai_suggestion == ai_suggestion
    assert decision.confidence == 0.72
    assert reason_keyword in decision.reason
    assert decision.evidence[0].chunk_id == "unionpay_reconciliation_faq_001"


def test_audit_agent_defers_when_rag_evidence_is_missing() -> None:
    decision = AuditAgent().decide(
        flow_id="F1005",
        error_type="SINGLE_SIDE_MISSING",
        exception_branch="BE-R005",
        bank_amount="120.00",
        clear_amount=None,
        amount_diff=None,
        evidence=[],
    )

    assert decision.flow_id == "F1005"
    assert decision.decision == "PENDING_HUMAN"
    assert decision.risk_level == "HIGH"
    assert decision.ai_suggestion == "PENDING_HUMAN"
    assert decision.confidence == 0.0
    assert "未检索到" in decision.reason
    assert decision.evidence == []


def test_audit_agent_uses_generic_fallback_for_unknown_branch() -> None:
    decision = AuditAgent().decide(
        flow_id="F1006",
        error_type="UNCLASSIFIED",
        exception_branch="UNCLASSIFIED",
        bank_amount="120.00",
        clear_amount="120.00",
        amount_diff="0.00",
        evidence=_evidence(),
    )

    assert decision.decision == "PENDING_HUMAN"
    assert decision.risk_level == "MEDIUM"
    assert decision.ai_suggestion == "PENDING_HUMAN"
    assert decision.confidence == 0.72
    assert "UNCLASSIFIED" in decision.reason


def test_audit_agent_llm_path_returns_extended_decision_with_fake_provider() -> None:
    decision = AuditAgent(provider=FakeLLMProvider()).decide_with_llm(
        flow_id="F1007",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount="300.00",
        clear_amount="295.00",
        amount_diff="5.00",
        evidence=_evidence(),
    )

    assert decision.flow_id == "F1007"
    assert decision.decision == "PENDING_HUMAN"
    assert decision.risk_level == "MEDIUM"
    assert decision.fallback_applied is False
    assert decision.fallback_level == 0
    assert decision.next_action == "PENDING_HUMAN"
    assert decision.confidence == 0.88
    assert decision.evidence == _evidence()


def test_audit_agent_llm_unavailable_falls_back_to_deterministic_pending_human() -> None:
    decision = AuditAgent(provider=UnavailableProvider()).decide_with_llm(
        flow_id="F1008",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount="300.00",
        clear_amount="295.00",
        amount_diff="5.00",
        evidence=_evidence(),
    )

    assert decision.flow_id == "F1008"
    assert decision.decision == "PENDING_HUMAN"
    assert decision.risk_level == "MEDIUM"
    assert decision.fallback_applied is True
    assert decision.fallback_level == 1
    assert decision.next_action == "PENDING_HUMAN"
    assert "金额不一致" in decision.reason
    assert decision.evidence == _evidence()


def test_audit_agent_invalid_llm_output_falls_back_without_raising() -> None:
    providers = [
        InvalidJsonProvider(),
        InvalidSchemaProvider(
            '{"decision":"PENDING_HUMAN","risk_level":"MEDIUM","reason":"缺字段",'
            '"ai_suggestion":"PENDING_HUMAN","evidence":["rule"]}'
        ),
        InvalidSchemaProvider(
            '{"decision":"PENDING_HUMAN","risk_level":"MEDIUM","reason":"置信度越界",'
            '"ai_suggestion":"PENDING_HUMAN","evidence":["rule"],"confidence":1.5}'
        ),
    ]

    for provider in providers:
        decision = AuditAgent(provider=provider).decide_with_llm(
            flow_id="F1008-BAD",
            error_type="AMOUNT_MISMATCH",
            exception_branch="BE-R002",
            bank_amount="300.00",
            clear_amount="295.00",
            amount_diff="5.00",
            evidence=_evidence(),
        )

        assert decision.flow_id == "F1008-BAD"
        assert decision.decision == "PENDING_HUMAN"
        assert decision.fallback_applied is True
        assert decision.fallback_level == 1
        assert decision.next_action == "PENDING_HUMAN"
        assert "金额不一致" in decision.reason


def test_audit_agent_invalid_decision_literal_from_llm_falls_back_without_raising() -> None:
    decision = AuditAgent(provider=InvalidDecisionLiteralProvider()).decide_with_llm(
        flow_id="F1010-BAD-LITERAL",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount="300.00",
        clear_amount="295.00",
        amount_diff="5.00",
        evidence=_evidence(),
    )

    assert decision.flow_id == "F1010-BAD-LITERAL"
    assert decision.decision == "PENDING_HUMAN"
    assert decision.fallback_applied is True
    assert decision.fallback_level == 1
    assert decision.next_action == "PENDING_HUMAN"
    assert decision.evidence == _evidence()
    assert "金额不一致" in decision.reason
    assert "AI 处理异常" not in decision.reason


def test_audit_agent_llm_path_defers_when_rag_evidence_is_missing() -> None:
    decision = AuditAgent(provider=FakeLLMProvider()).decide_with_llm(
        flow_id="F1009",
        error_type="SINGLE_SIDE_MISSING",
        exception_branch="BE-R005",
        bank_amount="120.00",
        clear_amount=None,
        amount_diff=None,
        evidence=[],
    )

    assert decision.flow_id == "F1009"
    assert decision.decision == "PENDING_HUMAN"
    assert decision.risk_level == "HIGH"
    assert decision.fallback_applied is False
    assert decision.fallback_level == 0
    assert decision.next_action == "PENDING_HUMAN"
    assert decision.confidence == 0.0
    assert decision.evidence == []


def test_audit_agent_injects_few_shot_and_trace_context_into_llm_messages() -> None:
    provider = RecordingProvider()
    few_shot_cases = [
        {
            "flow_id": "FLOW-OLD-001",
            "exception_branch": "BE-R002",
            "ai_audit_opinion": "人工确认金额差异需复核",
            "handle_status": "HELD",
        }
    ]
    trace_context = {
        "trace_found": True,
        "related_flow_ids": ["FLOW-T1-001"],
        "trace_summary": "发现 T+1 到账线索",
        "confidence": 0.91,
    }

    AuditAgent(provider=provider).decide_with_llm(
        flow_id="F1011",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount="300.00",
        clear_amount="295.00",
        amount_diff="5.00",
        evidence=_evidence(),
        few_shot_cases=few_shot_cases,
        trace_context=trace_context,
    )

    assert provider.messages is not None
    user_payload = provider.user_payload()
    assert user_payload["few_shot_cases"] == few_shot_cases
    assert user_payload["trace_context"] == trace_context


def test_audit_agent_injects_memory_context_as_additional_system_message() -> None:
    provider = RecordingProvider()

    AuditAgent(provider=provider).decide_with_llm(
        flow_id="F1012",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount="300.00",
        clear_amount="295.00",
        amount_diff="5.00",
        evidence=_evidence(),
        memory_context="Long-term memory: similar amount mismatch",
    )

    assert provider.messages is not None
    assert provider.messages[0]["role"] == "system"
    assert provider.messages[1] == {
        "role": "system",
        "content": "Long-term memory: similar amount mismatch",
    }
    assert provider.messages[2]["role"] == "user"


def test_reconciliation_audit_decision_schema_includes_fallback_fields() -> None:
    decision = AuditAgent(provider=FakeLLMProvider()).decide_with_llm(
        flow_id="F1010",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount="300.00",
        clear_amount="295.00",
        amount_diff="5.00",
        evidence=_evidence(),
    )

    response_decision = ReconciliationService()._to_reconciliation_audit_decision(decision)

    assert response_decision.fallback_applied is False
    assert response_decision.fallback_level == 0
    assert response_decision.next_action == "PENDING_HUMAN"


def test_audit_decision_rejects_invalid_decision_literal() -> None:
    with pytest.raises(ValidationError):
        AuditDecision(
            flow_id="F-INVALID",
            decision="FIXED",
            risk_level="MEDIUM",
            reason="invalid",
            ai_suggestion="PENDING_HUMAN",
            evidence=_evidence(),
            confidence=0.8,
        )


def test_audit_decision_requires_evidence_unless_pending_human() -> None:
    with pytest.raises(ValidationError):
        AuditDecision(
            flow_id="F-AUTO",
            decision="AUTO_FIXED",
            risk_level="LOW",
            reason="auto",
            ai_suggestion="APPROVED_MATCH",
            evidence=[],
            confidence=0.9,
        )

    unresolved = AuditDecision(
        flow_id="F-UNRESOLVED",
        decision="UNRESOLVED",
        risk_level="HIGH",
        reason="need follow-up",
        ai_suggestion="FORCE_HOLD",
        evidence=_evidence(),
        confidence=0.9,
    )
    pending_human = AuditDecision(
        flow_id="F-HUMAN",
        decision="PENDING_HUMAN",
        risk_level="HIGH",
        reason="no evidence",
        ai_suggestion="PENDING_HUMAN",
        evidence=[],
        confidence=0.0,
    )

    assert unresolved.decision == "UNRESOLVED"
    assert pending_human.evidence == []


class UnavailableProvider:
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
    ) -> LLMResult:
        del messages, temperature, response_format
        raise LLMUnavailable("provider unavailable")


class InvalidJsonProvider:
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
    ) -> LLMResult:
        del messages, temperature, response_format
        return LLMResult(
            text="{not-json",
            prompt_tokens=10,
            completion_tokens=8,
            model="invalid-json",
        )


class InvalidSchemaProvider:
    def __init__(self, text: str) -> None:
        self.text = text

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
    ) -> LLMResult:
        del messages, temperature, response_format
        return LLMResult(
            text=self.text,
            prompt_tokens=10,
            completion_tokens=8,
            model="invalid-schema",
        )


class InvalidDecisionLiteralProvider:
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
    ) -> LLMResult:
        del messages, temperature, response_format
        return LLMResult(
            text=(
                '{"decision":"APPROVED_MATCH","risk_level":"LOW","reason":"模型建议自动平账",'
                '"ai_suggestion":"APPROVED_MATCH","evidence":["rule"],"confidence":0.91}'
            ),
            prompt_tokens=10,
            completion_tokens=8,
            model="invalid-literal",
        )


class RecordingProvider:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] | None = None

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
    ) -> LLMResult:
        del temperature, response_format
        self.messages = messages
        return LLMResult(
            text=(
                '{"decision":"PENDING_HUMAN","risk_level":"MEDIUM","reason":"记录测试",'
                '"ai_suggestion":"PENDING_HUMAN","evidence":["rule"],"confidence":0.86}'
            ),
            prompt_tokens=10,
            completion_tokens=8,
            model="recording",
        )

    def user_payload(self) -> dict[str, object]:
        import json

        assert self.messages is not None
        return json.loads(self.messages[1]["content"])

import pytest

from bank_reconciliation_agent.agents.audit_agent import AuditAgent
from bank_reconciliation_agent.schemas.rag import RagSearchItem


def _evidence() -> list[RagSearchItem]:
    return [
        RagSearchItem(
            chunk_id="unionpay_reconciliation_faq_001",
            source="data/rag/raw_sources/unionpay_reconciliation_faq.md#清算文件流水与资金核对不平",
            source_name="银联一窗办清算对账公开 FAQ 摘录",
            source_url="https://pcs.unionpay.com/example",
            source_file="data/rag/raw_sources/unionpay_reconciliation_faq.md",
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

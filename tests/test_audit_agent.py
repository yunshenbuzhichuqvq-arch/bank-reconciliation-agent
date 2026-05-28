from bank_reconciliation_agent.agents.audit_agent import AuditAgent
from bank_reconciliation_agent.schemas.rag import RagSearchItem


def test_audit_agent_returns_structured_decision_with_evidence() -> None:
    evidence = [
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

    decision = AuditAgent().decide(
        flow_id="F1004",
        error_type="AMOUNT_MISMATCH",
        bank_amount="300.00",
        clear_amount="295.00",
        amount_diff="5.00",
        evidence=evidence,
    )

    assert decision.flow_id == "F1004"
    assert decision.decision == "PENDING_HUMAN"
    assert decision.risk_level == "MEDIUM"
    assert decision.confidence == 0.72
    assert "金额不一致" in decision.reason
    assert decision.evidence[0].chunk_id == "unionpay_reconciliation_faq_001"


def test_audit_agent_defers_when_rag_evidence_is_missing() -> None:
    decision = AuditAgent().decide(
        flow_id="F1005",
        error_type="SINGLE_SIDE_MISSING",
        bank_amount="120.00",
        clear_amount=None,
        amount_diff=None,
        evidence=[],
    )

    assert decision.flow_id == "F1005"
    assert decision.decision == "PENDING_HUMAN"
    assert decision.risk_level == "HIGH"
    assert decision.confidence == 0.0
    assert "未检索到" in decision.reason
    assert decision.evidence == []

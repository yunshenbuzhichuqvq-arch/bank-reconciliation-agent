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
        source_a_amount="300.00",
        source_b_amount="295.00",
        amount_diff="5.00",
        evidence=evidence,
    )

    assert decision.flow_id == "F1004"
    assert decision.decision == "PENDING_HUMAN"
    assert decision.risk_level == "MEDIUM"
    assert decision.confidence == 0.72
    assert "金额不一致" in decision.reason
    assert decision.evidence[0].chunk_id == "unionpay_reconciliation_faq_001"


def test_audit_agent_describes_bank_unarrived_with_enterprise_book_context() -> None:
    evidence = [
        RagSearchItem(
            chunk_id="bank_enterprise_single_side_001",
            source="rules/bank_enterprise.md#银行未到账",
            source_name="银企对账规则",
            source_url="",
            source_file="rules/bank_enterprise.md",
            section_title="银行未到账",
            element_type="paragraph",
            business_tags=["bank_unarrived"],
            score=0.8,
            content="企业账簿已记账但银行流水未到账，应追踪银行入账状态。",
        )
    ]

    decision = AuditAgent().decide(
        flow_id="F1005",
        error_type="BANK_UNARRIVED",
        source_a_amount="120.00",
        source_b_amount=None,
        amount_diff=None,
        evidence=evidence,
    )

    assert decision.risk_level == "MEDIUM"
    assert "银行未到账" in decision.reason
    assert "企业账簿金额 120.00" in decision.reason


def test_audit_agent_describes_book_unrecorded_with_bank_statement_context() -> None:
    evidence = [
        RagSearchItem(
            chunk_id="bank_enterprise_single_side_002",
            source="rules/bank_enterprise.md#企业未入账",
            source_name="银企对账规则",
            source_url="",
            source_file="rules/bank_enterprise.md",
            section_title="企业未入账",
            element_type="paragraph",
            business_tags=["book_unrecorded"],
            score=0.7,
            content="银行流水已到账但企业账簿未入账，应补记或复核。",
        )
    ]

    decision = AuditAgent().decide(
        flow_id="F1006",
        error_type="BOOK_UNRECORDED",
        source_a_amount=None,
        source_b_amount="45.00",
        amount_diff=None,
        evidence=evidence,
    )

    assert decision.risk_level == "MEDIUM"
    assert "企业未入账" in decision.reason
    assert "银行流水金额 45.00" in decision.reason


def test_audit_agent_defers_when_rag_evidence_is_missing() -> None:
    decision = AuditAgent().decide(
        flow_id="F1005",
        error_type="BANK_UNARRIVED",
        source_a_amount="120.00",
        source_b_amount=None,
        amount_diff=None,
        evidence=[],
    )

    assert decision.flow_id == "F1005"
    assert decision.decision == "PENDING_HUMAN"
    assert decision.risk_level == "HIGH"
    assert decision.confidence == 0.0
    assert "未检索到" in decision.reason
    assert decision.evidence == []

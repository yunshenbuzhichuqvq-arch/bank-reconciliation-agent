from bank_reconciliation_agent.agents.audit_agent import AuditDecision, audit_agent
from bank_reconciliation_agent.schemas.rag import RagSearchItem


VALID_DECISIONS = {"AUTO_FIXED", "PENDING_AI", "PENDING_HUMAN"}
VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}


def test_audit_agent_outputs_valid_schema_for_supported_error_types() -> None:
    evidence = [_evidence("unionpay_reconciliation_faq_001")]
    cases = [
        {
            "flow_id": "F1004",
            "error_type": "AMOUNT_MISMATCH",
            "source_a_amount": "300.00",
            "source_b_amount": "295.00",
            "amount_diff": "5.00",
            "evidence": evidence,
        },
        {
            "flow_id": "F1005",
            "error_type": "BANK_UNARRIVED",
            "source_a_amount": "120.00",
            "source_b_amount": None,
            "amount_diff": None,
            "evidence": evidence,
        },
        {
            "flow_id": "F1006",
            "error_type": "BOOK_UNRECORDED",
            "source_a_amount": None,
            "source_b_amount": "45.00",
            "amount_diff": None,
            "evidence": evidence,
        },
        {
            "flow_id": "F1007",
            "error_type": "BANK_UNARRIVED",
            "source_a_amount": "66.60",
            "source_b_amount": None,
            "amount_diff": None,
            "evidence": [],
        },
    ]

    for case in cases:
        decision = audit_agent.decide(**case)
        validated = AuditDecision.model_validate(decision.model_dump())

        assert validated.flow_id == case["flow_id"]
        assert validated.decision in VALID_DECISIONS
        assert validated.risk_level in VALID_RISK_LEVELS
        assert isinstance(validated.reason, str)
        assert validated.reason
        assert 0 <= validated.confidence <= 1
        for item in validated.evidence:
            RagSearchItem.model_validate(item.model_dump())


def _evidence(chunk_id: str) -> RagSearchItem:
    return RagSearchItem(
        chunk_id=chunk_id,
        source="unionpay_reconciliation_faq.md#金额差异处理",
        source_name="银联对账差错处理公开 FAQ",
        source_url="https://example.com/unionpay",
        source_file="unionpay_reconciliation_faq.md",
        section_title="金额差异处理",
        element_type="faq",
        business_tags=["AMOUNT_MISMATCH"],
        score=0.72,
        content="金额不一致时应人工复核差异金额和交易信息。",
    )

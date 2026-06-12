from collections import Counter

from bank_reconciliation_agent.agents.audit_agent import AuditAgent
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.llm.provider import FakeLLMProvider
from bank_reconciliation_agent.schemas.rag import RagSearchItem


ALLOWED_DECISIONS = {"AUTO_FIXED", "PENDING_HUMAN", "UNRESOLVED"}


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


def test_fake_provider_decision_regression_distribution_is_single_point() -> None:
    agent = AuditAgent(provider=FakeLLMProvider())

    decisions = [
        agent.decide_with_llm(
            flow_id="F-REGRESSION-001",
            error_type="AMOUNT_MISMATCH",
            exception_branch="BE-R002",
            bank_amount="300.00",
            clear_amount="295.00",
            amount_diff="5.00",
            evidence=_evidence(),
        )
        for _ in range(settings.decision_regression_runs)
    ]

    distribution = Counter(decision.decision for decision in decisions)

    assert len(decisions) == settings.decision_regression_runs
    assert set(distribution).issubset(ALLOWED_DECISIONS)
    assert len(distribution) == 1

    for decision in decisions:
        assert decision.decision in ALLOWED_DECISIONS
        assert decision.reason
        assert 0.0 <= decision.confidence <= 1.0
        if decision.decision != "PENDING_HUMAN":
            assert decision.evidence

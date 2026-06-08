from bank_reconciliation_agent.agents.audit_agent import AuditAgent, AuditDecision
from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgent, ExtractionResult
from bank_reconciliation_agent.agents.trace_agent import TraceAgent, TraceResult
from bank_reconciliation_agent.core.llm.provider import FakeLLMProvider
from bank_reconciliation_agent.schemas.rag import RagSearchItem


ALLOWED_DECISIONS = {"PENDING_HUMAN", "APPROVED_MATCH", "FORCE_HOLD"}
ALLOWED_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}


def test_audit_agent_quality_fields_are_valid_with_evidence() -> None:
    decision = AuditAgent(provider=FakeLLMProvider()).decide_with_llm(
        flow_id="F-QA-001",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount="300.00",
        clear_amount="295.00",
        amount_diff="5.00",
        evidence=[_evidence()],
    )

    assert isinstance(decision, AuditDecision)
    assert decision.decision in ALLOWED_DECISIONS
    assert decision.risk_level in ALLOWED_RISK_LEVELS
    assert decision.reason.strip()
    assert decision.evidence
    assert 0 <= decision.confidence <= 1


def test_extraction_agent_quality_fields_are_valid() -> None:
    result = ExtractionAgent(provider=FakeLLMProvider()).extract(
        flow_id="F-QA-002",
        summary="客户退款冲正",
        remark="原流水疑似 FLOW-ORIGINAL-001",
    )

    assert isinstance(result, ExtractionResult)
    assert result.standard_type in {"REVERSAL", "REFUND", "CANCEL", "UNKNOWN"}
    assert result.cleaned_remark.strip()
    assert 0 <= result.confidence <= 1


def test_trace_agent_quality_fields_are_valid() -> None:
    result = TraceAgent(provider=FakeLLMProvider()).trace(
        flow_id="F-QA-003",
        summary="企业已记账、银行未到账",
        transaction_date="2026-06-01",
        amount="72.00",
        remark="T+1 查询",
    )

    assert isinstance(result, TraceResult)
    assert isinstance(result.trace_found, bool)
    assert result.trace_summary.strip()
    assert 0 <= result.confidence <= 1
    if result.trace_found:
        assert result.related_flow_ids


def _evidence() -> RagSearchItem:
    return RagSearchItem(
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

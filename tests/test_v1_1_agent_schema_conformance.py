from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from bank_reconciliation_agent.agents.audit_agent import AuditAgent, AuditDecision
from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgent, ExtractionResult
from bank_reconciliation_agent.agents.trace_agent import TraceAgent, TraceResult
from bank_reconciliation_agent.core.llm.provider import FakeLLMProvider
from bank_reconciliation_agent.schemas.rag import RagSearchItem


# ADR-039 debt: 2b-3 regression assertions live inline in
# tests/test_mvp2b3_decision_regression.py, so this conformance test keeps the
# small invariant helpers local until a second caller needs a shared test module.
REPORT_PATH = Path("reports/agent_schema_conformance.md")


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


def _validate_schema(result: BaseModel, schema: type[BaseModel]) -> BaseModel:
    return schema.model_validate_json(result.model_dump_json())


def _assert_confidence(value: float) -> None:
    assert 0.0 <= value <= 1.0


def _assert_audit_invariants(decision: AuditDecision) -> None:
    assert decision.decision in {"AUTO_FIXED", "PENDING_HUMAN", "UNRESOLVED"}
    _assert_confidence(decision.confidence)
    if not decision.evidence:
        assert decision.decision == "PENDING_HUMAN"
        assert decision.ai_suggestion == "PENDING_HUMAN"
        assert decision.confidence == 0.0


def _write_report(results: list[tuple[str, bool]]) -> None:
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    lines = [
        "# Agent Schema Conformance",
        "",
        f"- Passed: {passed}/{total}",
        f"- Pass rate: {passed / total:.2%}",
        "",
        "| Agent case | Result |",
        "| --- | --- |",
    ]
    lines.extend(f"| {name} | {'PASS' if ok else 'FAIL'} |" for name, ok in results)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_three_agent_outputs_parse_and_satisfy_schema_invariants(capsys) -> None:
    cases: list[tuple[str, Callable[[], BaseModel], type[BaseModel], Callable[[BaseModel], None]]] = [
        (
            "ExtractionAgent",
            lambda: ExtractionAgent(provider=FakeLLMProvider()).extract(
                flow_id="FLOW-REVERSAL-001",
                summary="客户退款冲正，关联原流水 FLOW-ORIGINAL-001",
                remark="冲正退款",
            ),
            ExtractionResult,
            lambda result: _assert_confidence(result.confidence),
        ),
        (
            "AuditAgent.with_evidence",
            lambda: AuditAgent(provider=FakeLLMProvider()).decide_with_llm(
                flow_id="F-SCHEMA-001",
                error_type="AMOUNT_MISMATCH",
                exception_branch="BE-R002",
                bank_amount="300.00",
                clear_amount="295.00",
                amount_diff="5.00",
                evidence=_evidence(),
            ),
            AuditDecision,
            lambda result: _assert_audit_invariants(result),
        ),
        (
            "AuditAgent.no_rag_evidence",
            lambda: AuditAgent(provider=FakeLLMProvider()).decide_with_llm(
                flow_id="F-SCHEMA-002",
                error_type="SINGLE_SIDE_MISSING",
                exception_branch="BE-R005",
                bank_amount="120.00",
                clear_amount=None,
                amount_diff=None,
                evidence=[],
            ),
            AuditDecision,
            lambda result: _assert_audit_invariants(result),
        ),
        (
            "TraceAgent",
            lambda: TraceAgent(provider=FakeLLMProvider()).trace(
                flow_id="FLOW-SINGLE-001",
                summary="企业已记账，银行 T+1 次日到账待追溯",
                transaction_date="2026-06-07",
                amount="128.00",
                remark="跨日切",
            ),
            TraceResult,
            lambda result: _assert_confidence(result.confidence),
        ),
    ]

    results: list[tuple[str, bool]] = []
    for name, run_case, schema, assert_invariants in cases:
        parsed = _validate_schema(run_case(), schema)
        assert_invariants(parsed)
        results.append((name, True))

    _write_report(results)
    print(f"agent schema conformance pass rate: {len(results)}/{len(cases)}")

    assert len(results) == len(cases)
    assert all(ok for _, ok in results)
    assert "pass rate: 4/4" in capsys.readouterr().out

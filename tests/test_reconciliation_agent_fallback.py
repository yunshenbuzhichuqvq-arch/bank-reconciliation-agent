from decimal import Decimal

import pytest

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgentError
from bank_reconciliation_agent.schemas.ledger import LedgerQuery
from bank_reconciliation_agent.schemas.rag import RagSearchItem
from bank_reconciliation_agent.services.ledger import LedgerService
from bank_reconciliation_agent.services.reconciliation import (
    ReconciliationMatchResult,
    ReconciliationService,
)
from bank_reconciliation_agent.services.task import task_service


def test_write_ledger_entries_falls_back_per_row_and_continues(monkeypatch) -> None:
    service = ReconciliationService()
    task_id = "TASK-AGENT-FALLBACK"
    task_service.replace_task(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=2,
        total_clear_rows=2,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=2,
    )

    def fake_run_workflow(*, user_id, task_id, scenario_type, result, rag_query):
        del user_id, scenario_type, rag_query
        if result.flow_id == "FLOW-BAD":
            raise ExtractionAgentError("invalid LLM JSON for ExtractionAgent")
        return _workflow_state(task_id=task_id, result=result)

    monkeypatch.setattr(service, "_run_workflow_for_result", fake_run_workflow)

    service._write_ledger_entries(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        results=[
            _match_result("FLOW-BAD", Decimal("100.00"), Decimal("99.00")),
            _match_result("FLOW-GOOD", Decimal("200.00"), Decimal("198.00")),
        ],
    )

    page = LedgerService().list(
        user_id="demo_user",
        query=LedgerQuery(task_id=task_id, page=1, page_size=10),
    )
    rows = {row.flow_id: row for row in page.items}

    assert set(rows) == {"FLOW-BAD", "FLOW-GOOD"}
    assert rows["FLOW-BAD"].handle_status == "PENDING_HUMAN"
    assert rows["FLOW-BAD"].ai_confidence == Decimal("0.0000")
    assert "AI 处理异常，自动转人工" in (rows["FLOW-BAD"].ai_audit_opinion or "")
    assert rows["FLOW-GOOD"].handle_status == "PENDING_HUMAN"
    assert rows["FLOW-GOOD"].rag_source == "rule-001"


def test_write_ledger_entries_does_not_swallow_infrastructure_errors(monkeypatch) -> None:
    service = ReconciliationService()

    def fake_run_workflow(*, user_id, task_id, scenario_type, result, rag_query):
        del user_id, task_id, scenario_type, result, rag_query
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(service, "_run_workflow_for_result", fake_run_workflow)

    with pytest.raises(RuntimeError, match="database unavailable"):
        service._write_ledger_entries(
            user_id="demo_user",
            task_id="TASK-INFRA-ERROR",
            scenario_type="BANK_ENTERPRISE",
            results=[_match_result("FLOW-INFRA", Decimal("100.00"), Decimal("99.00"))],
        )


def _match_result(
    flow_id: str,
    bank_amount: Decimal,
    clear_amount: Decimal,
) -> ReconciliationMatchResult:
    return ReconciliationMatchResult(
        flow_id=flow_id,
        status="PENDING_HUMAN",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount=bank_amount,
        clear_amount=clear_amount,
        amount_diff=bank_amount - clear_amount,
    )


def _workflow_state(task_id: str, result: ReconciliationMatchResult) -> dict:
    evidence = _evidence()
    decision = AuditDecision(
        flow_id=result.flow_id,
        decision="PENDING_HUMAN",
        risk_level="MEDIUM",
        reason="正常审计输出",
        ai_suggestion="PENDING_HUMAN",
        evidence=[evidence],
        confidence=0.88,
        fallback_applied=False,
        fallback_level=0,
        next_action="PENDING_HUMAN",
    )
    return {
        "task_id": task_id,
        "user_id": "demo_user",
        "thread_id": task_id,
        "scenario_type": "BANK_ENTERPRISE",
        "current_queue_id": None,
        "source_a_item": {"flow_id": result.flow_id},
        "source_b_item": {"flow_id": result.flow_id},
        "error_type": result.error_type,
        "exception_branch": result.exception_branch,
        "math_result": {
            "bank_amount": str(result.bank_amount),
            "clear_amount": str(result.clear_amount),
            "amount_diff": str(result.amount_diff),
        },
        "extraction_result": {},
        "rag_context": [evidence.model_dump(mode="json")],
        "audit_decision": decision.model_dump(mode="json"),
        "confidence": 0.88,
        "retry_count": 0,
        "fallback_level": 0,
        "next_action": "PENDING_HUMAN",
        "error_message": None,
        "agent_logs": [
            {
                "agent_name": "AuditAgent",
                "step": "decide_with_llm",
                "flow_id": result.flow_id,
                "prompt_version": "v1",
                "fallback_level": 0,
                "prompt_tokens": 10,
                "completion_tokens": 8,
                "llm_tokens": 18,
            }
        ],
        "fallback_path": "L1",
    }


def _evidence() -> RagSearchItem:
    return RagSearchItem(
        chunk_id="rule-001",
        source="rules.md#rule",
        source_name="规则",
        source_url="https://example.com/rule",
        source_file="rules.md",
        section_title="rule",
        element_type="paragraph",
        business_tags=["bank_enterprise"],
        score=0.9,
        content="规则证据",
    )

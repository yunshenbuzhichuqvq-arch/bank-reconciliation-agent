from decimal import Decimal

from bank_reconciliation_agent.services.exception_router import BranchResult
from bank_reconciliation_agent.services.reconciliation import ReconciliationService


def _candidate_branch_result() -> BranchResult:
    return BranchResult(
        flow_id="BANK-001",
        action="EXCEPTION",
        error_type="FUZZY_MATCH_CANDIDATE",
        exception_branch="BE-R007",
        bank_amount=Decimal("128.00"),
        clear_amount=None,
        amount_diff=None,
        fuzzy_candidate={
            "flow_id": "CLEAR-001",
            "amount": "128.00",
            "trade_date": "2026-06-01",
            "counterparty": "上海云杉科技有限公司",
        },
    )


def test_fuzzy_candidate_maps_to_pending_ai_and_activates_summary() -> None:
    service = ReconciliationService()
    result = service._to_match_result(_candidate_branch_result())

    summary = service._summarize_match_results([result])

    assert result.status == "PENDING_AI"
    assert result.error_type == "FUZZY_MATCH_CANDIDATE"
    assert result.exception_branch == "BE-R007"
    assert summary.auto_fixed_rows == 0
    assert summary.pending_ai_rows == 1
    assert summary.pending_human_rows == 0


def test_fuzzy_candidate_queue_and_ledger_payload_keep_type_and_branch(monkeypatch) -> None:
    service = ReconciliationService()
    result = service._to_match_result(_candidate_branch_result())
    monkeypatch.setattr(
        service,
        "_run_workflow_for_result",
        lambda **kwargs: service._agent_error_workflow_state(
            user_id=kwargs["user_id"],
            task_id=kwargs["task_id"],
            scenario_type=kwargs["scenario_type"],
            result=kwargs["result"],
            error=RuntimeError("candidate confirmation belongs to RH.3"),
        ),
    )

    queue_rows = service._write_queue_entries(
        "demo_user",
        "TASK-RH2",
        "BANK_ENTERPRISE",
        [result],
    )
    ledger_rows = service._build_write_bundle(
        user_id="demo_user",
        task_id="TASK-RH2",
        scenario_type="BANK_ENTERPRISE",
        results=[result],
    ).ledger_rows

    assert queue_rows[0]["status"] == "PENDING_AI"
    assert queue_rows[0]["error_type"] == "FUZZY_MATCH_CANDIDATE"
    assert queue_rows[0]["exception_branch"] == "BE-R007"
    assert ledger_rows[0].error_type == "FUZZY_MATCH_CANDIDATE"
    assert ledger_rows[0].exception_branch == "BE-R007"

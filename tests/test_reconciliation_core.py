from __future__ import annotations

from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine

from bank_reconciliation_agent.schemas.ledger import LedgerQuery, LedgerRow
from bank_reconciliation_agent.services.ledger import LedgerService
from bank_reconciliation_agent.services.queue import QueueService
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from bank_reconciliation_agent.services.task import TaskService
from bank_reconciliation_agent.services.transactions import TransactionService


def test_build_match_results_uses_source_ab_error_mapping() -> None:
    service = ReconciliationService()
    source_a_df = pd.DataFrame(
        [
            {"flow_id": "F1001", "amount": 100.00},
            {"flow_id": "F1004", "amount": 300.00},
            {"flow_id": "F1005", "amount": 120.00},
        ]
    )
    source_b_df = pd.DataFrame(
        [
            {"flow_id": "F1001", "amount": 100.00},
            {"flow_id": "F1004", "amount": 295.00},
            {"flow_id": "F1006", "amount": 45.00},
        ]
    )

    results = {row.flow_id: row for row in service._build_match_results(source_a_df, source_b_df)}

    assert results["F1001"].status == "AUTO_FIXED"
    assert results["F1001"].error_type is None
    assert results["F1004"].status == "PENDING_AI"
    assert results["F1004"].error_type == "AMOUNT_MISMATCH"
    assert results["F1004"].amount_diff == Decimal("5.00")
    assert results["F1005"].status == "PENDING_HUMAN"
    assert results["F1005"].error_type == "BANK_UNARRIVED"
    assert results["F1005"].source_a_amount == Decimal("120.00")
    assert results["F1005"].source_b_amount is None
    assert results["F1006"].status == "PENDING_HUMAN"
    assert results["F1006"].error_type == "BOOK_UNRECORDED"
    assert results["F1006"].source_a_amount is None
    assert results["F1006"].source_b_amount == Decimal("45.00")


def test_services_persist_user_scenario_and_filter_by_user() -> None:
    engine = create_engine("sqlite:///:memory:")
    task_service = TaskService(engine)
    transaction_service = TransactionService(engine)
    queue_service = QueueService(engine)
    ledger_service = LedgerService(engine)
    source_a_df = pd.DataFrame(
        [{"flow_id": f"F{i}", "amount": 100 + i, "trade_time": "2026-05-21 09:00:00"} for i in range(10)]
    )
    source_b_df = pd.DataFrame(
        [{"flow_id": f"F{i}", "amount": 100 + i, "trade_time": "2026-05-21 09:00:05"} for i in range(10)]
    )

    task_service.replace_task(
        task_id="TASK_A",
        total_source_a_rows=10,
        total_source_b_rows=10,
        auto_fixed_rows=8,
        pending_ai_rows=1,
        pending_human_rows=2,
        user_id="demo_user",
        scenario_type="BANK_ENTERPRISE",
    )
    transaction_service.replace_task_rows(
        "TASK_A",
        source_a_df,
        source_b_df,
        user_id="demo_user",
        scenario_type="BANK_ENTERPRISE",
    )
    queue_service.replace_task_rows(
        "TASK_A",
        [
            {
                "user_id": "demo_user",
                "task_id": "TASK_A",
                "scenario_type": "BANK_ENTERPRISE",
                "source_a_transaction_id": None,
                "source_b_transaction_id": None,
                "error_type": "AMOUNT_MISMATCH",
                "status": "PENDING_AI",
                "risk_level": "MEDIUM",
                "retry_count": 0,
            }
        ],
        user_id="demo_user",
    )
    ledger_service.replace_task_rows(
        "TASK_A",
        [
            LedgerRow(
                id=0,
                task_id="TASK_A",
                scenario_type="BANK_ENTERPRISE",
                flow_id="F1004",
                error_type="AMOUNT_MISMATCH",
                discrepancy_amount=Decimal("5.00"),
                ai_cleaned_json={"source_a_amount": "300.00", "source_b_amount": "295.00"},
                ai_audit_opinion="金额不一致",
                ai_confidence=Decimal("0.7200"),
                rag_source="chunk-1",
                handle_status="PENDING_HUMAN",
            )
        ],
        user_id="demo_user",
    )
    task_service.replace_task(
        task_id="TASK_A",
        total_source_a_rows=1,
        total_source_b_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
        user_id="other_user",
        scenario_type="BANK_ENTERPRISE",
    )

    task = task_service.get("TASK_A", user_id="demo_user")
    assert task is not None
    assert task.scenario_type == "BANK_ENTERPRISE"
    assert task.total_source_a_rows == 10
    assert task.total_source_b_rows == 10
    assert transaction_service.count_source_a_rows("TASK_A", user_id="demo_user") == 10
    assert transaction_service.count_source_b_rows("TASK_A", user_id="demo_user") == 10
    assert transaction_service.count_source_a_rows("TASK_A", user_id="other_user") == 0
    assert queue_service.count_rows("TASK_A", user_id="demo_user") == 1

    page = ledger_service.list(LedgerQuery(task_id="TASK_A", user_id="demo_user"))
    assert page.total == 1
    assert page.items[0].scenario_type == "BANK_ENTERPRISE"
    assert page.items[0].ai_cleaned_json == {
        "source_a_amount": "300.00",
        "source_b_amount": "295.00",
    }
    assert ledger_service.list(LedgerQuery(task_id="TASK_A", user_id="other_user")).total == 0

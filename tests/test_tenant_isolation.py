from datetime import datetime
from decimal import Decimal

import pandas as pd

from bank_reconciliation_agent.schemas.ledger import LedgerQuery, LedgerRow
from bank_reconciliation_agent.services.ledger import LedgerService
from bank_reconciliation_agent.services.queue import QueueService
from bank_reconciliation_agent.services.rag_log import RagLogService
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from bank_reconciliation_agent.services.review import review_service
from bank_reconciliation_agent.services.task import TaskService
from bank_reconciliation_agent.services.transactions import TransactionService


def test_task_queue_ledger_are_filtered_by_user_id() -> None:
    task_service = TaskService()
    queue_service = QueueService()
    ledger_service = LedgerService()

    for user_id, flow_id, amount in [
        ("u1", "F_U1", Decimal("10.00")),
        ("u2", "F_U2", Decimal("20.00")),
    ]:
        task_service.replace_task(
            user_id=user_id,
            task_id="TASK_SHARED",
            scenario_type="BANK_ENTERPRISE",
            total_bank_rows=1,
            total_clear_rows=1,
            auto_fixed_rows=0,
            pending_ai_rows=0,
            pending_human_rows=1,
        )
        queue_service.replace_task_rows(
            user_id=user_id,
            task_id="TASK_SHARED",
            scenario_type="BANK_ENTERPRISE",
            rows=[
                {
                    "user_id": user_id,
                    "task_id": "TASK_SHARED",
                    "flow_id": flow_id,
                    "bank_transaction_id": None,
                    "clear_transaction_id": None,
                    "error_type": "AMOUNT_MISMATCH",
                    "status": "PENDING_HUMAN",
                    "risk_level": "MEDIUM",
                    "retry_count": 0,
                }
            ],
        )
        ledger_service.replace_task_rows(
            user_id=user_id,
            task_id="TASK_SHARED",
            scenario_type="BANK_ENTERPRISE",
            rows=[
                LedgerRow(
                    id=0,
                    task_id="TASK_SHARED",
                    flow_id=flow_id,
                    error_type="AMOUNT_MISMATCH",
                    bank_amount=amount,
                    clear_amount=Decimal("0.00"),
                    discrepancy_amount=amount,
                    ai_audit_opinion=None,
                    ai_confidence=None,
                    rag_source=None,
                    handle_status="PENDING_HUMAN",
                )
            ],
        )

    assert task_service.get(user_id="u1", task_id="TASK_SHARED") is not None
    assert task_service.get(user_id="u2", task_id="TASK_SHARED") is not None
    assert queue_service.get_row(user_id="u1", task_id="TASK_SHARED", flow_id="F_U1") is not None
    assert queue_service.get_row(user_id="u1", task_id="TASK_SHARED", flow_id="F_U2") is None
    assert queue_service.get_row(user_id="u2", task_id="TASK_SHARED", flow_id="F_U1") is None

    u1_page = ledger_service.list(user_id="u1", query=LedgerQuery(task_id="TASK_SHARED"))
    u2_page = ledger_service.list(user_id="u2", query=LedgerQuery(task_id="TASK_SHARED"))

    assert u1_page.total == 1
    assert [row.flow_id for row in u1_page.items] == ["F_U1"]
    assert u2_page.total == 1
    assert [row.flow_id for row in u2_page.items] == ["F_U2"]


def test_transaction_and_rag_log_rows_are_filtered_by_user_id() -> None:
    transaction_service = TransactionService()
    rag_log_service = RagLogService()
    now = datetime(2026, 6, 5, 10, 0, 0)

    for user_id, flow_id, amount in [
        ("u1", "F_U1", Decimal("10.00")),
        ("u2", "F_U2", Decimal("20.00")),
    ]:
        bank_df = pd.DataFrame(
            [
                {
                    "flow_id": flow_id,
                    "amount": amount,
                    "trade_time": now,
                }
            ]
        )
        clear_df = pd.DataFrame(
            [
                {
                    "flow_id": flow_id,
                    "amount": amount,
                    "transaction_amount": amount,
                    "net_amount": amount,
                    "trade_time": now,
                }
            ]
        )
        transaction_service.replace_task_rows(
            user_id=user_id,
            task_id="TASK_SHARED",
            bank_df=bank_df,
            clear_df=clear_df,
        )
        rag_log_service.replace_task_rows(
            user_id=user_id,
            task_id="TASK_SHARED",
            rows=[
                rag_log_service.build_row(
                    user_id=user_id,
                    task_id="TASK_SHARED",
                    query_text=f"{user_id} query",
                    top_k=2,
                    items=[],
                )
            ],
        )

    assert transaction_service.count_bank_rows(user_id="u1", task_id="TASK_SHARED") == 1
    assert transaction_service.count_clear_rows(user_id="u1", task_id="TASK_SHARED") == 1
    assert transaction_service.count_bank_rows(user_id="u2", task_id="TASK_SHARED") == 1
    assert transaction_service.count_clear_rows(user_id="u2", task_id="TASK_SHARED") == 1
    assert transaction_service.get_bank_row(
        user_id="u1",
        task_id="TASK_SHARED",
        flow_id="F_U2",
    ) is None
    assert transaction_service.get_clear_row(
        user_id="u2",
        task_id="TASK_SHARED",
        flow_id="F_U1",
    ) is None

    assert rag_log_service.count_rows(user_id="u1", task_id="TASK_SHARED") == 1
    assert rag_log_service.count_rows(user_id="u2", task_id="TASK_SHARED") == 1
    assert rag_log_service.get_latest_row(
        user_id="u1",
        task_id="TASK_SHARED",
        query_marker="u2 query",
    ) is None


def test_start_rejects_task_owned_by_other_user() -> None:
    task_service = TaskService()
    task_service.replace_task(
        user_id="owner_user",
        task_id="TASK_OWNED",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )

    try:
        ReconciliationService().start(user_id="other_user", task_id="TASK_OWNED")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
        assert getattr(exc, "detail", None) == "forbidden task access"
    else:
        raise AssertionError("expected HTTPException")


def test_review_approve_rejects_task_owned_by_other_user() -> None:
    task_service = TaskService()
    queue_service = QueueService()
    ledger_service = LedgerService()

    task_service.replace_task(
        user_id="owner_user",
        task_id="TASK_REVIEW_OWNED",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )
    queue_service.replace_task_rows(
        user_id="owner_user",
        task_id="TASK_REVIEW_OWNED",
        scenario_type="BANK_ENTERPRISE",
        rows=[
            {
                "task_id": "TASK_REVIEW_OWNED",
                "flow_id": "F_REVIEW",
                "bank_transaction_id": None,
                "clear_transaction_id": None,
                "error_type": "AMOUNT_MISMATCH",
                "exception_branch": "BE-R002",
                "status": "PENDING_HUMAN",
                "risk_level": "MEDIUM",
                "retry_count": 0,
            }
        ],
    )
    ledger_service.replace_task_rows(
        user_id="owner_user",
        task_id="TASK_REVIEW_OWNED",
        scenario_type="BANK_ENTERPRISE",
        rows=[
            LedgerRow(
                id=0,
                task_id="TASK_REVIEW_OWNED",
                flow_id="F_REVIEW",
                error_type="AMOUNT_MISMATCH",
                bank_amount=Decimal("10.00"),
                clear_amount=Decimal("8.00"),
                discrepancy_amount=Decimal("2.00"),
                ai_audit_opinion="need review",
                ai_confidence=Decimal("0.9000"),
                rag_source="rule-1",
                handle_status="PENDING_HUMAN",
                exception_branch="BE-R002",
            )
        ],
    )
    queue_row = queue_service.get_row(
        user_id="owner_user",
        task_id="TASK_REVIEW_OWNED",
        flow_id="F_REVIEW",
    )
    assert queue_row is not None

    try:
        review_service.approve(
            user_id="other_user",
            queue_id=int(queue_row["id"]),
            action="APPROVED_MATCH",
            handler_username="reviewer_x",
            remark=None,
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
        assert getattr(exc, "detail", None) == "forbidden task access"
    else:
        raise AssertionError("expected HTTPException")

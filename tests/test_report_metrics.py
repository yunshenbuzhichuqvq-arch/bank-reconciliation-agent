from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, insert

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.services.ledger import error_ledger_table
from bank_reconciliation_agent.services.metrics import MetricsService
from bank_reconciliation_agent.services.rag_log import rag_retrieval_log_table
from bank_reconciliation_agent.services.review import human_review_table
from bank_reconciliation_agent.services.task import reconciliation_task_table


def test_task_report_metrics_aggregates_only_requested_task(tmp_path: Path) -> None:
    _reset_tables()
    _insert_fixture_rows()

    result = MetricsService(
        rag_snapshot_path=tmp_path / "missing-rag.json",
        schema_snapshot_path=tmp_path / "missing-schema.json",
    ).get_task_report_metrics(user_id="demo_user", task_id="TASK_REPORT")

    assert result is not None
    assert result.task_id == "TASK_REPORT"
    assert result.user_id == "demo_user"
    assert result.recon_date == "2026-06-18T09:30:00"
    assert result.source_a_rows == 10
    assert result.source_b_rows == 9
    assert result.auto_fixed_rows == 6
    assert result.auto_fix_rate == 0.6
    assert result.ai_processed_rows == 3
    assert result.pending_human_count == 2
    assert result.review_count == 2
    assert result.hold_count == 1
    assert result.discrepancy_amount_total == Decimal("15.75")
    assert isinstance(result.discrepancy_amount_total, Decimal)
    assert result.exception_dist == {"BE-R001": 2, "BE-R002": 1}
    assert result.agent_decision_dist == {"FIXED": 1, "HELD": 1, "PENDING_HUMAN": 1}
    assert result.fallback_dist == {"L1->L2": 2}
    assert result.total_tokens == 321
    assert result.total_cost == Decimal("0.1234")
    assert isinstance(result.total_cost, Decimal)
    assert result.offline.model_dump() == {"status": "no_snapshot"}
    assert result.rag_sources == ["ledger-source-a", "rag-chunk-a", "rag-chunk-b"]


def test_task_report_metrics_returns_none_for_other_user_task(tmp_path: Path) -> None:
    _reset_tables()
    _insert_fixture_rows()

    result = MetricsService(
        rag_snapshot_path=tmp_path / "missing-rag.json",
        schema_snapshot_path=tmp_path / "missing-schema.json",
    ).get_task_report_metrics(user_id="other_user", task_id="TASK_REPORT")

    assert result is None


def _reset_tables() -> None:
    engine = get_engine()
    reconciliation_task_table.metadata.create_all(engine, tables=[reconciliation_task_table])
    error_ledger_table.metadata.create_all(engine, tables=[error_ledger_table])
    human_review_table.metadata.create_all(engine, tables=[human_review_table])
    rag_retrieval_log_table.metadata.create_all(engine, tables=[rag_retrieval_log_table])
    with engine.begin() as connection:
        connection.execute(delete(rag_retrieval_log_table))
        connection.execute(delete(human_review_table))
        connection.execute(delete(error_ledger_table))
        connection.execute(delete(reconciliation_task_table))


def _insert_fixture_rows() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            insert(reconciliation_task_table),
            [
                {
                    "user_id": "demo_user",
                    "task_id": "TASK_REPORT",
                    "scenario_type": "BANK_ENTERPRISE",
                    "task_name": "report task",
                    "status": "COMPLETED",
                    "total_bank_rows": 10,
                    "total_clear_rows": 9,
                    "auto_fixed_rows": 6,
                    "pending_ai_rows": 2,
                    "pending_human_rows": 2,
                    "unresolved_rows": 4,
                    "ai_processed_rows": 3,
                    "fallback_l2_rows": 2,
                    "fallback_l3_rows": 0,
                    "total_llm_tokens": 321,
                    "total_llm_cost": Decimal("0.1234"),
                    "created_at": datetime(2026, 6, 18, 9, 30),
                },
                {
                    "user_id": "demo_user",
                    "task_id": "TASK_OTHER",
                    "scenario_type": "BANK_ENTERPRISE",
                    "task_name": "other task",
                    "status": "COMPLETED",
                    "total_bank_rows": 99,
                    "total_clear_rows": 99,
                    "auto_fixed_rows": 99,
                    "pending_ai_rows": 0,
                    "pending_human_rows": 0,
                    "unresolved_rows": 0,
                    "ai_processed_rows": 99,
                    "fallback_l2_rows": 0,
                    "fallback_l3_rows": 0,
                    "total_llm_tokens": 999,
                    "total_llm_cost": Decimal("9.9999"),
                    "created_at": datetime(2026, 6, 18, 10, 0),
                },
            ],
        )
        connection.execute(
            insert(error_ledger_table),
            [
                _ledger_row("FLOW-1", "BE-R001", "FIXED", "L1->L2", "10.50", "ledger-source-a"),
                _ledger_row("FLOW-2", "BE-R001", "HELD", "L1->L2", "5.25", "ledger-source-a"),
                _ledger_row("FLOW-3", "BE-R002", "PENDING_HUMAN", None, "0.00", None),
                _ledger_row(
                    "FLOW-OTHER", "BE-R999", "HELD", "L1->L3", "999.00", "other-source",
                    task_id="TASK_OTHER",
                ),
            ],
        )
        connection.execute(
            insert(human_review_table),
            [
                _review_row(1, "APPROVED_MATCH"),
                _review_row(2, "FORCE_HOLD"),
                _review_row(3, "FORCE_HOLD", task_id="TASK_OTHER"),
            ],
        )
        connection.execute(
            insert(rag_retrieval_log_table),
            [
                {
                    "user_id": "demo_user",
                    "task_id": "TASK_REPORT",
                    "scenario_type": "BANK_ENTERPRISE",
                    "query_text": "report query",
                    "top_k": 2,
                    "sources": ["rag-chunk-a", "rag-chunk-b"],
                },
                {
                    "user_id": "demo_user",
                    "task_id": "TASK_OTHER",
                    "scenario_type": "BANK_ENTERPRISE",
                    "query_text": "other query",
                    "top_k": 1,
                    "sources": ["other-chunk"],
                },
            ],
        )


def _ledger_row(
    flow_id: str,
    exception_branch: str,
    handle_status: str,
    fallback_path: str | None,
    discrepancy_amount: str,
    rag_source: str | None,
    *,
    task_id: str = "TASK_REPORT",
) -> dict[str, object]:
    return {
        "user_id": "demo_user",
        "task_id": task_id,
        "scenario_type": "BANK_ENTERPRISE",
        "flow_id": flow_id,
        "error_type": "AMOUNT_MISMATCH",
        "exception_branch": exception_branch,
        "discrepancy_amount": Decimal(discrepancy_amount),
        "fallback_path": fallback_path,
        "handle_status": handle_status,
        "rag_source": rag_source,
    }


def _review_row(queue_id: int, action: str, *, task_id: str = "TASK_REPORT") -> dict[str, object]:
    return {
        "user_id": "demo_user",
        "scenario_type": "BANK_ENTERPRISE",
        "queue_id": queue_id,
        "task_id": task_id,
        "ai_suggestion": "PENDING_HUMAN",
        "ai_fallback_level": 0,
        "action": action,
        "handler_username": "reviewer",
    }

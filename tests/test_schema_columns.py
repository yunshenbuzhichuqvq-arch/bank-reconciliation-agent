from pathlib import Path

from sqlalchemy import Numeric, String, create_engine, inspect

from bank_reconciliation_agent.services.agent_log import agent_execution_log_table
from bank_reconciliation_agent.services.ledger import error_ledger_table
from bank_reconciliation_agent.services.queue import reconciliation_queue_table
from bank_reconciliation_agent.services.rag_log import rag_retrieval_log_table
from bank_reconciliation_agent.services.task import reconciliation_task_table
from bank_reconciliation_agent.services.transactions import (
    bank_transaction_table,
    clear_transaction_table,
)


def test_task_101_schema_columns_are_present_after_create_all() -> None:
    engine = create_engine("sqlite:///:memory:")
    tables = [
        reconciliation_task_table,
        bank_transaction_table,
        clear_transaction_table,
        reconciliation_queue_table,
        error_ledger_table,
        rag_retrieval_log_table,
        agent_execution_log_table,
    ]

    for table in tables:
        table.metadata.create_all(engine, tables=[table])

    inspector = inspect(engine)

    assert_columns(
        inspector,
        "t_reconciliation_task",
        {"user_id", "scenario_type", "batch_id"},
    )
    assert_columns(inspector, "t_bank_transaction", {"user_id"})
    assert_columns(inspector, "t_clear_transaction", {"user_id"})
    assert_columns(
        inspector,
        "t_reconciliation_queue",
        {"user_id", "scenario_type", "exception_branch"},
    )
    assert_columns(
        inspector,
        "t_error_ledger",
        {"user_id", "scenario_type", "exception_branch"},
    )
    assert_columns(inspector, "t_rag_retrieval_log", {"user_id", "scenario_type"})
    assert_columns(
        inspector,
        "t_agent_execution_log",
        {
            "prompt_version",
            "fallback_level",
            "llm_tokens",
            "pre_hook_results",
            "post_hook_results",
        },
    )


def test_task_2a13_schema_columns_are_present_after_create_all() -> None:
    engine = create_engine("sqlite:///:memory:")
    tables = [
        agent_execution_log_table,
        reconciliation_task_table,
        error_ledger_table,
    ]

    for table in tables:
        table.metadata.create_all(engine, tables=[table])

    inspector = inspect(engine)

    assert_columns(
        inspector,
        "t_agent_execution_log",
        {
            "prompt_version",
            "fallback_level",
            "llm_tokens",
            "pre_hook_results",
            "post_hook_results",
        },
    )
    assert_columns(
        inspector,
        "t_reconciliation_task",
        {
            "ai_processed_rows",
            "fallback_l2_rows",
            "fallback_l3_rows",
            "total_llm_tokens",
            "total_llm_cost",
        },
    )
    assert_columns(inspector, "t_error_ledger", {"fallback_path"})
    assert isinstance(reconciliation_task_table.c.total_llm_cost.type, Numeric)
    assert reconciliation_task_table.c.total_llm_cost.type.precision == 10
    assert reconciliation_task_table.c.total_llm_cost.type.scale == 4


def test_task_2a13_schema_sql_contains_runtime_columns() -> None:
    schema_sql = read_schema_sql()

    expected_fragments = [
        "prompt_version VARCHAR(16) DEFAULT NULL",
        "fallback_level INT NOT NULL DEFAULT 0",
        "llm_tokens INT NOT NULL DEFAULT 0",
        "pre_hook_results JSON DEFAULT NULL",
        "post_hook_results JSON DEFAULT NULL",
        "ai_processed_rows INT NOT NULL DEFAULT 0",
        "fallback_l2_rows INT NOT NULL DEFAULT 0",
        "fallback_l3_rows INT NOT NULL DEFAULT 0",
        "total_llm_tokens INT NOT NULL DEFAULT 0",
        "total_llm_cost DECIMAL(10,4) NOT NULL DEFAULT 0.0000",
        "fallback_path VARCHAR(128) DEFAULT NULL",
    ]
    for fragment in expected_fragments:
        assert fragment in schema_sql


def test_task_101_branch_indexes_are_present() -> None:
    engine = create_engine("sqlite:///:memory:")

    reconciliation_queue_table.metadata.create_all(
        engine, tables=[reconciliation_queue_table]
    )
    error_ledger_table.metadata.create_all(engine, tables=[error_ledger_table])

    inspector = inspect(engine)

    assert "idx_error_branch" in index_names(inspector, "t_reconciliation_queue")
    assert "idx_branch_status" in index_names(inspector, "t_error_ledger")


def test_fuzzy_candidate_fits_existing_error_type_columns() -> None:
    value = "FUZZY_MATCH_CANDIDATE"

    assert len(value) <= reconciliation_queue_table.c.error_type.type.length
    assert len(value) <= error_ledger_table.c.error_type.type.length
    assert "error_type VARCHAR(32)" in read_schema_sql()


def test_stage_25_recovery_columns_in_service_table() -> None:
    engine = create_engine("sqlite:///:memory:")
    reconciliation_task_table.metadata.create_all(engine, tables=[reconciliation_task_table])
    inspector = inspect(engine)

    assert_columns(
        inspector,
        "t_reconciliation_task",
        {
            "job_attempt",
            "retry_recovered",
            "retry_exhausted",
            "failure_type",
            "failure_summary",
            "failed_at",
            "force_requeue_count",
        },
    )

    job_col = inspector.get_columns("t_reconciliation_task")[
        next(
            i
            for i, c in enumerate(inspector.get_columns("t_reconciliation_task"))
            if c["name"] == "job_attempt"
        )
    ]
    assert job_col["nullable"] is False
    assert job_col["default"] in ("0", "'0'")

    exhausted_col = inspector.get_columns("t_reconciliation_task")[
        next(
            i
            for i, c in enumerate(inspector.get_columns("t_reconciliation_task"))
            if c["name"] == "retry_exhausted"
        )
    ]
    assert exhausted_col["nullable"] is False

    force_col = inspector.get_columns("t_reconciliation_task")[
        next(
            i
            for i, c in enumerate(inspector.get_columns("t_reconciliation_task"))
            if c["name"] == "force_requeue_count"
        )
    ]
    assert force_col["nullable"] is False
    assert force_col["default"] in ("0", "'0'")

    for nullable_col in ("failure_type", "failure_summary", "failed_at"):
        col_info = inspector.get_columns("t_reconciliation_task")[
            next(
                i
                for i, c in enumerate(inspector.get_columns("t_reconciliation_task"))
                if c["name"] == nullable_col
            )
        ]
        assert col_info["nullable"] is True, f"{nullable_col} should be nullable"

    assert isinstance(reconciliation_task_table.c.failure_type.type.length, int)
    assert reconciliation_task_table.c.failure_type.type.length == 64
    assert isinstance(reconciliation_task_table.c.failure_summary.type.length, int)
    assert reconciliation_task_table.c.failure_summary.type.length == 255


def test_stage_25_recovery_columns_in_schema_sql() -> None:
    schema_sql = read_schema_sql()

    expected_fragments = [
        "job_attempt INT NOT NULL DEFAULT 0",
        "retry_recovered BOOLEAN NOT NULL DEFAULT 0",
        "retry_exhausted BOOLEAN NOT NULL DEFAULT 0",
        "failure_type VARCHAR(64) NULL",
        "failure_summary VARCHAR(255) NULL",
        "failed_at TIMESTAMP NULL",
        "force_requeue_count INT NOT NULL DEFAULT 0",
    ]
    for fragment in expected_fragments:
        assert fragment in schema_sql, f"Missing in schema.sql: {fragment}"


def test_stage_28_bank_t1_reference_columns_in_service_table() -> None:
    engine = create_engine("sqlite:///:memory:")
    bank_transaction_table.metadata.create_all(engine, tables=[bank_transaction_table])
    inspector = inspect(engine)

    reference_columns = {"reference_no", "merchant_order_no", "voucher_no"}
    assert_columns(inspector, "t_bank_transaction", reference_columns)

    columns = {c["name"]: c for c in inspector.get_columns("t_bank_transaction")}
    for column_name in reference_columns:
        assert columns[column_name]["nullable"] is True
        table_column = bank_transaction_table.c[column_name]
        assert isinstance(table_column.type, String)
        assert table_column.type.length == 64
        assert table_column.nullable is True


def test_stage_28_bank_t1_reference_columns_in_schema_sql() -> None:
    schema_sql = read_schema_sql()

    for fragment in (
        "voucher_no VARCHAR(64)",
        "reference_no VARCHAR(64)",
        "merchant_order_no VARCHAR(64)",
    ):
        assert fragment in schema_sql, f"Missing in schema.sql: {fragment}"


def assert_columns(inspector, table_name: str, expected_columns: set[str]) -> None:
    actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
    assert expected_columns <= actual_columns

def index_names(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def read_schema_sql() -> str:
    return Path("src/bank_reconciliation_agent/db/schema.sql").read_text(encoding="utf-8")

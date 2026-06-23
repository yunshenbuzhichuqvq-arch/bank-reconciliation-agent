from pathlib import Path

from sqlalchemy import Numeric, create_engine, inspect

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


def assert_columns(inspector, table_name: str, expected_columns: set[str]) -> None:
    actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
    assert expected_columns <= actual_columns


def index_names(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def read_schema_sql() -> str:
    return Path("src/bank_reconciliation_agent/db/schema.sql").read_text(encoding="utf-8")

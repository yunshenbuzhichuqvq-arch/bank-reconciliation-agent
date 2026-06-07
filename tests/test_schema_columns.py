from sqlalchemy import create_engine, inspect

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


def test_task_101_branch_indexes_are_present() -> None:
    engine = create_engine("sqlite:///:memory:")

    reconciliation_queue_table.metadata.create_all(
        engine, tables=[reconciliation_queue_table]
    )
    error_ledger_table.metadata.create_all(engine, tables=[error_ledger_table])

    inspector = inspect(engine)

    assert "idx_error_branch" in index_names(inspector, "t_reconciliation_queue")
    assert "idx_branch_status" in index_names(inspector, "t_error_ledger")


def assert_columns(inspector, table_name: str, expected_columns: set[str]) -> None:
    actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
    assert expected_columns <= actual_columns


def index_names(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}

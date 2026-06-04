import importlib
import re
from pathlib import Path


SCHEMA_PATH = Path("src/bank_reconciliation_agent/db/schema.sql")
TABLE_TARGETS = [
    ("t_reconciliation_task", "services.task", "reconciliation_task_table"),
    ("t_source_a_transaction", "services.transactions", "source_a_transaction_table"),
    ("t_source_b_transaction", "services.transactions", "source_b_transaction_table"),
    ("t_reconciliation_queue", "services.queue", "reconciliation_queue_table"),
    ("t_error_ledger", "services.ledger", "error_ledger_table"),
    ("t_rag_retrieval_log", "services.rag_log", "rag_retrieval_log_table"),
]
CONSTRAINT_PREFIXES = ("INDEX", "UNIQUE", "PRIMARY", "KEY", "CONSTRAINT", "FOREIGN")


def test_schema_sql_columns_match_service_tables() -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    for table_name, module_name, table_var in TABLE_TARGETS:
        schema_columns = _schema_columns(schema_sql, table_name)
        service_columns = _service_columns(module_name, table_var)

        assert schema_columns == service_columns, (
            f"{table_name} schema/service column mismatch: "
            f"schema_only={sorted(schema_columns - service_columns)} "
            f"service_only={sorted(service_columns - schema_columns)}"
        )


def _schema_columns(schema_sql: str, table_name: str) -> set[str]:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {re.escape(table_name)} \((.*?)\n\) ENGINE",
        schema_sql,
        re.S,
    )
    assert match is not None, f"{table_name} not found in schema.sql"

    columns: set[str] = set()
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.upper().startswith(CONSTRAINT_PREFIXES):
            continue
        column_match = re.match(r"`?([a-z_]+)`?\s+[A-Za-z]", stripped)
        if column_match:
            columns.add(column_match.group(1))
    return columns


def _service_columns(module_name: str, table_var: str) -> set[str]:
    module = importlib.import_module(f"bank_reconciliation_agent.{module_name}")
    table = getattr(module, table_var)
    return set(table.c.keys())

from __future__ import annotations

import argparse
from collections.abc import Sequence

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.sql.schema import Table

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.services.agent_log import agent_execution_log_table
from bank_reconciliation_agent.services.ledger import error_ledger_table
from bank_reconciliation_agent.services.queue import reconciliation_queue_table
from bank_reconciliation_agent.services.rag_log import rag_retrieval_log_table
from bank_reconciliation_agent.services.review import human_review_table
from bank_reconciliation_agent.services.task import reconciliation_task_table
from bank_reconciliation_agent.services.transactions import (
    bank_transaction_table,
    clear_transaction_table,
)


def collect_service_tables() -> list[Table]:
    return [
        reconciliation_task_table,
        bank_transaction_table,
        clear_transaction_table,
        reconciliation_queue_table,
        error_ledger_table,
        human_review_table,
        agent_execution_log_table,
        rag_retrieval_log_table,
    ]


def database_name(url: URL) -> str:
    return url.database or "<no database>"


def drop_all_tables(engine: Engine) -> None:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        table_names = [row[0] for row in connection.execute(text("SHOW TABLES")).all()]
        for table_name in table_names:
            escaped_name = str(table_name).replace("`", "``")
            connection.execute(text(f"DROP TABLE IF EXISTS `{escaped_name}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def create_service_tables(engine: Engine, tables: Sequence[Table]) -> None:
    for table in tables:
        table.metadata.create_all(engine, tables=[table])


def print_self_check(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    task_columns = {
        column["name"] for column in inspector.get_columns(reconciliation_task_table.name)
    }
    print(f"Table count: {len(table_names)}")
    print(f"t_reconciliation_task has scenario_type: {'scenario_type' in task_columns}")
    print(f"t_reconciliation_task has batch_id: {'batch_id' in task_columns}")


def reset_database(*, yes: bool) -> None:
    url = make_url(settings.mysql_dsn)
    tables = collect_service_tables()
    print(f"Target database: {database_name(url)}")
    print(f"Plan: drop all existing tables, then recreate {len(tables)} service tables")

    if not yes:
        print("Dry run only. Re-run with --yes to execute.")
        return

    engine = create_engine(settings.mysql_dsn, future=True)
    drop_all_tables(engine)
    create_service_tables(engine, tables)
    print_self_check(engine)


def main() -> None:
    parser = argparse.ArgumentParser(description="Drop and rebuild the configured dev database.")
    parser.add_argument("--yes", action="store_true", help="Actually drop and recreate all tables.")
    args = parser.parse_args()
    reset_database(yes=args.yes)


if __name__ == "__main__":
    main()

from sqlalchemy.engine import make_url

from scripts import reset_db


def test_collect_service_tables_covers_mvp1_persistence_tables() -> None:
    table_names = {table.name for table in reset_db.collect_service_tables()}

    assert table_names == {
        "t_agent_execution_log",
        "t_bank_transaction",
        "t_clear_transaction",
        "t_error_ledger",
        "t_human_review",
        "t_rag_retrieval_log",
        "t_reconciliation_queue",
        "t_reconciliation_task",
    }


def test_database_name_uses_dsn_database_component() -> None:
    url = make_url("mysql+pymysql://root:password@127.0.0.1:3306/AI_agent")

    assert reset_db.database_name(url) == "AI_agent"

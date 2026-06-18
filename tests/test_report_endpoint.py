from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete, insert

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.services.ledger import error_ledger_table
from bank_reconciliation_agent.services.rag_log import rag_retrieval_log_table
from bank_reconciliation_agent.services.review import human_review_table
from bank_reconciliation_agent.services.task import reconciliation_task_table


client = TestClient(app)
DEMO_HEADERS = {"X-User-ID": "demo_user"}


def test_report_endpoint_returns_task_report_with_real_metrics() -> None:
    _reset_tables()
    _insert_task(user_id="demo_user", task_id="TASK_REPORT")
    _insert_ledger(user_id="demo_user", task_id="TASK_REPORT")

    response = client.get("/api/v1/reconcile/TASK_REPORT/report", headers=DEMO_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["error_code"] is None
    assert body["data"]["task_id"] == "TASK_REPORT"
    assert body["data"]["generated_at"]
    assert body["data"]["llm_used"] is True
    assert body["data"]["metrics"]["source_a_rows"] == 4
    assert body["data"]["metrics"]["discrepancy_amount_total"] == "5.25"
    assert body["data"]["narrative"]["risk_summary"]
    assert "来源 A 笔数：4" in body["data"]["markdown"]
    assert "差异金额合计：5.25" in body["data"]["markdown"]


def test_report_endpoint_requires_user_header() -> None:
    response = client.get("/api/v1/reconcile/TASK_REPORT/report")

    assert response.status_code == 401
    assert response.json()["detail"] == "X-User-ID header is required"


def test_report_endpoint_returns_404_for_task_owned_by_other_user() -> None:
    _reset_tables()
    _insert_task(user_id="other_user", task_id="TASK_OTHER_USER")

    response = client.get("/api/v1/reconcile/TASK_OTHER_USER/report", headers=DEMO_HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"] == "reconciliation task not found"


def test_report_endpoint_returns_404_for_missing_task() -> None:
    _reset_tables()

    response = client.get("/api/v1/reconcile/NO_SUCH_TASK/report", headers=DEMO_HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"] == "reconciliation task not found"


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


def _insert_task(*, user_id: str, task_id: str) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            insert(reconciliation_task_table).values(
                user_id=user_id,
                task_id=task_id,
                scenario_type="BANK_ENTERPRISE",
                task_name=f"{task_id} reconciliation",
                status="COMPLETED",
                total_bank_rows=4,
                total_clear_rows=4,
                auto_fixed_rows=3,
                pending_ai_rows=0,
                pending_human_rows=1,
                unresolved_rows=1,
                ai_processed_rows=1,
                fallback_l2_rows=0,
                fallback_l3_rows=0,
                total_llm_tokens=10,
                total_llm_cost=Decimal("0.0010"),
            )
        )


def _insert_ledger(*, user_id: str, task_id: str) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            insert(error_ledger_table).values(
                user_id=user_id,
                task_id=task_id,
                scenario_type="BANK_ENTERPRISE",
                flow_id="FLOW-REPORT",
                error_type="AMOUNT_MISMATCH",
                exception_branch="BE-R002",
                discrepancy_amount=Decimal("5.25"),
                fallback_path=None,
                handle_status="PENDING_HUMAN",
            )
        )

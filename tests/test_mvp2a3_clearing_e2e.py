from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import select

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.schemas.ledger import LedgerQuery
from bank_reconciliation_agent.services.ledger import LedgerService, error_ledger_table
from bank_reconciliation_agent.services.queue import QueueService
from bank_reconciliation_agent.services.task import TaskService
from scripts.generate_mock_excel import (
    BANK_CLEARING_EXPECTED_BRANCHES,
    DEFAULT_BANK_CLEARING_NORMAL_ROWS,
    generate_mvp2a3_mock_excel,
)
from tests.auth_helpers import demo_bearer_headers


client = TestClient(app)
DEMO_HEADERS = demo_bearer_headers()


def test_mvp2a3_bank_clearing_upload_start_and_exceptions_match_expected_branches(
    tmp_path: Path,
) -> None:
    bank_path, clear_path = generate_mvp2a3_mock_excel(tmp_path)
    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)

    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        upload_response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
            data={"scenario_type": "BANK_CLEARING"},
            files={
                "bank_file": (
                    "mvp2a3_core.xlsx",
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    "mvp2a3_clearing.xlsx",
                    clear_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )

    assert upload_response.status_code == 200
    upload_body = upload_response.json()["data"]
    task_id = upload_body["task_id"]
    expected_pending = {
        flow_id: branch
        for flow_id, branch in BANK_CLEARING_EXPECTED_BRANCHES.items()
        if branch[2] == "PENDING_HUMAN"
    }
    expected_auto_fixed = DEFAULT_BANK_CLEARING_NORMAL_ROWS + 1

    assert upload_body["status"] == "UPLOADED"
    assert upload_body["total_bank_rows"] == len(bank_df)
    assert upload_body["total_clear_rows"] == len(clear_df)
    assert upload_body["auto_fixed_rows"] == expected_auto_fixed
    assert upload_body["pending_ai_rows"] == 0
    assert upload_body["pending_human_rows"] == len(expected_pending)

    task = TaskService().get(user_id="demo_user", task_id=task_id)
    assert task is not None
    assert task.scenario_type == "BANK_CLEARING"

    start_response = client.post(f"/api/v1/reconcile/{task_id}/start", headers=DEMO_HEADERS)
    assert start_response.status_code == 200
    assert start_response.json()["data"]["status"] == "AI_RUNNING"

    status_response = client.get(f"/api/v1/reconcile/{task_id}/status", headers=DEMO_HEADERS)
    assert status_response.status_code == 200
    status_body = status_response.json()["data"]
    assert status_body["status"] == "AI_RUNNING"
    assert status_body["auto_fixed_rows"] == expected_auto_fixed
    assert status_body["pending_human_rows"] == len(expected_pending)
    assert status_body["unresolved_rows"] == len(expected_pending)

    exceptions_response = client.get(
        f"/api/v1/reconcile/{task_id}/exceptions",
        headers=DEMO_HEADERS,
    )
    assert exceptions_response.status_code == 200
    exceptions_body = exceptions_response.json()["data"]
    items_by_flow_id = {item["flow_id"]: item for item in exceptions_body["items"]}

    assert exceptions_body["task_id"] == task_id
    assert exceptions_body["total"] == len(expected_pending)
    assert set(items_by_flow_id) == set(expected_pending)

    for flow_id, (error_type, exception_branch, disposition) in expected_pending.items():
        item = items_by_flow_id[flow_id]
        assert item["status"] == disposition
        assert item["error_type"] == error_type
        assert item["exception_branch"] == exception_branch
        assert item["audit_decision"]["decision"] == "PENDING_HUMAN"
        assert item["rag_evidence"]
        assert all(
            "data/rag/raw_sources/bank_clearing/" in evidence["source_file"]
            for evidence in item["rag_evidence"]
        )

    queue_service = QueueService()
    ledger_service = LedgerService()
    ledger_page = ledger_service.list(
        user_id="demo_user",
        query=LedgerQuery(task_id=task_id, page=1, page_size=10_000),
    )
    ledger_by_flow_id = {row.flow_id: row for row in ledger_page.items}

    for flow_id in expected_pending:
        queue_row = queue_service.get_row(user_id="demo_user", task_id=task_id, flow_id=flow_id)
        assert queue_row is not None
        assert queue_row["scenario_type"] == "BANK_CLEARING"

    with get_engine().connect() as connection:
        ledger_rows = connection.execute(
            select(error_ledger_table.c.flow_id, error_ledger_table.c.scenario_type).where(
                error_ledger_table.c.user_id == "demo_user",
                error_ledger_table.c.task_id == task_id,
            )
        ).all()
    ledger_scenarios = {flow_id: scenario_type for flow_id, scenario_type in ledger_rows}
    assert {ledger_scenarios[flow_id] for flow_id in expected_pending} == {"BANK_CLEARING"}

    assert ledger_by_flow_id["BC3003"].exception_branch == "BC-R003"
    assert ledger_by_flow_id["BC3004"].exception_branch == "BC-R003"
    assert ledger_by_flow_id["BC3002"].exception_branch == "BC-R001"
    assert ledger_by_flow_id["BC3002"].rag_source is not None

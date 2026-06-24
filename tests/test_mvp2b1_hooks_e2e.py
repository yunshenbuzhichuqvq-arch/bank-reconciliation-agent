import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
import pandas as pd

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.services.agent_log import agent_execution_log_table
from bank_reconciliation_agent.services.ledger import LedgerService
from bank_reconciliation_agent.services.queue import QueueService
from bank_reconciliation_agent.services.rag_log import rag_log_service
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from bank_reconciliation_agent.services.task import TaskService
from scripts.generate_mock_excel import (
    BANK_CLEARING_EXPECTED_BRANCHES,
    EXPECTED_BRANCHES,
    generate_mvp1_mock_excel,
    generate_mvp2a3_mock_excel,
)
from tests.auth_helpers import demo_bearer_headers


client = TestClient(app)
DEMO_HEADERS = demo_bearer_headers()


def test_mvp2b1_bank_enterprise_e2e_keeps_baseline_and_exposes_hook_results(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)
    expected_pending = {
        flow_id: branch
        for flow_id, branch in EXPECTED_BRANCHES.items()
        if branch[2] == "PENDING_HUMAN"
    }
    expected_auto_fixed = len(set(bank_df["flow_id"]) | set(clear_df["flow_id"])) - len(
        expected_pending
    )
    task_id = _upload_task(
        tmp_path=tmp_path,
        scenario_type="BANK_ENTERPRISE",
        generator=lambda output_dir: (bank_path, clear_path),
    )
    start_response = client.post(f"/api/v1/reconcile/{task_id}/start", headers=DEMO_HEADERS)

    assert start_response.status_code == 200
    assert start_response.json()["data"]["status"] == "AI_RUNNING"

    persisted_task = TaskService().get(user_id="demo_user", task_id=task_id)
    assert persisted_task is not None
    assert persisted_task.scenario_type == "BANK_ENTERPRISE"
    assert persisted_task.auto_fixed_rows == expected_auto_fixed
    assert persisted_task.pending_ai_rows == 0
    assert persisted_task.pending_human_rows == len(expected_pending)
    assert persisted_task.ai_processed_rows == len(expected_pending)

    assert QueueService().count_rows(user_id="demo_user", task_id=task_id) == len(expected_pending)
    assert LedgerService().list(user_id="demo_user", query=_ledger_query(task_id)).total == len(
        expected_pending
    )

    rows = _agent_log_rows(task_id)
    assert len(rows) == len(expected_pending)
    assert {_row_flow_id(row) for row in rows} == set(expected_pending)
    for row in rows:
        post_hook_results = json.loads(row["post_hook_results"])
        assert set(post_hook_results) == {"schema_retries", "constraint_violated", "decision_route"}
        assert isinstance(post_hook_results["schema_retries"], int)
        assert isinstance(post_hook_results["constraint_violated"], list)
        assert post_hook_results["decision_route"] == "PENDING_HUMAN"

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert '"event": "validation_hook_passed"' in messages
    assert '"hook_name": "ValidationHook"' in messages
    assert '"event": "auth_hook_passed"' in messages
    assert '"hook_name": "AuthHook"' in messages
    assert '"event": "memory_hook_passed"' in messages
    assert '"hook_name": "MemoryHook"' in messages
    assert '"event": "schema_hook_passed"' in messages
    assert '"hook_name": "SchemaHook"' in messages
    assert '"event": "constraint_hook_evaluated"' in messages
    assert '"hook_name": "ConstraintHook"' in messages
    assert '"event": "decision_hook_routed"' in messages
    assert '"hook_name": "DecisionHook"' in messages


def test_mvp2b1_bank_clearing_e2e_keeps_baseline_and_exposes_hook_results(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    task_id = _upload_task(
        tmp_path=tmp_path,
        scenario_type="BANK_CLEARING",
        generator=generate_mvp2a3_mock_excel,
    )
    start_response = client.post(f"/api/v1/reconcile/{task_id}/start", headers=DEMO_HEADERS)

    assert start_response.status_code == 200
    assert start_response.json()["data"]["status"] == "AI_RUNNING"

    expected_pending = {
        flow_id: branch
        for flow_id, branch in BANK_CLEARING_EXPECTED_BRANCHES.items()
        if branch[2] == "PENDING_HUMAN"
    }
    persisted_task = TaskService().get(user_id="demo_user", task_id=task_id)
    assert persisted_task is not None
    assert persisted_task.scenario_type == "BANK_CLEARING"
    assert persisted_task.auto_fixed_rows == 1
    assert persisted_task.pending_ai_rows == 0
    assert persisted_task.pending_human_rows == len(expected_pending)
    assert persisted_task.ai_processed_rows == len(expected_pending)

    assert QueueService().count_rows(user_id="demo_user", task_id=task_id) == len(expected_pending)
    assert LedgerService().list(user_id="demo_user", query=_ledger_query(task_id)).total == len(
        expected_pending
    )

    rows = _agent_log_rows(task_id)
    assert len(rows) == len(expected_pending)
    assert {_row_flow_id(row) for row in rows} == set(expected_pending)
    for row in rows:
        post_hook_results = json.loads(row["post_hook_results"])
        assert set(post_hook_results) == {"schema_retries", "constraint_violated", "decision_route"}
        assert isinstance(post_hook_results["schema_retries"], int)
        assert isinstance(post_hook_results["constraint_violated"], list)
        assert post_hook_results["decision_route"] == "PENDING_HUMAN"

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert '"event": "validation_hook_passed"' in messages
    assert '"hook_name": "ValidationHook"' in messages
    assert '"event": "auth_hook_passed"' in messages
    assert '"hook_name": "AuthHook"' in messages
    assert '"event": "memory_hook_passed"' in messages
    assert '"hook_name": "MemoryHook"' in messages
    assert '"event": "schema_hook_passed"' in messages
    assert '"hook_name": "SchemaHook"' in messages
    assert '"event": "constraint_hook_evaluated"' in messages
    assert '"hook_name": "ConstraintHook"' in messages
    assert '"event": "decision_hook_routed"' in messages
    assert '"hook_name": "DecisionHook"' in messages


def test_mvp2b1_side_effect_failure_does_not_break_bank_clearing_upload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    task_id = "TASK_SIDE_EFFECT_CLEARING"

    def failing_replace_task_rows(**kwargs):
        del kwargs
        raise RuntimeError("rag log unavailable")

    monkeypatch.setattr(rag_log_service, "replace_task_rows", failing_replace_task_rows)
    monkeypatch.setattr(ReconciliationService, "_generate_task_id", lambda self, content: task_id)

    returned_task_id = _upload_task(
        tmp_path=tmp_path,
        scenario_type="BANK_CLEARING",
        generator=generate_mvp2a3_mock_excel,
    )

    expected_pending = {
        flow_id: branch
        for flow_id, branch in BANK_CLEARING_EXPECTED_BRANCHES.items()
        if branch[2] == "PENDING_HUMAN"
    }
    assert returned_task_id == task_id
    assert QueueService().count_rows(user_id="demo_user", task_id=task_id) == len(expected_pending)
    assert LedgerService().list(user_id="demo_user", query=_ledger_query(task_id)).total == len(
        expected_pending
    )

    persisted_task = TaskService().get(user_id="demo_user", task_id=task_id)
    assert persisted_task is not None
    assert persisted_task.ai_processed_rows == len(expected_pending)

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert '"event": "reconciliation_side_effect_failed"' in messages
    assert '"side_effect_failed": "rag_log"' in messages


def _upload_task(
    *,
    tmp_path: Path,
    scenario_type: str,
    generator,
) -> str:
    bank_path, clear_path = generator(tmp_path)
    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
            data={"scenario_type": scenario_type},
            files={
                "bank_file": (
                    bank_path.name,
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    clear_path.name,
                    clear_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
    assert response.status_code == 200
    return response.json()["data"]["task_id"]


def _agent_log_rows(task_id: str) -> list[dict[str, object]]:
    with get_engine().connect() as connection:
        return list(
            connection.execute(
                select(agent_execution_log_table).where(
                    agent_execution_log_table.c.user_id == "demo_user",
                    agent_execution_log_table.c.task_id == task_id,
                )
            ).mappings()
        )


def _row_flow_id(row: dict[str, object]) -> str:
    payload = json.loads(row["input_payload"])
    return str(payload["flow_id"])


def _ledger_query(task_id: str):
    from bank_reconciliation_agent.schemas.ledger import LedgerQuery

    return LedgerQuery(task_id=task_id, page=1, page_size=10_000)

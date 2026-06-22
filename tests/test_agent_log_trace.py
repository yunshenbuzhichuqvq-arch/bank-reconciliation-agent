import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.services.agent_log import (
    agent_execution_log_table,
    agent_log_service,
)
from bank_reconciliation_agent.services.trace import trace_writer
from scripts.generate_mock_excel import EXPECTED_BRANCHES, generate_mvp1_mock_excel
from tests.auth_helpers import demo_bearer_headers


client = TestClient(app)
DEMO_HEADERS = demo_bearer_headers()


def _upload_task(tmp_path: Path) -> str:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
            files={
                "bank_file": (
                    "bank_transactions.xlsx",
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    "clear_transactions.xlsx",
                    clear_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
    assert response.status_code == 200
    return response.json()["data"]["task_id"]


def test_upload_writes_agent_logs_and_trace_files(tmp_path: Path) -> None:
    settings.trace_dir = str(tmp_path / "traces")
    trace_writer.trace_dir = Path(settings.trace_dir)
    task_id = _upload_task(tmp_path)
    expected_exceptions = {
        flow_id: expected
        for flow_id, expected in EXPECTED_BRANCHES.items()
        if expected[2] == "PENDING_HUMAN"
    }

    assert agent_log_service.count_rows(user_id="demo_user", task_id=task_id) == len(
        expected_exceptions
    )
    assert agent_log_service.count_rows(user_id="other_user", task_id=task_id) == 0

    with get_engine().connect() as connection:
        rows = connection.execute(
            select(agent_execution_log_table).where(
                agent_execution_log_table.c.user_id == "demo_user",
                agent_execution_log_table.c.task_id == task_id,
            )
        ).mappings().all()

    assert {row["agent_name"] for row in rows} == {"AuditAgent"}
    assert {row["event_type"] for row in rows} == {"AUDIT_DECISION"}
    first_input = json.loads(rows[0]["input_payload"])
    first_output = json.loads(rows[0]["output_payload"])
    first_post_hooks = json.loads(rows[0]["post_hook_results"])
    assert first_input["rule_hit"]["exception_branch"] in {
        expected[1] for expected in expected_exceptions.values()
    }
    assert first_input["rag_hit"]["chunk_ids"]
    assert first_output["decision"] == "PENDING_HUMAN"
    assert first_output["ai_suggestion"] in {"PENDING_HUMAN", "APPROVED_MATCH", "FORCE_HOLD"}
    assert rows[0]["pre_hook_results"] is None
    assert set(first_post_hooks) == {"schema_retries", "constraint_violated", "decision_route"}
    assert isinstance(first_post_hooks["schema_retries"], int)
    assert isinstance(first_post_hooks["constraint_violated"], list)
    assert first_post_hooks["decision_route"] == "PENDING_HUMAN"

    trace_dir = Path(settings.trace_dir) / task_id
    trace_files = sorted(path.name for path in trace_dir.glob("*.json"))
    assert trace_files == sorted(f"{flow_id}.json" for flow_id in expected_exceptions)
    assert not (trace_dir / "F2001.json").exists()
    assert not (trace_dir / "F2002.json").exists()

    trace = json.loads((trace_dir / "F2003.json").read_text(encoding="utf-8"))
    assert trace["task_id"] == task_id
    assert trace["flow_id"] == "F2003"
    assert trace["user_id"] == "demo_user"
    assert trace["rule_hit"] == {
        "error_type": "AMOUNT_MISMATCH",
        "exception_branch": "BE-R002",
    }
    assert trace["rag_hit"]["chunk_ids"]
    assert trace["rag_hit"]["best_score"] is not None
    assert trace["agent_output"]["decision"] == "PENDING_HUMAN"
    assert trace["agent_output"]["risk_level"] == "MEDIUM"
    assert trace["agent_output"]["ai_suggestion"] == "PENDING_HUMAN"
    assert trace["agent_output"]["reason"]
    assert trace["agent_output"]["confidence"] > 0
    assert trace["created_at"]


def test_reupload_replaces_agent_logs_and_overwrites_trace_files(tmp_path: Path) -> None:
    settings.trace_dir = str(tmp_path / "traces")
    trace_writer.trace_dir = Path(settings.trace_dir)
    task_id = _upload_task(tmp_path)
    trace_file = Path(settings.trace_dir) / task_id / "F2003.json"
    trace_file.write_text('{"stale": true}', encoding="utf-8")

    reupload_task_id = _upload_task(tmp_path)

    assert reupload_task_id == task_id
    assert agent_log_service.count_rows(user_id="demo_user", task_id=task_id) == 6
    trace = json.loads(trace_file.read_text(encoding="utf-8"))
    assert trace["flow_id"] == "F2003"
    assert "stale" not in trace

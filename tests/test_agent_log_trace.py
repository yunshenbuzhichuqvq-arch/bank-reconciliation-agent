import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.services.agent_log import (
    agent_execution_log_table,
    agent_log_service,
)
from bank_reconciliation_agent.services.trace import TraceService
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
                    "mvp1_bank.xlsx",
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    "mvp1_clear.xlsx",
                    clear_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
    assert response.status_code == 200
    return response.json()["data"]["task_id"]


def test_upload_writes_agent_logs_and_trace_spans(tmp_path: Path) -> None:
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

    # Execution Trace is persisted to t_trace_span (DB), never local JSON files.
    trace_service = TraceService()
    runs = trace_service.list_runs(user_id="demo_user", task_id=task_id, flow_id="F2003")
    assert len(runs) >= 1
    assert trace_service.count_runs(user_id="demo_user", task_id=task_id, flow_id="F2001") == 0
    assert trace_service.count_runs(user_id="demo_user", task_id=task_id, flow_id="F2002") == 0

    spans = trace_service.get_spans(user_id="demo_user", task_id=task_id, flow_id="F2003")
    assert spans, "F2003 should have a persisted Trace"
    assert spans[0].span_type == "WORKFLOW"
    assert spans[0].sequence_no == 1
    assert [s.sequence_no for s in spans] == list(range(1, len(spans) + 1))
    span_types = {s.span_type for s in spans}
    assert "ROUTE" in span_types
    assert "TOOL" in span_types
    assert "AGENT" not in span_types
    rule_audit = next(s for s in spans if s.span_type == "ROUTE" and s.name == "RuleAudit")
    assert rule_audit.prompt_tokens is None
    assert rule_audit.completion_tokens is None
    # Exactly one terminal span, cross-user isolation.
    terminals = [s for s in spans if s.span_type in {"FINAL", "FALLBACK"}]
    assert len(terminals) == 1
    assert trace_service.count_runs(user_id="other_user", task_id=task_id, flow_id="F2003") == 0


def test_reupload_appends_trace_runs_and_replaces_agent_logs(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)
    trace_service = TraceService()
    runs_before = trace_service.count_runs(
        user_id="demo_user", task_id=task_id, flow_id="F2003"
    )
    assert runs_before >= 1

    reupload_task_id = _upload_task(tmp_path)

    assert reupload_task_id == task_id
    # Agent logs use replace semantics.
    assert agent_log_service.count_rows(user_id="demo_user", task_id=task_id) == 6
    # Append-only Trace: re-running the same flow adds a new run, keeping history.
    assert (
        trace_service.count_runs(user_id="demo_user", task_id=task_id, flow_id="F2003")
        == runs_before + 1
    )

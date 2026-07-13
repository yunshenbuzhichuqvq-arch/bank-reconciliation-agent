"""Tests for the tenant-scoped Trace Replay endpoint.

Covers: latest vs historical run selection, replay status matrix, tenant
isolation (task/flow/trace), token totals from Agent spans, and forbidden-field
exclusion (no ``user_id`` / internal ``id``).

Refs: TASK-29.4
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from bank_reconciliation_agent.core.security import create_access_token
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.schemas.trace import SpanStatus, SpanType, WorkflowOutcome
from bank_reconciliation_agent.services.queue import queue_service
from bank_reconciliation_agent.services.task import task_service
from bank_reconciliation_agent.services.trace import TraceRecorder, trace_service


client = TestClient(app)


def _headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _seed_task(user_id: str, task_id: str, *, status: str = "COMPLETED") -> None:
    task_service.replace_task(
        user_id=user_id,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
        status=status,
    )


def _seed_queue(user_id: str, task_id: str, flow_id: str) -> None:
    queue_service.replace_task_rows(
        user_id=user_id,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        rows=[
            {
                "task_id": task_id,
                "flow_id": flow_id,
                "bank_transaction_id": None,
                "clear_transaction_id": None,
                "error_type": "AMOUNT_MISMATCH",
                "exception_branch": "BE-R002",
                "status": "PENDING_HUMAN",
                "risk_level": "MEDIUM",
                "retry_count": 0,
            }
        ],
    )


def _persist_trace(
    user_id: str,
    task_id: str,
    flow_id: str,
    *,
    prompt_tokens: int = 100,
    completion_tokens: int = 40,
) -> str:
    recorder = TraceRecorder(user_id=user_id, task_id=task_id, flow_id=flow_id)
    with recorder.span(SpanType.ROUTE, "BE-R002"):
        pass
    recorder.record_tool(
        name="search_rules",
        status=SpanStatus.SUCCEEDED,
        outcome="RESULT",
        duration_ms=12,
        attempt=1,
        retry_recovered=False,
        recovered_error_type=None,
        result_count=1,
        evidence_ids=["rule-001"],
    )
    recorder.record_agent(
        name="AuditAgent",
        status=SpanStatus.SUCCEEDED,
        duration_ms=30,
        model_name="fake",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_calls=0,
    )
    recorder.close_root(
        status=SpanStatus.SUCCEEDED,
        outcome=WorkflowOutcome.PENDING_HUMAN,
        terminal_type=SpanType.FALLBACK,
    )
    spans = list(recorder.snapshot())
    assert trace_service.persist_snapshot(
        user_id=user_id, task_id=task_id, flow_id=flow_id, spans=spans
    )
    return recorder.trace_id


def _url(task_id: str, flow_id: str) -> str:
    return f"/api/v1/traces/{task_id}/flows/{flow_id}"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_replay_returns_latest_run_with_ordered_spans_and_tokens() -> None:
    user_id, task_id, flow_id = "replay_u1", "TASK_REPLAY_1", "FLOW_1"
    _seed_task(user_id, task_id)
    _seed_queue(user_id, task_id, flow_id)
    _persist_trace(user_id, task_id, flow_id, prompt_tokens=100, completion_tokens=40)

    resp = client.get(_url(task_id, flow_id), headers=_headers(user_id))
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["replay_status"] == "AVAILABLE"
    assert data["execution_count"] == 1
    assert data["selected_trace_id"]
    seqs = [s["sequence_no"] for s in data["spans"]]
    assert seqs == sorted(seqs)
    assert data["spans"][0]["span_type"] == "WORKFLOW"
    assert data["prompt_tokens"] == 100
    assert data["completion_tokens"] == 40
    assert data["total_tokens"] == 140

    # No forbidden fields leak.
    for span in data["spans"]:
        assert "user_id" not in span
        assert "id" not in span


def test_replay_selects_specific_historical_run() -> None:
    user_id, task_id, flow_id = "replay_u2", "TASK_REPLAY_2", "FLOW_1"
    _seed_task(user_id, task_id)
    _seed_queue(user_id, task_id, flow_id)
    first_trace = _persist_trace(user_id, task_id, flow_id)
    second_trace = _persist_trace(user_id, task_id, flow_id)
    assert first_trace != second_trace

    latest = client.get(_url(task_id, flow_id), headers=_headers(user_id)).json()["data"]
    assert latest["execution_count"] == 2
    assert latest["selected_trace_id"] == second_trace
    # Runs are most-recent first.
    assert latest["runs"][0]["trace_id"] == second_trace

    historical = client.get(
        _url(task_id, flow_id),
        headers=_headers(user_id),
        params={"trace_id": first_trace},
    ).json()["data"]
    assert historical["selected_trace_id"] == first_trace
    assert historical["execution_count"] == 2


# ---------------------------------------------------------------------------
# Status matrix
# ---------------------------------------------------------------------------


def test_replay_in_progress_when_task_running_without_trace() -> None:
    user_id, task_id, flow_id = "replay_u3", "TASK_REPLAY_3", "FLOW_1"
    _seed_task(user_id, task_id, status="RUNNING")
    _seed_queue(user_id, task_id, flow_id)

    resp = client.get(_url(task_id, flow_id), headers=_headers(user_id))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["replay_status"] == "IN_PROGRESS"
    assert data["spans"] == []
    assert data["selected_trace_id"] is None


def test_replay_not_available_when_task_finished_without_trace() -> None:
    user_id, task_id, flow_id = "replay_u4", "TASK_REPLAY_4", "FLOW_1"
    _seed_task(user_id, task_id, status="COMPLETED")
    _seed_queue(user_id, task_id, flow_id)

    resp = client.get(_url(task_id, flow_id), headers=_headers(user_id))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["replay_status"] == "TRACE_NOT_AVAILABLE"
    assert data["spans"] == []


# ---------------------------------------------------------------------------
# Tenant isolation and 404 matrix
# ---------------------------------------------------------------------------


def test_replay_unknown_task_returns_task_not_found() -> None:
    resp = client.get(_url("TASK_MISSING", "FLOW_X"), headers=_headers("replay_u5"))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "TASK_NOT_FOUND"


def test_replay_cross_user_task_returns_task_not_found() -> None:
    owner, other, task_id, flow_id = "owner_u", "intruder_u", "TASK_REPLAY_OWN", "FLOW_1"
    _seed_task(owner, task_id)
    _seed_queue(owner, task_id, flow_id)
    _persist_trace(owner, task_id, flow_id)

    resp = client.get(_url(task_id, flow_id), headers=_headers(other))
    assert resp.status_code == 404
    # Same 404 as a missing task -> no existence leak.
    assert resp.json()["detail"] == "TASK_NOT_FOUND"


def test_replay_unknown_flow_returns_trace_not_found() -> None:
    user_id, task_id = "replay_u6", "TASK_REPLAY_6"
    _seed_task(user_id, task_id)
    _seed_queue(user_id, task_id, "FLOW_REAL")

    resp = client.get(_url(task_id, "FLOW_GHOST"), headers=_headers(user_id))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "TRACE_NOT_FOUND"


def test_replay_unknown_trace_id_returns_trace_not_found() -> None:
    user_id, task_id, flow_id = "replay_u7", "TASK_REPLAY_7", "FLOW_1"
    _seed_task(user_id, task_id)
    _seed_queue(user_id, task_id, flow_id)
    _persist_trace(user_id, task_id, flow_id)

    resp = client.get(
        _url(task_id, flow_id),
        headers=_headers(user_id),
        params={"trace_id": "not-a-real-trace"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "TRACE_NOT_FOUND"


def test_replay_other_users_trace_id_returns_trace_not_found() -> None:
    owner, other = "own_t", "other_t"
    task_id, flow_id = "TASK_REPLAY_XU", "FLOW_1"
    _seed_task(owner, task_id)
    _seed_queue(owner, task_id, flow_id)
    owner_trace = _persist_trace(owner, task_id, flow_id)

    # Other user also owns a task with the same id/flow but different trace.
    _seed_task(other, task_id)
    _seed_queue(other, task_id, flow_id)
    _persist_trace(other, task_id, flow_id)

    # The other user cannot select the owner's trace_id.
    resp = client.get(
        _url(task_id, flow_id),
        headers=_headers(other),
        params={"trace_id": owner_trace},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "TRACE_NOT_FOUND"


def test_replay_requires_bearer_token() -> None:
    resp = client.get(_url("TASK_ANY", "FLOW_ANY"))
    assert resp.status_code == 401

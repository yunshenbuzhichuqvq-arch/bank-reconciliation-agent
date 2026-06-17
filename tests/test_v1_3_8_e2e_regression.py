import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

from bank_reconciliation_agent.api.v1 import reconcile as reconcile_api
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.services.live_registry import register, unregister
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from bank_reconciliation_agent.services.task import TaskService
from scripts.generate_mock_excel import (
    BANK_CLEARING_EXPECTED_BRANCHES,
    EXPECTED_BRANCHES,
    generate_mvp1_mock_excel,
    generate_mvp2a3_mock_excel,
)


client = TestClient(app)
DEMO_HEADERS = {"X-User-ID": "demo_user"}


@pytest.mark.parametrize(
    ("scenario_type", "generator", "expected_branches"),
    [
        ("BANK_ENTERPRISE", generate_mvp1_mock_excel, EXPECTED_BRANCHES),
        ("BANK_CLEARING", generate_mvp2a3_mock_excel, BANK_CLEARING_EXPECTED_BRANCHES),
    ],
)
def test_v1_3_8_sync_start_zero_regression_for_both_scenarios(
    tmp_path: Path,
    scenario_type: str,
    generator,
    expected_branches: dict[str, tuple[str, str, str]],
) -> None:
    bank_path, clear_path = generator(tmp_path)

    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        upload_response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
            data={"scenario_type": scenario_type},
            files={
                "bank_file": (
                    "bank.xlsx",
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    "clear.xlsx",
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
        for flow_id, branch in expected_branches.items()
        if branch[2] == "PENDING_HUMAN"
    }

    assert upload_body["status"] == "UPLOADED"
    assert upload_body["pending_human_rows"] == len(expected_pending)

    start_response = client.post(f"/api/v1/reconcile/{task_id}/start", headers=DEMO_HEADERS)
    assert start_response.status_code == 200
    assert start_response.json()["data"] == {"task_id": task_id, "status": "AI_RUNNING"}

    status_response = client.get(f"/api/v1/reconcile/{task_id}/status", headers=DEMO_HEADERS)
    assert status_response.status_code == 200
    status_body = status_response.json()["data"]
    assert status_body["status"] == "AI_RUNNING"
    assert status_body["pending_human_rows"] == len(expected_pending)
    assert status_body["unresolved_rows"] == len(expected_pending)

    exceptions_response = client.get(
        f"/api/v1/reconcile/{task_id}/exceptions",
        headers=DEMO_HEADERS,
    )
    assert exceptions_response.status_code == 200
    exceptions_body = exceptions_response.json()["data"]
    items_by_flow_id = {item["flow_id"]: item for item in exceptions_body["items"]}
    assert set(items_by_flow_id) == set(expected_pending)
    assert {item["exception_branch"] for item in items_by_flow_id.values()} == {
        branch[1] for branch in expected_pending.values()
    }

    persisted_task = TaskService().get(user_id="demo_user", task_id=task_id)
    assert persisted_task is not None
    assert persisted_task.scenario_type == scenario_type
    assert ReconciliationService().get_status(user_id="demo_user", task_id=task_id).status == (
        "AI_RUNNING"
    )


def test_v1_3_8_by_task_sse_yields_first_progress_before_done_and_workbench_stream_survives(
    tmp_path: Path,
) -> None:
    anyio.run(_assert_by_task_sse_yields_progress_before_done)

    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        stream_response = client.post(
            "/api/v1/reconcile/stream",
            headers=DEMO_HEADERS,
            files={
                "bank_file": (
                    "bank.xlsx",
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    "clear.xlsx",
                    clear_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )

    assert stream_response.status_code == 200
    workbench_events = [_event_from_frame(frame) for frame in stream_response.text.split("\n\n") if frame]
    assert workbench_events[0].event_type == StreamEventType.TASK_STARTED
    assert workbench_events[-1].event_type == StreamEventType.TASK_DONE
    assert workbench_events[-1].payload["status"] == "COMPLETED"


async def _assert_by_task_sse_yields_progress_before_done() -> None:
    task_id = "TASK_V1_3_8_REALTIME"
    emitter = register(task_id)
    terminal_emitted = asyncio.Event()
    try:
        response = await reconcile_api.stream_task_events(task_id=task_id, user_id="demo_user")

        async def produce_events() -> None:
            await asyncio.sleep(0.01)
            emitter.emit(_event(StreamEventType.TASK_PROGRESS, task_id, seq=1))
            await asyncio.sleep(0.05)
            emitter.emit(_event(StreamEventType.TASK_DONE, task_id, seq=2))
            terminal_emitted.set()

        producer = asyncio.create_task(produce_events())
        iterator = response.body_iterator

        first_frame = await asyncio.wait_for(anext(iterator), timeout=1)
        first_event = _event_from_frame(first_frame)

        assert first_event.event_type == StreamEventType.TASK_PROGRESS
        assert first_event.payload["processed"] == 1
        assert not terminal_emitted.is_set()

        async for _ in iterator:
            pass
        await producer
    finally:
        unregister(task_id)


def _event(event_type: StreamEventType, task_id: str, *, seq: int) -> AgentStreamEvent:
    payload = (
        {
            "processed": 1,
            "total": 2,
            "auto_fixed": 0,
            "pending_ai": 0,
            "pending_human": 1,
            "unresolved": 1,
            "exception_dist": {"AMOUNT_MISMATCH": 1},
        }
        if event_type == StreamEventType.TASK_PROGRESS
        else {"status": "COMPLETED"}
    )
    return AgentStreamEvent(
        event_type=event_type,
        seq=seq,
        task_id=task_id,
        ts=datetime(2026, 6, 16, 10, 30, tzinfo=UTC),
        payload=payload,
    )


def _event_from_frame(frame: str) -> AgentStreamEvent:
    assert frame.startswith("data: ")
    return AgentStreamEvent.model_validate(json.loads(frame.removeprefix("data: ")))

import asyncio
import json
from datetime import UTC, datetime

import anyio
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from bank_reconciliation_agent.api.v1 import reconcile as reconcile_api
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.services.live_registry import get_emitter, register, unregister
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from bank_reconciliation_agent.services.task import task_service


client = TestClient(app)
DEMO_HEADERS = {"X-User-ID": "demo_user"}


def test_start_live_endpoint_starts_background_driver() -> None:
    task_id = "TASK_V1_3_3_START_LIVE"
    task_service.replace_task(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )

    response = client.post(f"/api/v1/reconcile/{task_id}/start-live", headers=DEMO_HEADERS)

    assert response.status_code == 200
    assert response.json()["data"] == {"task_id": task_id, "status": "AI_RUNNING"}


def test_events_endpoint_rejects_unknown_or_unregistered_task_id() -> None:
    async def run_case() -> None:
        with pytest.raises(HTTPException) as exc_info:
            await reconcile_api.stream_task_events(task_id="NO_SUCH_TASK", user_id="demo_user")

        assert exc_info.value.status_code == 404

    anyio.run(run_case)


def test_events_endpoint_streams_registered_live_emitter_without_db_replay() -> None:
    async def run_case() -> None:
        task_id = "TASK_V1_3_3_EVENTS"
        emitter = register(task_id)
        emitter.emit(_event(StreamEventType.TASK_PROGRESS, task_id, seq=1))
        emitter.emit(_event(StreamEventType.TASK_DONE, task_id, seq=2))

        response = await reconcile_api.stream_task_events(task_id=task_id, user_id="demo_user")
        frames = [frame async for frame in response.body_iterator]

        events = [_event_from_frame(frame) for frame in frames]
        assert [event.event_type for event in events] == [
            StreamEventType.TASK_PROGRESS,
            StreamEventType.TASK_DONE,
        ]
        assert events[0].payload["processed"] == 1
        assert get_emitter(task_id) is None

    anyio.run(run_case)


def test_events_endpoint_yields_progress_before_task_done_is_emitted() -> None:
    async def run_case() -> None:
        task_id = "TASK_V1_3_3_TIMING"
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
            assert not terminal_emitted.is_set()

            async for _ in iterator:
                pass
            await producer
        finally:
            unregister(task_id)

    anyio.run(run_case)


@pytest.mark.anyio
async def test_events_after_background_finished_does_not_404() -> None:
    task_id = "TASK_V1_3_3_EVENTS_AFTER_FINISHED"
    user_id = "demo_user"
    task_service.replace_task(
        user_id=user_id,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )

    service = ReconciliationService()
    await service.start_live(user_id=user_id, task_id=task_id)

    async with asyncio.timeout(1):
        while service.get_status(user_id=user_id, task_id=task_id).status != "COMPLETED":
            await asyncio.sleep(0.01)

    response = await reconcile_api.stream_task_events(task_id=task_id, user_id=user_id)
    frames = [frame async for frame in response.body_iterator]
    events = [_event_from_frame(frame) for frame in frames]

    assert [event.event_type for event in events] == [
        StreamEventType.TASK_PROGRESS,
        StreamEventType.TASK_DONE,
    ]


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

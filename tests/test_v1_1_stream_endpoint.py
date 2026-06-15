import json
import asyncio
import threading
from types import SimpleNamespace
from pathlib import Path

import anyio
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from bank_reconciliation_agent.api.v1 import stream as stream_api
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.services.stream_emitter import QueueEmitter
from scripts.generate_mock_excel import generate_mvp1_mock_excel


client = TestClient(app)
DEMO_HEADERS = {"X-User-ID": "demo_user"}


def test_stream_reconcile_returns_ordered_sse_events(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)

    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/stream",
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
    assert response.headers["content-type"].startswith("text/event-stream")

    frames = [frame for frame in response.text.split("\n\n") if frame]
    assert frames
    assert all(frame.startswith("data: ") for frame in frames)

    events = [
        AgentStreamEvent.model_validate(json.loads(frame.removeprefix("data: ")))
        for frame in frames
    ]
    assert [event.seq for event in events] == sorted(event.seq for event in events)
    assert len({event.seq for event in events}) == len(events)
    assert events[-1].event_type == StreamEventType.TASK_DONE
    assert events[-1].payload["status"] == "COMPLETED"


def test_stream_reconcile_returns_before_upload_finishes(monkeypatch) -> None:
    async def run_case() -> None:
        await _assert_stream_reconcile_returns_before_upload_finishes(monkeypatch)

    anyio.run(run_case)


async def _assert_stream_reconcile_returns_before_upload_finishes(monkeypatch) -> None:
    upload_started = threading.Event()
    allow_upload_done = threading.Event()

    async def slow_upload(**kwargs):
        del kwargs
        upload_started.set()
        while not allow_upload_done.is_set():
            await asyncio.sleep(0.01)
        return SimpleNamespace(
            task_id="TASK_REALTIME",
            total_bank_rows=1,
            total_clear_rows=1,
            auto_fixed_rows=0,
            pending_ai_rows=0,
            pending_human_rows=1,
        )

    monkeypatch.setattr(stream_api.reconciliation_service, "upload", slow_upload)

    with Path(__file__).open("rb") as bank_file, Path(__file__).open("rb") as clear_file:
        response_task = asyncio.create_task(
            stream_api.stream_reconcile(
                bank_file=UploadFile(filename="bank.xlsx", file=bank_file),
                clear_file=UploadFile(filename="clear.xlsx", file=clear_file),
                user_id="demo_user",
                scenario_type="BANK_ENTERPRISE",
            )
        )
        assert await asyncio.to_thread(upload_started.wait, 1)

        response = await asyncio.wait_for(response_task, timeout=1)
        first_frame = await anext(response.body_iterator)
        first_event = AgentStreamEvent.model_validate_json(first_frame.removeprefix("data: "))

        assert first_event.event_type == StreamEventType.TASK_STARTED
        assert not allow_upload_done.is_set()

        allow_upload_done.set()
        async for _ in response.body_iterator:
            pass


def test_event_frames_preserve_workflow_event_sequence_numbers() -> None:
    async def run_case() -> None:
        emitter = QueueEmitter()
        emitter.emit(
            AgentStreamEvent(
                event_type=StreamEventType.RAG_RETRIEVED,
                seq=1,
                task_id="TASK_SEQ",
                ts=stream_api.datetime.now(stream_api.timezone.utc),
                payload={"chunk_ids": ["rule-001"], "best_score": 0.9, "query": "q"},
            )
        )
        upload_task = asyncio.create_task(_fake_upload_result())

        frames = [
            frame
            async for frame in stream_api._event_frames(
                scenario_type="BANK_ENTERPRISE",
                emitter=emitter,
                upload_task=upload_task,
            )
        ]
        events = [
            AgentStreamEvent.model_validate_json(frame.removeprefix("data: "))
            for frame in frames
        ]

        assert [event.seq for event in events] == [0, 1, 2]
        assert events[1].event_type == StreamEventType.RAG_RETRIEVED

    anyio.run(run_case)


async def _fake_upload_result():
    return SimpleNamespace(
        task_id="TASK_SEQ",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )

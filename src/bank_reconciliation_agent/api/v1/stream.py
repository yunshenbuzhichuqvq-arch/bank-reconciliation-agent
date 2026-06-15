from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import datetime, timezone
from queue import Empty
from typing import Any

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from bank_reconciliation_agent.api.dependencies import CurrentUserId
from bank_reconciliation_agent.api.v1.reconcile import VALID_SCENARIO_TYPES
from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.services.reconciliation import reconciliation_service
from bank_reconciliation_agent.services.stream_emitter import QueueEmitter


router = APIRouter()


@router.post("/stream")
async def stream_reconcile(
    bank_file: UploadFile,
    clear_file: UploadFile,
    user_id: CurrentUserId,
    scenario_type: str = Form("BANK_ENTERPRISE"),
) -> StreamingResponse:
    if scenario_type not in VALID_SCENARIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail="scenario_type must be one of: BANK_ENTERPRISE, BANK_CLEARING",
        )

    emitter = QueueEmitter()
    upload_task = asyncio.create_task(
        _run_upload(
            user_id=user_id,
            scenario_type=scenario_type,
            bank_file=bank_file,
            clear_file=clear_file,
            emitter=emitter,
        )
    )

    return StreamingResponse(
        _event_frames(
            scenario_type=scenario_type,
            emitter=emitter,
            upload_task=upload_task,
        ),
        media_type="text/event-stream",
    )


async def _run_upload(
    *,
    user_id: str,
    scenario_type: str,
    bank_file: UploadFile,
    clear_file: UploadFile,
    emitter: QueueEmitter,
) -> Any:
    return await asyncio.to_thread(
        lambda: asyncio.run(
            reconciliation_service.upload(
                user_id=user_id,
                scenario_type=scenario_type,
                bank_file=bank_file,
                clear_file=clear_file,
                emitter=emitter,
            )
        )
    )


async def _event_frames(
    *,
    scenario_type: str,
    emitter: QueueEmitter,
    upload_task: asyncio.Task[Any],
) -> AsyncIterator[str]:
    last_seq = 0
    try:
        yield _to_sse_frame(
            _build_event(
                event_type=StreamEventType.TASK_STARTED,
                seq=last_seq,
                task_id="PENDING",
                payload={"scenario_type": scenario_type},
            )
        )

        while not upload_task.done():
            try:
                event = await asyncio.to_thread(emitter.get, 0.1)
            except Empty:
                continue
            last_seq = event.seq
            yield _to_sse_frame(event)

        for event in emitter.drain():
            last_seq = event.seq
            yield _to_sse_frame(event)

        result = await upload_task
        yield _to_sse_frame(
            _build_event(
                event_type=StreamEventType.TASK_DONE,
                seq=last_seq + 1,
                task_id=result.task_id,
                payload={
                    "status": "COMPLETED",
                    "total_bank_rows": result.total_bank_rows,
                    "total_clear_rows": result.total_clear_rows,
                    "auto_fixed_rows": result.auto_fixed_rows,
                    "pending_ai_rows": result.pending_ai_rows,
                    "pending_human_rows": result.pending_human_rows,
                },
            )
        )
    except asyncio.CancelledError:
        upload_task.cancel()
        with suppress(asyncio.CancelledError):
            await upload_task
        raise
    except Exception as exc:
        upload_task.cancel()
        yield _to_sse_frame(
            _build_event(
                event_type=StreamEventType.TASK_DONE,
                seq=last_seq + 1,
                task_id="FAILED",
                payload={"status": "FAILED", "error_message": str(exc)},
            )
        )


def _build_event(
    *,
    event_type: StreamEventType,
    seq: int,
    task_id: str,
    payload: dict[str, Any],
) -> AgentStreamEvent:
    return AgentStreamEvent(
        event_type=event_type,
        seq=seq,
        task_id=task_id,
        ts=datetime.now(timezone.utc),
        payload=payload,
    )


def _to_sse_frame(event: AgentStreamEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"

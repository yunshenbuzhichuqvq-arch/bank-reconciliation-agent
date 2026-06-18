from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from queue import Empty

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from bank_reconciliation_agent.api.dependencies import CurrentUserId
from bank_reconciliation_agent.schemas.common import ApiResponse
from bank_reconciliation_agent.schemas.reconciliation import (
    ReconciliationExceptionListResponse,
    ReconciliationStartResponse,
    ReconciliationStatusResponse,
    ReconciliationUploadResponse,
)
from bank_reconciliation_agent.schemas.report import TaskReport
from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.services.live_registry import get_emitter, unregister
from bank_reconciliation_agent.services.reconciliation import reconciliation_service
from bank_reconciliation_agent.services.report import build_report


router = APIRouter()

VALID_SCENARIO_TYPES = {"BANK_ENTERPRISE", "BANK_CLEARING"}


@router.post("/upload", response_model=ApiResponse[ReconciliationUploadResponse])
async def upload_reconciliation_files(
    bank_file: UploadFile,
    clear_file: UploadFile,
    user_id: CurrentUserId,
    scenario_type: str = Form("BANK_ENTERPRISE"),
) -> ApiResponse[ReconciliationUploadResponse]:
    """上传银行端和清算端 Excel，对文件进行解析和字段校验。"""
    if scenario_type not in VALID_SCENARIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail="scenario_type must be one of: BANK_ENTERPRISE, BANK_CLEARING",
        )
    result = await reconciliation_service.upload(
        user_id=user_id,
        scenario_type=scenario_type,
        bank_file=bank_file,
        clear_file=clear_file,
    )
    return ApiResponse(message="upload success", data=result)


@router.post("/{task_id}/start", response_model=ApiResponse[ReconciliationStartResponse])
async def start_reconciliation(
    task_id: str,
    user_id: CurrentUserId,
) -> ApiResponse[ReconciliationStartResponse]:
    """启动指定对账任务的后续处理流程。"""
    result = reconciliation_service.start(user_id=user_id, task_id=task_id)
    return ApiResponse(message="workflow started", data=result)


@router.post("/{task_id}/start-live", response_model=ApiResponse[ReconciliationStartResponse])
async def start_reconciliation_live(
    task_id: str,
    user_id: CurrentUserId,
) -> ApiResponse[ReconciliationStartResponse]:
    """启动实时对账任务，供 by-taskId SSE 订阅。"""
    result = await reconciliation_service.start_live(user_id=user_id, task_id=task_id)
    return ApiResponse(message="live workflow started", data=result)


@router.get("/{task_id}/events")
async def stream_task_events(
    task_id: str,
    user_id: CurrentUserId,
) -> StreamingResponse:
    """按 task_id 订阅实时事件；仅使用 live emitter，不做 DB 回放。"""
    del user_id
    emitter = get_emitter(task_id)
    if emitter is None:
        raise HTTPException(status_code=404, detail="live event stream not found")
    return StreamingResponse(_task_event_frames(task_id, emitter), media_type="text/event-stream")


@router.get("/{task_id}/status", response_model=ApiResponse[ReconciliationStatusResponse])
async def get_reconciliation_status(
    task_id: str,
    user_id: CurrentUserId,
) -> ApiResponse[ReconciliationStatusResponse]:
    """查询指定对账任务的当前状态和统计结果。"""
    result = reconciliation_service.get_status(user_id=user_id, task_id=task_id)
    return ApiResponse(data=result)


@router.get("/{task_id}/exceptions", response_model=ApiResponse[ReconciliationExceptionListResponse])
async def list_reconciliation_exceptions(
    task_id: str,
    user_id: CurrentUserId,
) -> ApiResponse[ReconciliationExceptionListResponse]:
    """查询指定对账任务的基础异常明细。"""
    result = reconciliation_service.get_exceptions(user_id=user_id, task_id=task_id)
    return ApiResponse(data=result)


@router.get("/{task_id}/report", response_model=ApiResponse[TaskReport])
async def get_reconciliation_report(
    task_id: str,
    user_id: CurrentUserId,
) -> ApiResponse[TaskReport]:
    """按需生成指定对账任务的审计报告。"""
    try:
        result = build_report(user_id=user_id, task_id=task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="reconciliation task not found") from exc
    return ApiResponse(data=result)


async def _task_event_frames(task_id: str, emitter) -> AsyncIterator[str]:
    try:
        while True:
            events = emitter.drain()
            if not events:
                if emitter.finished:
                    return
                try:
                    events = [await asyncio.to_thread(emitter.get, 0.1)]
                except Empty:
                    continue
            for event in events:
                yield _to_sse_frame(event)
                if event.event_type == StreamEventType.TASK_DONE:
                    return
    finally:
        unregister(task_id)


def _to_sse_frame(event: AgentStreamEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"

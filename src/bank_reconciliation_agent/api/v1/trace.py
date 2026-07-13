from fastapi import APIRouter, HTTPException

from bank_reconciliation_agent.api.dependencies import CurrentUserId
from bank_reconciliation_agent.schemas.common import ApiResponse, ErrorCode
from bank_reconciliation_agent.schemas.trace import (
    ReplayStatus,
    TraceReplayData,
    TraceRunSummary,
    TraceSpan,
    TraceSpanView,
    SpanType,
)
from bank_reconciliation_agent.services.ledger import ledger_service
from bank_reconciliation_agent.services.queue import queue_service
from bank_reconciliation_agent.services.task import task_service
from bank_reconciliation_agent.services.trace import trace_service


router = APIRouter()

# Task statuses that mean the task is still being processed. Anything else is
# treated as ended, so a missing Trace is reported as TRACE_NOT_AVAILABLE rather
# than IN_PROGRESS.
_IN_PROGRESS_STATUSES = {"QUEUED", "RUNNING", "AI_RUNNING"}


@router.get(
    "/{task_id}/flows/{flow_id}",
    response_model=ApiResponse[TraceReplayData],
)
async def get_trace_replay(
    user_id: CurrentUserId,
    task_id: str,
    flow_id: str,
    trace_id: str | None = None,
) -> ApiResponse[TraceReplayData]:
    """Return the read-only execution Trace for a tenant's task/flow.

    Ownership is verified strictly in order: JWT user -> task -> flow ->
    optional trace. Cross-user and missing resources return identical 404s so
    existence, span metadata, errors and evidence never leak.
    """
    # 1. Task ownership (missing or cross-user share the same 404).
    task = task_service.get(user_id=user_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=ErrorCode.TASK_NOT_FOUND.value)

    # 2. Flow ownership within the task.
    if not _flow_belongs_to_task(user_id=user_id, task_id=task_id, flow_id=flow_id):
        raise HTTPException(status_code=404, detail=ErrorCode.TRACE_NOT_FOUND.value)

    runs = trace_service.list_runs(user_id=user_id, task_id=task_id, flow_id=flow_id)
    execution_count = len(runs)
    run_summaries = [
        TraceRunSummary(
            trace_id=str(r["trace_id"]),
            started_at=_as_utc(r["started_at"]),
            status=str(r["status"]),
            outcome=r.get("outcome"),
        )
        for r in runs
    ]

    # No persisted Trace for a legitimate task/flow.
    if execution_count == 0:
        status = (
            ReplayStatus.IN_PROGRESS
            if task.status in _IN_PROGRESS_STATUSES
            else ReplayStatus.TRACE_NOT_AVAILABLE
        )
        return ApiResponse(
            data=TraceReplayData(
                replay_status=status,
                selected_trace_id=None,
                execution_count=0,
                runs=[],
                spans=[],
            )
        )

    # 3. Optional trace ownership; unknown or out-of-scope trace is TRACE_NOT_FOUND.
    if trace_id is not None and trace_id not in {r.trace_id for r in run_summaries}:
        raise HTTPException(status_code=404, detail=ErrorCode.TRACE_NOT_FOUND.value)

    spans = trace_service.get_spans(
        user_id=user_id,
        task_id=task_id,
        flow_id=flow_id,
        trace_id=trace_id,
    )
    selected_trace_id = spans[0].trace_id if spans else (trace_id or run_summaries[0].trace_id)
    span_views = [TraceSpanView.from_span(span) for span in spans]
    prompt_tokens, completion_tokens = _sum_agent_tokens(spans)

    return ApiResponse(
        data=TraceReplayData(
            replay_status=ReplayStatus.AVAILABLE,
            selected_trace_id=selected_trace_id,
            execution_count=execution_count,
            runs=run_summaries,
            spans=span_views,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
    )


def _flow_belongs_to_task(*, user_id: str, task_id: str, flow_id: str) -> bool:
    if queue_service.get_row(user_id=user_id, task_id=task_id, flow_id=flow_id) is not None:
        return True
    if trace_service.count_runs(user_id=user_id, task_id=task_id, flow_id=flow_id) > 0:
        return True
    return _flow_in_ledger(user_id=user_id, task_id=task_id, flow_id=flow_id)


def _flow_in_ledger(*, user_id: str, task_id: str, flow_id: str) -> bool:
    from bank_reconciliation_agent.schemas.ledger import LedgerQuery

    page = ledger_service.list(
        user_id=user_id,
        query=LedgerQuery(task_id=task_id, page=1, page_size=10_000),
    )
    return any(row.flow_id == flow_id for row in page.items)


def _sum_agent_tokens(spans: list[TraceSpan]) -> tuple[int, int]:
    prompt = sum(s.prompt_tokens or 0 for s in spans if s.span_type == SpanType.AGENT)
    completion = sum(s.completion_tokens or 0 for s in spans if s.span_type == SpanType.AGENT)
    return prompt, completion


def _as_utc(value: object) -> object:
    from datetime import datetime, timezone

    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

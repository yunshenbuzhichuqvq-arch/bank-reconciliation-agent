from __future__ import annotations

from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any, Protocol

from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.schemas.trace import TraceSpanView


class StreamEmitter(Protocol):
    def emit(self, event: AgentStreamEvent) -> None: ...


class NullEmitter:
    def emit(self, event: AgentStreamEvent) -> None:
        del event


class QueueEmitter:
    def __init__(self, *, created_at: float | None = None) -> None:
        self._queue: Queue[AgentStreamEvent] = Queue()
        self.created_at = created_at
        self.finished_at: float | None = None

    @property
    def finished(self) -> bool:
        return self.finished_at is not None

    def mark_finished(self, *, finished_at: float) -> None:
        self.finished_at = finished_at

    def emit(self, event: AgentStreamEvent) -> None:
        self._queue.put(event)

    def get(self, timeout: float | None = None) -> AgentStreamEvent:
        return self._queue.get(timeout=timeout)

    def drain(self) -> list[AgentStreamEvent]:
        events: list[AgentStreamEvent] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except Empty:
                return events


def to_stream_event(
    row: dict[str, Any],
    *,
    seq: int,
    task_id: str,
    event_type: StreamEventType | None = None,
) -> AgentStreamEvent:
    flow_id = row.get("flow_id")
    return AgentStreamEvent(
        event_type=event_type or _event_type_from_row(row),
        seq=seq,
        task_id=task_id,
        flow_id=str(flow_id) if flow_id is not None else None,
        ts=datetime.now(timezone.utc),
        payload=_payload_from_row(row),
    )


def _event_type_from_row(row: dict[str, Any]) -> StreamEventType:
    agent_name = str(row.get("agent_name") or "")
    step = str(row.get("step") or row.get("event_type") or "")
    if agent_name.endswith("Hook") or "hook" in step.lower():
        return StreamEventType.HOOK
    if "fallback" in step.lower() or int(row.get("fallback_level") or 0) > 1:
        return StreamEventType.FALLBACK
    return StreamEventType.AGENT_DECISION


def _payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in (
        "agent_name",
        "step",
        "decision",
        "confidence",
        "fallback_level",
        "few_shot_rows",
        "prompt_version",
        "prompt_tokens",
        "completion_tokens",
        "llm_tokens",
        "transport_attempts",
        "retry_recovered",
        "structured_repair_attempted",
        "structured_repair_succeeded",
        "cached_calls",
        "final_failure_type",
        "fallback_reason",
        "retry_count",
        "error_message",
        "next_action",
        "violated",
        "hook_name",
        "breaker_state",
        "reason",
        "query",
    ):
        if key in row and row[key] is not None:
            payload[key] = row[key]
    if "output" in row:
        payload["output"] = row["output"]
    if "output_payload" in row and isinstance(row["output_payload"], dict):
        payload.update(row["output_payload"])
    if "input_payload" in row and isinstance(row["input_payload"], dict):
        payload["input"] = row["input_payload"]
    return payload


def to_trace_span_event(
    span_view: TraceSpanView,
    *,
    seq: int,
) -> AgentStreamEvent:
    """Build a ``trace_span`` SSE event from a canonical safe projection.

    The event reuses the same ``trace_id`` / ``span_id`` / ``sequence_no`` as the
    persisted Trace, so consumers can join real-time and replay data.
    """
    return AgentStreamEvent(
        event_type=StreamEventType.TRACE_SPAN,
        seq=seq,
        task_id=span_view.task_id,
        flow_id=span_view.flow_id,
        ts=datetime.now(timezone.utc),
        payload=span_view.model_dump(mode="json"),
    )

from decimal import Decimal

from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.schemas.trace import TraceSpanView, SpanType, SpanStatus
from bank_reconciliation_agent.services.exception_router import BranchResult
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from bank_reconciliation_agent.services.stream_emitter import QueueEmitter, to_trace_span_event
from bank_reconciliation_agent.services.workflow import run_item

from tests.test_workflow import (
    SpyAuditAgent,
    SpyExtractionAgent,
    SpyTraceAgent,
    StaticRetriever,
    _state,
)
from tests.tool_workflow_helpers import RetrieverBackedToolExecutor


def test_run_item_emits_ordered_agent_stream_events() -> None:
    emitter = QueueEmitter()

    result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        tool_executor=RetrieverBackedToolExecutor(retriever=StaticRetriever()),
        emitter=emitter,
    )

    events = emitter.drain()

    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    assert {event.event_type for event in events} >= {
        StreamEventType.RAG_RETRIEVED,
        StreamEventType.AGENT_DECISION,
    }
    assert all(AgentStreamEvent.model_validate(event.model_dump()) for event in events)
    assert events[-1].payload["decision"] == result["audit_decision"]["decision"]


def test_run_item_default_emitter_does_not_reuse_null_emitter_instance() -> None:
    assert run_item.__kwdefaults__["emitter"] is None


def test_reconciliation_service_passes_emitter_to_workflow(monkeypatch) -> None:
    service = ReconciliationService()
    emitter = QueueEmitter()
    captured_emitters: list[QueueEmitter] = []

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.transaction_service.get_bank_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "银行流水"},
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.transaction_service.get_clear_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "清算流水"},
    )

    def fake_run_item(state, *, emitter):
        captured_emitters.append(emitter)
        return state

    monkeypatch.setattr("bank_reconciliation_agent.services.reconciliation.run_item", fake_run_item)

    branch_result = BranchResult(
        flow_id="FLOW-STREAM",
        action="EXCEPTION",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount=Decimal("100.00"),
        clear_amount=Decimal("99.00"),
        amount_diff=Decimal("1.00"),
    )

    service._run_workflow_for_result(
        user_id="demo_user",
        task_id="TASK-STREAM",
        scenario_type="BANK_ENTERPRISE",
        result=service._to_match_result(branch_result),
        rag_query="AMOUNT_MISMATCH BE-R002",
        emitter=emitter,
    )

    assert captured_emitters == [emitter]


def test_to_trace_span_event_uses_same_identity_as_persistence() -> None:
    from datetime import datetime, timezone

    view = TraceSpanView(
        trace_id="trace-abc",
        span_id="span-123",
        parent_span_id=None,
        task_id="TASK-SSE",
        flow_id="FLOW-SSE",
        sequence_no=2,
        span_type=SpanType.TOOL,
        name="search_rules",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        duration_ms=15,
        status=SpanStatus.SUCCEEDED,
        outcome="RESULT",
        attempt=1,
        result_count=3,
        evidence_ids=["chunk-1"],
    )
    event = to_trace_span_event(view, seq=42)

    assert event.schema_version == "1.2"
    assert event.event_type == StreamEventType.TRACE_SPAN
    assert event.task_id == "TASK-SSE"
    assert event.flow_id == "FLOW-SSE"
    assert event.seq == 42
    assert event.payload["trace_id"] == "trace-abc"
    assert event.payload["span_id"] == "span-123"
    assert event.payload["sequence_no"] == 2
    assert event.payload["span_type"] == "TOOL"
    assert event.payload["name"] == "search_rules"
    assert event.payload["duration_ms"] == 15
    assert "user_id" not in event.payload


def test_to_trace_span_event_has_all_canonical_fields() -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    view = TraceSpanView(
        trace_id="trace-canon",
        span_id="span-canon",
        parent_span_id=None,
        task_id="TASK-CANON",
        flow_id="FLOW-CANON",
        sequence_no=3,
        span_type=SpanType.TOOL,
        name="search_rules",
        started_at=now,
        ended_at=now,
        duration_ms=15,
        status=SpanStatus.SUCCEEDED,
        outcome="RESULT",
        attempt=2,
        retry_recovered=True,
        recovered_error_type="TIMEOUT",
        result_count=5,
        evidence_ids=["chunk-1"],
    )
    event = to_trace_span_event(view, seq=42)
    payload = event.payload

    required_fields = {
        "schema_version",
        "trace_id",
        "span_id",
        "task_id",
        "flow_id",
        "sequence_no",
        "span_type",
        "name",
        "started_at",
        "ended_at",
        "duration_ms",
        "status",
    }
    for field in required_fields:
        assert field in payload, f"Missing canonical field: {field}"

    assert payload["trace_id"] == "trace-canon"
    assert payload["span_id"] == "span-canon"
    assert payload["span_type"] == "TOOL"
    assert payload["sequence_no"] == 3
    assert payload["attempt"] == 2
    assert payload["retry_recovered"] is True
    assert payload["result_count"] == 5
    assert payload["evidence_ids"] == ["chunk-1"]
    assert "user_id" not in payload


def test_to_trace_span_event_no_forbidden_fields() -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    view = TraceSpanView(
        trace_id="trace-safe",
        span_id="span-safe",
        parent_span_id=None,
        task_id="TASK-SAFE",
        flow_id="FLOW-SAFE",
        sequence_no=1,
        span_type=SpanType.WORKFLOW,
        name="workflow",
        started_at=now,
        ended_at=now,
        duration_ms=100,
        status=SpanStatus.SUCCEEDED,
        outcome="AUTO_FIXED",
    )
    event = to_trace_span_event(view, seq=1)
    dumped = event.model_dump()

    assert "user_id" not in dumped["payload"]
    assert "id" not in dumped["payload"]
    assert "user_id" not in event.model_dump_json()


def test_run_item_trace_span_fields_present_in_sse(monkeypatch) -> None:
    from bank_reconciliation_agent.services.trace import TraceRecorder

    emitter = QueueEmitter()
    recorded_events: list = []

    orig_emit = emitter.emit

    def capture(event):
        recorded_events.append(event)
        return orig_emit(event)

    monkeypatch.setattr(emitter, "emit", capture)

    recorder = TraceRecorder(user_id="demo_user", task_id="TASK-WF-001", flow_id="FLOW-BE-R002")
    state = _state("BE-R002")
    state["recorder"] = recorder

    run_item(
        state,
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        tool_executor=RetrieverBackedToolExecutor(retriever=StaticRetriever()),
        emitter=emitter,
    )

    trace_span_events = [e for e in recorded_events if e.event_type == StreamEventType.TRACE_SPAN]
    assert len(trace_span_events) >= 1

    for event in trace_span_events:
        p = event.payload
        assert "trace_id" in p
        assert "span_id" in p
        assert "sequence_no" in p
        assert "span_type" in p
        assert "name" in p
        assert "started_at" in p
        assert "ended_at" in p
        assert "duration_ms" in p
        assert "status" in p
        assert "user_id" not in p

    span_types_emitted = {e.payload["span_type"] for e in trace_span_events}
    assert span_types_emitted >= {"ROUTE", "TOOL", "AGENT", "GUARD"}

    type_counts = {}
    for e in trace_span_events:
        t = e.payload["span_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    for count in type_counts.values():
        assert count == 1, f"Span type emitted more than once: {type_counts}"


def test_trace_span_emit_failure_isolated() -> None:
    """Verify _emit_trace_span does not raise on emitter failure."""
    from unittest.mock import MagicMock

    from bank_reconciliation_agent.services.trace import TraceRecorder

    emitter = MagicMock()
    emitter.emit.side_effect = RuntimeError("emit broken")

    recorder = TraceRecorder(user_id="demo_user", task_id="TASK-FAIL", flow_id="FLOW-FAIL")
    with recorder.span(SpanType.ROUTE, "BE-R002"):
        pass

    state = {
        "task_id": "TASK-FAIL",
        "user_id": "demo_user",
        "thread_id": "THREAD",
        "scenario_type": "BANK_ENTERPRISE",
        "current_queue_id": None,
        "source_a_item": {"flow_id": "FLOW-FAIL"},
        "source_b_item": {"flow_id": "FLOW-FAIL"},
        "error_type": "AMOUNT_MISMATCH",
        "exception_branch": "BE-R002",
        "math_result": {},
        "extraction_result": {},
        "rag_context": [],
        "audit_decision": {},
        "confidence": None,
        "retry_count": 0,
        "fallback_level": 0,
        "next_action": "",
        "error_message": None,
        "agent_logs": [],
        "stream_seq": 0,
        "recorder": recorder,
    }

    from bank_reconciliation_agent.services.workflow import _emit_trace_span

    try:
        _emit_trace_span(state, recorder, emitter)
    except Exception as exc:
        raise AssertionError(
            f"_emit_trace_span should not raise, but got {type(exc).__name__}"
        ) from exc

    emitter.emit.assert_called_once()
    assert state["stream_seq"] == 1

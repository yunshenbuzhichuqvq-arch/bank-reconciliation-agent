import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine

from bank_reconciliation_agent.schemas.ledger import LedgerQuery
from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.schemas.trace import TraceSpanView, SpanType, SpanStatus
from bank_reconciliation_agent.services.exception_router import BranchResult
from bank_reconciliation_agent.services.ledger import ledger_service
from bank_reconciliation_agent.services.queue import queue_service
from bank_reconciliation_agent.services.reconciliation import (
    ReconciliationMatchResult,
    ReconciliationService,
)
from bank_reconciliation_agent.services.stream_emitter import QueueEmitter, to_trace_span_event
from bank_reconciliation_agent.services.task import task_service
from bank_reconciliation_agent.services.trace import (
    TraceService,
    trace_service as global_trace_service,
)
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
        "bank_reconciliation_agent.services.reconciliation.service.transaction_service.get_bank_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "银行流水"},
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.service.transaction_service.get_clear_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "清算流水"},
    )

    def fake_run_item(state, *, emitter):
        captured_emitters.append(emitter)
        return state

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.service.run_item", fake_run_item
    )

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
    assert span_types_emitted >= {"ROUTE", "TOOL", "GUARD"}
    assert "AGENT" not in span_types_emitted
    rule_audit = next(
        event for event in trace_span_events if event.payload["name"] == "RuleAudit"
    )
    assert rule_audit.payload.get("prompt_tokens") is None
    assert rule_audit.payload.get("completion_tokens") is None

    type_counts = {}
    for e in trace_span_events:
        t = e.payload["span_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    assert type_counts["ROUTE"] == 2
    assert type_counts["TOOL"] == 1
    assert type_counts["GUARD"] == 1


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

    from bank_reconciliation_agent.services.workflow.runner import _emit_trace_span

    try:
        _emit_trace_span(state, recorder, emitter)
    except Exception as exc:
        raise AssertionError(
            f"_emit_trace_span should not raise, but got {type(exc).__name__}"
        ) from exc

    emitter.emit.assert_called_once()
    assert state["stream_seq"] == 1


# ---------------------------------------------------------------------------
# Production-path: SSE trace_span set matches persisted DB rows exactly
# ---------------------------------------------------------------------------


def _prod_match_result(flow_id: str) -> ReconciliationMatchResult:
    return ReconciliationMatchResult(
        flow_id=flow_id,
        status="PENDING_HUMAN",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount=Decimal("100.00"),
        clear_amount=Decimal("99.00"),
        amount_diff=Decimal("1.00"),
    )


def test_production_path_sse_span_set_matches_persisted_rows(monkeypatch) -> None:
    """Through the real ReconciliationService finalize/persist path, the emitted
    ``trace_span`` set equals the persisted DB rows, with the root and terminal
    each emitted exactly once and canonical fields identical on both sides."""
    engine = create_engine("sqlite:///:memory:")
    service = ReconciliationService()
    service._engine = engine
    trace_service = TraceService(engine)

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.persistence.trace_service",
        trace_service,
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.service.transaction_service.get_bank_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "银行流水"},
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.service.transaction_service.get_clear_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "清算流水"},
    )

    def deterministic_run_item(state, *, emitter):
        return run_item(
            state,
            extraction_agent=SpyExtractionAgent(),
            trace_agent=SpyTraceAgent(),
            audit_agent=SpyAuditAgent(),
            tool_executor=RetrieverBackedToolExecutor(retriever=StaticRetriever()),
            emitter=emitter,
        )

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.service.run_item",
        deterministic_run_item,
    )

    user_id, task_id, flow_id = "prod_u", "TASK-PROD", "FLOW-PROD"
    result = _prod_match_result(flow_id)
    emitter = QueueEmitter()

    queue_rows = service._write_queue_entries(user_id, task_id, "BANK_ENTERPRISE", [result])
    service._write_ledger_entries(
        user_id,
        task_id,
        "BANK_ENTERPRISE",
        [result],
        queue_rows=queue_rows,
        emitter=emitter,
    )

    db_spans = trace_service.get_spans(user_id=user_id, task_id=task_id, flow_id=flow_id)
    assert db_spans, "trace must persist through the real path"
    db_by_id = {s.span_id: s for s in db_spans}

    trace_events = [e for e in emitter.drain() if e.event_type == StreamEventType.TRACE_SPAN]
    sse_by_id = {e.payload["span_id"]: e.payload for e in trace_events}

    # 1. Exact identity-set match between SSE and persisted DB rows.
    assert set(sse_by_id) == set(db_by_id)
    # 2. No duplicate trace_span events.
    assert len(trace_events) == len(sse_by_id)

    # 3. Root and terminal each appear exactly once on both sides.
    db_roots = [s for s in db_spans if s.span_type == SpanType.WORKFLOW]
    db_terminals = [s for s in db_spans if s.span_type in (SpanType.FINAL, SpanType.FALLBACK)]
    assert len(db_roots) == 1
    assert len(db_terminals) == 1
    sse_types = [p["span_type"] for p in sse_by_id.values()]
    assert sse_types.count("WORKFLOW") == 1
    assert sse_types.count("FINAL") + sse_types.count("FALLBACK") == 1

    # 4. Canonical fields identical for every span shared by both sides.
    for span_id, payload in sse_by_id.items():
        span = db_by_id[span_id]
        assert payload["trace_id"] == span.trace_id
        assert payload["sequence_no"] == span.sequence_no
        assert payload["span_type"] == span.span_type.value
        assert payload["status"] == span.status.value
        assert payload["outcome"] == span.outcome
        assert "user_id" not in payload


def _prod_setup(monkeypatch):
    """Wire the real ReconciliationService finalize/persist path on the shared
    engine with deterministic spy agents; return the service."""
    service = ReconciliationService()  # uses the global engine, like the workers
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.service.transaction_service.get_bank_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "银行流水"},
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.service.transaction_service.get_clear_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "清算流水"},
    )

    def deterministic_run_item(state, *, emitter):
        return run_item(
            state,
            extraction_agent=SpyExtractionAgent(),
            trace_agent=SpyTraceAgent(),
            audit_agent=SpyAuditAgent(),
            tool_executor=RetrieverBackedToolExecutor(retriever=StaticRetriever()),
            emitter=emitter,
        )

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.service.run_item",
        deterministic_run_item,
    )
    return service


class _RecordingLog:
    """Fake structured logger capturing warning calls; every other level no-ops."""

    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict]] = []

    def warning(self, event, **kwargs) -> None:
        self.warnings.append((event, kwargs))

    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return None

        return _noop


_SENSITIVE_MARKER = "SENSITIVE-TRACE-PAYLOAD-DO-NOT-LEAK"


def _install_from_span_failure(monkeypatch, emitter):
    def _boom(span):
        raise RuntimeError(_SENSITIVE_MARKER)

    monkeypatch.setattr(TraceSpanView, "from_span", staticmethod(_boom))
    return emitter


def _install_event_failure(monkeypatch, emitter):
    def _boom(view, *, seq):
        raise RuntimeError(_SENSITIVE_MARKER)

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.runtime.to_trace_span_event", _boom
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.flow.to_trace_span_event", _boom
    )
    return emitter


def _install_emit_failure(monkeypatch, emitter):
    del emitter

    class _BrokenEmitter:
        def emit(self, event) -> None:
            if event.event_type == StreamEventType.TRACE_SPAN:
                raise RuntimeError(_SENSITIVE_MARKER)

    return _BrokenEmitter()


@pytest.mark.parametrize(
    "installer",
    [_install_from_span_failure, _install_event_failure, _install_emit_failure],
    ids=["from_span", "to_trace_span_event", "emitter_emit"],
)
def test_production_path_trace_span_failure_is_isolated(monkeypatch, installer) -> None:
    """Each of the three trace_span failure classes (projection, event build,
    emit) is isolated: business commits, Trace persists, warnings stay clean."""
    recording_log = _RecordingLog()
    monkeypatch.setattr("bank_reconciliation_agent.services.workflow.runner.log", recording_log)
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.service.log", recording_log
    )
    monkeypatch.setattr("bank_reconciliation_agent.services.workflow.runtime.log", recording_log)
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.flow.log", recording_log
    )

    user_id = "iso_u"
    task_id = f"TASK-ISO-{installer.__name__}"
    flow_id = "FLOW-ISO"

    service = _prod_setup(monkeypatch)
    task_service.replace_task(
        user_id=user_id,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=1,
        pending_human_rows=0,
        status="RUNNING",
    )

    emitter = installer(monkeypatch, QueueEmitter())

    result = _prod_match_result(flow_id)
    queue_rows = service._write_queue_entries(user_id, task_id, "BANK_ENTERPRISE", [result])

    # 1. Business call must not raise despite the injected trace_span fault.
    service._write_ledger_entries(
        user_id,
        task_id,
        "BANK_ENTERPRISE",
        [result],
        queue_rows=queue_rows,
        emitter=emitter,
    )

    # 2. Ledger committed and the final decision is unchanged.
    ledger_page = ledger_service.list(
        user_id=user_id, query=LedgerQuery(task_id=task_id, page=1, page_size=100)
    )
    ledger_row = next((r for r in ledger_page.items if r.flow_id == flow_id), None)
    assert ledger_row is not None
    assert ledger_row.handle_status == "PENDING_HUMAN"

    # 3. Queue committed.
    assert queue_service.get_row(user_id=user_id, task_id=task_id, flow_id=flow_id) is not None

    # 4. Task stats committed.
    task_row = task_service.get(user_id=user_id, task_id=task_id)
    assert task_row is not None
    assert task_row.ai_processed_rows == 1

    # 5. Trace rows still persisted with WORKFLOW + a unique terminal, proving the
    #    recorder snapshot was neither disabled nor rewritten by the fault.
    db_spans = global_trace_service.get_spans(user_id=user_id, task_id=task_id, flow_id=flow_id)
    types = [s.span_type for s in db_spans]
    assert SpanType.WORKFLOW in types
    assert types.count(SpanType.FINAL) + types.count(SpanType.FALLBACK) == 1

    # 6. Warnings were emitted for the isolated fault but carry no exception text.
    assert any(event == "trace_span_emit_failed" for event, _ in recording_log.warnings)
    serialized = json.dumps(recording_log.warnings, default=str)
    assert _SENSITIVE_MARKER not in serialized

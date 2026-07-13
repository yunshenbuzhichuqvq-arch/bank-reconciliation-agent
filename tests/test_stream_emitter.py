from decimal import Decimal

from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.schemas.trace import TraceSpanView, SpanType, SpanStatus
from bank_reconciliation_agent.services.exception_router import BranchResult
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from bank_reconciliation_agent.services.stream_emitter import QueueEmitter, to_trace_span_event
from bank_reconciliation_agent.services.workflow import run_item

from tests.test_workflow import SpyAuditAgent, SpyExtractionAgent, SpyTraceAgent, StaticRetriever, _state
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

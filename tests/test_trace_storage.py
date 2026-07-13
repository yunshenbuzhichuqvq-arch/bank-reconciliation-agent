"""Tests for TraceService persistence — SQLite backend.

Covers: batch insert/query/order, multi-run history, cross-user empty results,
batch rollback on duplicate, evidence_ids round-trip, and tenant isolation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine

from bank_reconciliation_agent.schemas.trace import (
    SpanStatus,
    SpanType,
    ToolOutcome,
    TraceSpan,
    WorkflowOutcome,
)
from bank_reconciliation_agent.services.trace import TraceService, t_trace_span


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)
_LATER = datetime(2026, 7, 13, 0, 0, 1, tzinfo=timezone.utc)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def svc(engine) -> TraceService:
    return TraceService(engine=engine)


def _make_span(
    trace_id: str,
    span_id: str | None = None,
    *,
    parent_span_id: str | None = None,
    user_id: str = "user_1",
    task_id: str = "task_1",
    flow_id: str = "flow_1",
    sequence_no: int = 1,
    span_type: SpanType = SpanType.WORKFLOW,
    name: str = "reconciliation_workflow",
    started_at: datetime = _NOW,
    ended_at: datetime = _LATER,
    duration_ms: int = 1000,
    status: SpanStatus = SpanStatus.SUCCEEDED,
    outcome: str | None = WorkflowOutcome.AUTO_FIXED,
    evidence_ids: list[str] | None = None,
    **kwargs: object,
) -> TraceSpan:
    return TraceSpan(
        trace_id=trace_id,
        span_id=span_id or str(uuid.uuid4()),
        parent_span_id=parent_span_id,
        user_id=user_id,
        task_id=task_id,
        flow_id=flow_id,
        sequence_no=sequence_no,
        span_type=span_type,
        name=name,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        status=status,
        outcome=outcome,
        evidence_ids=evidence_ids or [],
        **kwargs,
    )


def _make_full_trace(
    trace_id: str,
    *,
    user_id: str = "user_1",
    task_id: str = "task_1",
    flow_id: str = "flow_1",
    started_at: datetime = _NOW,
) -> list[TraceSpan]:
    """Build a minimal complete 4-span trace."""
    root_span_id = str(uuid.uuid4())
    route_span_id = str(uuid.uuid4())
    tool_span_id = str(uuid.uuid4())
    final_span_id = str(uuid.uuid4())
    ended = datetime(
        started_at.year,
        started_at.month,
        started_at.day,
        started_at.hour,
        started_at.minute,
        started_at.second + 1,
        tzinfo=timezone.utc,
    )
    return [
        _make_span(
            trace_id,
            root_span_id,
            user_id=user_id,
            task_id=task_id,
            flow_id=flow_id,
            sequence_no=1,
            span_type=SpanType.WORKFLOW,
            name="reconciliation_workflow",
            started_at=started_at,
            ended_at=ended,
            outcome=WorkflowOutcome.AUTO_FIXED,
        ),
        _make_span(
            trace_id,
            route_span_id,
            parent_span_id=root_span_id,
            user_id=user_id,
            task_id=task_id,
            flow_id=flow_id,
            sequence_no=2,
            span_type=SpanType.ROUTE,
            name="AMOUNT_MISMATCH",
            started_at=started_at,
            ended_at=ended,
            outcome=None,
        ),
        _make_span(
            trace_id,
            tool_span_id,
            parent_span_id=route_span_id,
            user_id=user_id,
            task_id=task_id,
            flow_id=flow_id,
            sequence_no=3,
            span_type=SpanType.TOOL,
            name="search_rules",
            started_at=started_at,
            ended_at=ended,
            outcome=ToolOutcome.RESULT,
            result_count=3,
            evidence_ids=["chunk_1", "chunk_2"],
        ),
        _make_span(
            trace_id,
            final_span_id,
            parent_span_id=root_span_id,
            user_id=user_id,
            task_id=task_id,
            flow_id=flow_id,
            sequence_no=4,
            span_type=SpanType.FINAL,
            name="final_decision",
            started_at=started_at,
            ended_at=ended,
            outcome=WorkflowOutcome.AUTO_FIXED,
        ),
    ]


# ---------------------------------------------------------------------------
# Insert & query
# ---------------------------------------------------------------------------


class TestInsertAndQuery:
    """Basic batch insert and query by tenant."""

    def test_insert_and_read_single_trace(self, svc: TraceService) -> None:
        trace_id = str(uuid.uuid4())
        spans = _make_full_trace(trace_id)
        svc.save_trace(user_id="user_1", spans=spans)

        result = svc.get_spans(user_id="user_1", task_id="task_1", flow_id="flow_1")
        assert len(result) == 4
        # Should be ordered by sequence_no
        assert [s.sequence_no for s in result] == [1, 2, 3, 4]

    def test_spans_ordered_by_sequence_no(self, svc: TraceService) -> None:
        trace_id = str(uuid.uuid4())
        spans = _make_full_trace(trace_id)
        svc.save_trace(user_id="user_1", spans=spans)

        result = svc.get_spans(user_id="user_1", task_id="task_1", flow_id="flow_1")
        types = [s.span_type for s in result]
        assert types == [
            SpanType.WORKFLOW,
            SpanType.ROUTE,
            SpanType.TOOL,
            SpanType.FINAL,
        ]

    def test_evidence_ids_roundtrip(self, svc: TraceService) -> None:
        trace_id = str(uuid.uuid4())
        spans = _make_full_trace(trace_id)
        svc.save_trace(user_id="user_1", spans=spans)

        result = svc.get_spans(user_id="user_1", task_id="task_1", flow_id="flow_1")
        tool_span = [s for s in result if s.span_type == SpanType.TOOL][0]
        assert tool_span.evidence_ids == ["chunk_1", "chunk_2"]

    def test_empty_evidence_ids_roundtrip(self, svc: TraceService) -> None:
        trace_id = str(uuid.uuid4())
        spans = [_make_span(trace_id, evidence_ids=[])]
        svc.save_trace(user_id="user_1", spans=spans)

        result = svc.get_spans(user_id="user_1", task_id="task_1", flow_id="flow_1")
        assert result[0].evidence_ids == []

    def test_save_empty_list_is_noop(self, svc: TraceService) -> None:
        svc.save_trace(user_id="user_1", spans=[])
        assert svc.count_runs(user_id="user_1", task_id="task_1", flow_id="flow_1") == 0


# ---------------------------------------------------------------------------
# Multi-run history
# ---------------------------------------------------------------------------


class TestMultiRunHistory:
    """Same task_id+flow_id can hold multiple trace_ids."""

    def test_two_runs_for_same_flow(self, svc: TraceService) -> None:
        t1 = str(uuid.uuid4())
        t2 = str(uuid.uuid4())
        spans1 = _make_full_trace(
            t1,
            started_at=datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc),
        )
        spans2 = _make_full_trace(
            t2,
            started_at=datetime(2026, 7, 13, 1, 0, 0, tzinfo=timezone.utc),
        )
        svc.save_trace(user_id="user_1", spans=spans1)
        svc.save_trace(user_id="user_1", spans=spans2)

        assert svc.count_runs(user_id="user_1", task_id="task_1", flow_id="flow_1") == 2

    def test_list_runs_most_recent_first(self, svc: TraceService) -> None:
        t1 = str(uuid.uuid4())
        t2 = str(uuid.uuid4())
        earlier = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)
        later = datetime(2026, 7, 13, 1, 0, 0, tzinfo=timezone.utc)

        svc.save_trace(user_id="user_1", spans=_make_full_trace(t1, started_at=earlier))
        svc.save_trace(user_id="user_1", spans=_make_full_trace(t2, started_at=later))

        runs = svc.list_runs(user_id="user_1", task_id="task_1", flow_id="flow_1")
        assert len(runs) == 2
        assert runs[0]["trace_id"] == t2  # most recent first
        assert runs[1]["trace_id"] == t1

    def test_get_spans_default_latest(self, svc: TraceService) -> None:
        t1 = str(uuid.uuid4())
        t2 = str(uuid.uuid4())
        earlier = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)
        later = datetime(2026, 7, 13, 1, 0, 0, tzinfo=timezone.utc)

        svc.save_trace(user_id="user_1", spans=_make_full_trace(t1, started_at=earlier))
        svc.save_trace(user_id="user_1", spans=_make_full_trace(t2, started_at=later))

        result = svc.get_spans(user_id="user_1", task_id="task_1", flow_id="flow_1")
        assert all(s.trace_id == t2 for s in result)

    def test_get_spans_specific_trace_id(self, svc: TraceService) -> None:
        t1 = str(uuid.uuid4())
        t2 = str(uuid.uuid4())
        earlier = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)
        later = datetime(2026, 7, 13, 1, 0, 0, tzinfo=timezone.utc)

        svc.save_trace(user_id="user_1", spans=_make_full_trace(t1, started_at=earlier))
        svc.save_trace(user_id="user_1", spans=_make_full_trace(t2, started_at=later))

        result = svc.get_spans(user_id="user_1", task_id="task_1", flow_id="flow_1", trace_id=t1)
        assert all(s.trace_id == t1 for s in result)


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """Reads must be tenant-scoped; cross-user queries return empty."""

    def test_cross_user_returns_empty(self, svc: TraceService) -> None:
        trace_id = str(uuid.uuid4())
        svc.save_trace(user_id="user_1", spans=_make_full_trace(trace_id))

        result = svc.get_spans(user_id="user_2", task_id="task_1", flow_id="flow_1")
        assert result == []

    def test_cross_user_count_zero(self, svc: TraceService) -> None:
        trace_id = str(uuid.uuid4())
        svc.save_trace(user_id="user_1", spans=_make_full_trace(trace_id))

        assert svc.count_runs(user_id="user_2", task_id="task_1", flow_id="flow_1") == 0

    def test_cross_user_list_runs_empty(self, svc: TraceService) -> None:
        trace_id = str(uuid.uuid4())
        svc.save_trace(user_id="user_1", spans=_make_full_trace(trace_id))

        runs = svc.list_runs(user_id="user_2", task_id="task_1", flow_id="flow_1")
        assert runs == []


# ---------------------------------------------------------------------------
# Duplicate rejection (DB constraints)
# ---------------------------------------------------------------------------


class TestDuplicateRejection:
    """DB unique constraints prevent duplicate span_id or sequence_no."""

    def test_duplicate_span_id_rejected(self, svc: TraceService) -> None:
        trace_id = str(uuid.uuid4())
        shared_span_id = str(uuid.uuid4())
        span1 = _make_span(trace_id, shared_span_id, sequence_no=1)
        span2 = _make_span(trace_id, shared_span_id, sequence_no=2)

        with pytest.raises(Exception):
            svc.save_trace(user_id="user_1", spans=[span1, span2])

    def test_duplicate_sequence_no_rejected(self, svc: TraceService) -> None:
        trace_id = str(uuid.uuid4())
        span1 = _make_span(trace_id, sequence_no=1)
        span2 = _make_span(trace_id, sequence_no=1)

        with pytest.raises(Exception):
            svc.save_trace(user_id="user_1", spans=[span1, span2])


# ---------------------------------------------------------------------------
# Batch rollback
# ---------------------------------------------------------------------------


class TestBatchRollback:
    """Failed batch must not leave partial rows."""

    def test_failed_batch_leaves_no_rows(self, svc: TraceService) -> None:
        trace_id = str(uuid.uuid4())
        good_span = _make_span(trace_id, sequence_no=1)
        # Create a duplicate sequence_no to trigger failure
        bad_span = _make_span(trace_id, sequence_no=1)

        with pytest.raises(Exception):
            svc.save_trace(user_id="user_1", spans=[good_span, bad_span])

        assert svc.count_runs(user_id="user_1", task_id="task_1", flow_id="flow_1") == 0


# ---------------------------------------------------------------------------
# Table structure validation
# ---------------------------------------------------------------------------


class TestTableStructure:
    """Verify t_trace_span table is created with expected columns."""

    def test_table_created_with_columns(self, svc: TraceService) -> None:
        svc._ensure_initialized()
        expected_columns = {
            "id",
            "trace_id",
            "span_id",
            "parent_span_id",
            "user_id",
            "task_id",
            "flow_id",
            "sequence_no",
            "span_type",
            "name",
            "started_at",
            "ended_at",
            "duration_ms",
            "status",
            "outcome",
            "attempt",
            "retry_recovered",
            "recovered_error_type",
            "structured_repair_attempted",
            "structured_repair_succeeded",
            "model_name",
            "prompt_tokens",
            "completion_tokens",
            "cached_calls",
            "result_count",
            "error_type",
            "fallback_reason",
            "evidence_ids",
            "schema_version",
            "created_at",
        }
        actual_columns = {c.name for c in t_trace_span.columns}
        assert actual_columns == expected_columns


# ---------------------------------------------------------------------------
# Nonexistent data
# ---------------------------------------------------------------------------


class TestNonexistentData:
    """Queries for missing data return empty, not errors."""

    def test_get_spans_no_data(self, svc: TraceService) -> None:
        result = svc.get_spans(user_id="user_1", task_id="task_x", flow_id="flow_x")
        assert result == []

    def test_count_runs_no_data(self, svc: TraceService) -> None:
        assert svc.count_runs(user_id="user_1", task_id="task_x", flow_id="flow_x") == 0

    def test_list_runs_no_data(self, svc: TraceService) -> None:
        runs = svc.list_runs(user_id="user_1", task_id="task_x", flow_id="flow_x")
        assert runs == []

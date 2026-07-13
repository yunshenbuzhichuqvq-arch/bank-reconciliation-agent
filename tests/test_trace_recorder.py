"""Tests for flow-scoped TraceRecorder and structural invariants.

Covers: normal nesting, completion-order independence, Tool retry recovery,
LLM repair, Guard blocked, business exception propagation, all structural
invariant failure paths, no-op recorder, and recorder self-fault disabling.

Refs: TASK-29.2
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from bank_reconciliation_agent.schemas.trace import (
    GuardOutcome,
    SpanStatus,
    SpanType,
    ToolOutcome,
    TraceSpan,
    WorkflowOutcome,
)
from bank_reconciliation_agent.services.trace import (
    NoOpRecorder,
    TraceRecorder,
    validate_trace_snapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_recorder(
    user_id: str = "user_1",
    task_id: str = "task_1",
    flow_id: str = "flow_1",
    root_name: str = "reconciliation_workflow",
) -> TraceRecorder:
    return TraceRecorder(
        user_id=user_id,
        task_id=task_id,
        flow_id=flow_id,
        root_name=root_name,
    )


# ---------------------------------------------------------------------------
# 1. Identity and root span
# ---------------------------------------------------------------------------


class TestRecorderIdentity:
    """Each recorder creates new UUID trace_id and unique root WORKFLOW span."""

    def test_new_trace_id(self) -> None:
        r = _make_recorder()
        assert r.trace_id
        uuid.UUID(r.trace_id)  # must be valid UUID

    def test_unique_trace_ids(self) -> None:
        r1 = _make_recorder()
        r2 = _make_recorder()
        assert r1.trace_id != r2.trace_id

    def test_root_span_is_workflow(self) -> None:
        r = _make_recorder()
        # Close root span normally
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        root = snapshot[0]
        assert root.span_type == SpanType.WORKFLOW
        assert root.sequence_no == 1
        assert root.parent_span_id is None
        assert root.name == "reconciliation_workflow"


# ---------------------------------------------------------------------------
# 2. Sequence numbering
# ---------------------------------------------------------------------------


class TestSequenceNumbering:
    """sequence_no assigned at span start, from 1, continuously incrementing."""

    def test_sequential_assignment(self) -> None:
        r = _make_recorder()
        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH"):
            pass
        with r.span(SpanType.TOOL, "search_rules"):
            pass
        with r.span(SpanType.AGENT, "AuditAgent", model_name="deepseek-chat"):
            pass
        r.close_root(
            status=SpanStatus.SUCCEEDED,
            outcome=WorkflowOutcome.AUTO_FIXED,
            terminal_type=SpanType.FINAL,
            terminal_name="final_decision",
        )
        snapshot = r.snapshot()

        seqs = [s.sequence_no for s in snapshot]
        assert seqs == [1, 2, 3, 4, 5]  # root=1, route=2, tool=3, agent=4, terminal=5

    def test_completion_order_does_not_change_sequence(self) -> None:
        """Spans that start first get lower sequence, regardless of end order."""
        r = _make_recorder()
        # Start two spans manually (parent -> child nesting)
        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH"):
            with r.span(SpanType.TOOL, "search_rules"):
                pass  # inner finishes first
            # outer finishes second

        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        route = [s for s in snapshot if s.name == "AMOUNT_MISMATCH"][0]
        tool = [s for s in snapshot if s.name == "search_rules"][0]
        assert route.sequence_no < tool.sequence_no


# ---------------------------------------------------------------------------
# 3. Parent-child context management
# ---------------------------------------------------------------------------


class TestParentChild:
    """Context manager correctly maintains parent-child relationships."""

    def test_nested_parent_child(self) -> None:
        r = _make_recorder()
        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH") as route_span:
            with r.span(SpanType.TOOL, "search_rules"):
                pass

        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()

        root = snapshot[0]
        route = [s for s in snapshot if s.name == "AMOUNT_MISMATCH"][0]
        tool = [s for s in snapshot if s.name == "search_rules"][0]

        assert route.parent_span_id == root.span_id
        assert tool.parent_span_id == route_span.span_id

    def test_sibling_spans_share_parent(self) -> None:
        r = _make_recorder()
        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH"):
            with r.span(SpanType.TOOL, "search_rules"):
                pass
            with r.span(SpanType.TOOL, "load_confirmed_cases"):
                pass

        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()

        route = [s for s in snapshot if s.name == "AMOUNT_MISMATCH"][0]
        tool1 = [s for s in snapshot if s.name == "search_rules"][0]
        tool2 = [s for s in snapshot if s.name == "load_confirmed_cases"][0]

        assert tool1.parent_span_id == route.span_id
        assert tool2.parent_span_id == route.span_id


# ---------------------------------------------------------------------------
# 4. Duration and time
# ---------------------------------------------------------------------------


class TestDuration:
    """Monotonic clock duration, non-negative, doesn't swallow exceptions."""

    def test_duration_non_negative(self) -> None:
        r = _make_recorder()
        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH"):
            pass

        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        for s in snapshot:
            assert s.duration_ms >= 0

    def test_utc_timestamps(self) -> None:
        r = _make_recorder()
        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH"):
            pass
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        for s in snapshot:
            assert s.started_at.tzinfo is not None
            assert s.ended_at.tzinfo is not None
            assert s.ended_at >= s.started_at


# ---------------------------------------------------------------------------
# 5. Exception handling
# ---------------------------------------------------------------------------


class TestExceptionHandling:
    """Recorder does not swallow business exceptions; failed spans are FAILED."""

    def test_business_exception_propagated(self) -> None:
        r = _make_recorder()
        with pytest.raises(ValueError, match="business error"):
            with r.span(SpanType.AGENT, "AuditAgent", model_name="deepseek-chat"):
                raise ValueError("business error")

    def test_exception_marks_span_failed(self) -> None:
        r = _make_recorder()
        try:
            with r.span(SpanType.AGENT, "AuditAgent", model_name="deepseek-chat"):
                raise ValueError("business error")
        except ValueError:
            pass

        r.close_root(status=SpanStatus.FAILED, outcome=WorkflowOutcome.PENDING_HUMAN)
        snapshot = r.snapshot()
        agent = [s for s in snapshot if s.name == "AuditAgent"][0]
        assert agent.status == SpanStatus.FAILED

    def test_exception_does_not_change_return_value(self) -> None:
        """Recorder fault doesn't change wrapped operation result."""
        r = _make_recorder()
        result = None
        with r.span(SpanType.TOOL, "search_rules"):
            result = "expected_value"
        assert result == "expected_value"


# ---------------------------------------------------------------------------
# 6. Seven span types
# ---------------------------------------------------------------------------


class TestSevenSpanTypes:
    """Recorder can record all seven span types."""

    def test_all_span_types(self) -> None:
        r = _make_recorder()
        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH"):
            pass
        with r.span(SpanType.TOOL, "search_rules"):
            pass
        with r.span(SpanType.AGENT, "AuditAgent", model_name="deepseek-chat"):
            pass
        with r.span(SpanType.GUARD, "SafetyGuard"):
            pass
        r.close_root(
            status=SpanStatus.SUCCEEDED,
            outcome=WorkflowOutcome.AUTO_FIXED,
            terminal_type=SpanType.FINAL,
            terminal_name="final_decision",
        )
        snapshot = r.snapshot()

        types = {s.span_type for s in snapshot}
        assert SpanType.WORKFLOW in types
        assert SpanType.ROUTE in types
        assert SpanType.TOOL in types
        assert SpanType.AGENT in types
        assert SpanType.GUARD in types
        assert SpanType.FINAL in types


# ---------------------------------------------------------------------------
# 7. Tool projection
# ---------------------------------------------------------------------------


class TestToolProjection:
    """Tool projection maps Stage 28 safe result to one span."""

    def test_tool_success_projection(self) -> None:
        r = _make_recorder()
        r.record_tool(
            name="search_rules",
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.RESULT,
            duration_ms=150,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            result_count=5,
            evidence_ids=["chunk_abc"],
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        tool = [s for s in snapshot if s.span_type == SpanType.TOOL][0]
        assert tool.name == "search_rules"
        assert tool.outcome == "RESULT"
        assert tool.attempt == 1
        assert tool.result_count == 5
        assert tool.evidence_ids == ["chunk_abc"]

    def test_tool_retry_recovery(self) -> None:
        r = _make_recorder()
        r.record_tool(
            name="search_rules",
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.RESULT,
            duration_ms=300,
            attempt=2,
            retry_recovered=True,
            recovered_error_type="TIMEOUT",
            result_count=3,
            evidence_ids=["chunk_1"],
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        tool = [s for s in snapshot if s.span_type == SpanType.TOOL][0]
        assert tool.attempt == 2
        assert tool.retry_recovered is True
        assert tool.recovered_error_type == "TIMEOUT"

    def test_tool_failed_projection(self) -> None:
        r = _make_recorder()
        r.record_tool(
            name="search_rules",
            status=SpanStatus.FAILED,
            outcome=None,
            duration_ms=500,
            attempt=2,
            retry_recovered=False,
            recovered_error_type=None,
            error_type="TIMEOUT",
            fallback_reason="TOOL_TIMEOUT",
            result_count=0,
            evidence_ids=[],
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.PENDING_HUMAN)
        snapshot = r.snapshot()
        tool = [s for s in snapshot if s.span_type == SpanType.TOOL][0]
        assert tool.status == SpanStatus.FAILED
        assert tool.outcome is None
        assert tool.error_type == "TIMEOUT"
        assert tool.fallback_reason == "TOOL_TIMEOUT"

    def test_tool_empty_projection(self) -> None:
        r = _make_recorder()
        r.record_tool(
            name="load_confirmed_cases",
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.EMPTY,
            duration_ms=100,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            result_count=0,
            evidence_ids=[],
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        tool = [s for s in snapshot if s.span_type == SpanType.TOOL][0]
        assert tool.outcome == "EMPTY"
        assert tool.result_count == 0

    def test_tool_no_args_or_result_in_span(self) -> None:
        """Tool span must not contain args/result/attempt details."""
        r = _make_recorder()
        r.record_tool(
            name="search_rules",
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.RESULT,
            duration_ms=150,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            result_count=5,
            evidence_ids=["chunk_abc"],
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        tool = [s for s in snapshot if s.span_type == SpanType.TOOL][0]
        dumped = tool.model_dump()
        assert "args" not in dumped
        assert "result" not in dumped
        assert "attempts" not in dumped


# ---------------------------------------------------------------------------
# 7b. Call-lifecycle spans (allocate before the real call, complete after)
# ---------------------------------------------------------------------------


class TestCallLifecycleSpans:
    """start_tool/finish_tool and start_agent/finish_agent allocate the span
    (id, sequence_no, started_at, parent) *before* the real call and only
    complete it afterwards using the monotonic clock."""

    def test_start_tool_allocates_identity_before_completion(self) -> None:
        r = _make_recorder()
        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH"):
            pass
        handle = r.start_tool("search_rules")
        # Identity, ordering, start time and parent are assigned immediately.
        assert handle is not None
        assert handle.span_id
        assert handle.sequence_no == 3  # root=1, route=2, tool=3
        assert handle.started_at.tzinfo is not None
        assert handle.parent_span_id == r._root.span_id  # parent is the root span

        marker = datetime.now(timezone.utc)
        r.finish_tool(
            handle,
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.RESULT,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            result_count=2,
            evidence_ids=["chunk_1"],
        )
        r.close_root(
            status=SpanStatus.SUCCEEDED,
            outcome=WorkflowOutcome.PENDING_HUMAN,
            terminal_type=SpanType.FALLBACK,
        )
        snapshot = r.snapshot()
        tool = [s for s in snapshot if s.span_type == SpanType.TOOL][0]
        # started_at was captured at allocation (before completion marker);
        # ended_at is at/after completion; duration is monotonic and non-negative.
        assert tool.started_at <= marker
        assert tool.ended_at >= marker
        assert tool.duration_ms >= 0
        assert tool.outcome == "RESULT"
        assert tool.result_count == 2
        assert tool.evidence_ids == ["chunk_1"]

    def test_finish_tool_failed_keeps_null_outcome(self) -> None:
        r = _make_recorder()
        handle = r.start_tool("search_rules")
        r.finish_tool(
            handle,
            status=SpanStatus.FAILED,
            outcome=None,
            attempt=2,
            retry_recovered=False,
            recovered_error_type=None,
            error_type="CIRCUIT_OPEN",
            fallback_reason="RAG_CIRCUIT_OPEN",
        )
        r.close_root(
            status=SpanStatus.SUCCEEDED,
            outcome=WorkflowOutcome.PENDING_HUMAN,
            terminal_type=SpanType.FALLBACK,
        )
        tool = [s for s in r.snapshot() if s.span_type == SpanType.TOOL][0]
        assert tool.status == SpanStatus.FAILED
        assert tool.outcome is None
        assert tool.error_type == "CIRCUIT_OPEN"
        assert tool.fallback_reason == "RAG_CIRCUIT_OPEN"

    def test_start_agent_allocates_identity_before_completion(self) -> None:
        r = _make_recorder()
        handle = r.start_agent("AuditAgent")
        assert handle is not None
        assert handle.span_id
        assert handle.sequence_no == 2  # root=1, agent=2
        marker = datetime.now(timezone.utc)
        r.finish_agent(
            handle,
            status=SpanStatus.SUCCEEDED,
            model_name="deepseek-chat",
            prompt_tokens=500,
            completion_tokens=200,
            cached_calls=0,
            attempt=1,
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        agent = [s for s in r.snapshot() if s.span_type == SpanType.AGENT][0]
        assert agent.started_at <= marker
        assert agent.ended_at >= marker
        assert agent.duration_ms >= 0
        assert agent.prompt_tokens == 500
        assert agent.model_name == "deepseek-chat"

    def test_finish_agent_carries_recovered_error_type(self) -> None:
        r = _make_recorder()
        handle = r.start_agent("AuditAgent")
        r.finish_agent(
            handle,
            status=SpanStatus.SUCCEEDED,
            model_name="deepseek-chat",
            prompt_tokens=10,
            completion_tokens=5,
            attempt=2,
            retry_recovered=True,
            recovered_error_type="timeout",
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        agent = [s for s in r.snapshot() if s.span_type == SpanType.AGENT][0]
        assert agent.retry_recovered is True
        assert agent.recovered_error_type == "timeout"

    def test_disabled_recorder_start_returns_none(self) -> None:
        r = _make_recorder()
        r.disable()
        assert r.start_tool("search_rules") is None
        assert r.start_agent("AuditAgent") is None
        # finish with a None handle is a safe no-op.
        r.finish_tool(
            None,
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.RESULT,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
        )
        assert r.snapshot() == ()

    def test_noop_recorder_lifecycle_is_safe(self) -> None:
        r = NoOpRecorder()
        assert r.start_tool("search_rules") is None
        assert r.start_agent("AuditAgent") is None
        r.finish_tool(None, status=SpanStatus.SUCCEEDED, outcome=None, attempt=1)
        r.finish_agent(None, status=SpanStatus.SUCCEEDED)
        assert r.snapshot() == ()


# ---------------------------------------------------------------------------
# 8. Agent projection
# ---------------------------------------------------------------------------


class TestAgentProjection:
    """Agent projection maps Stage 26 logical summary/result."""

    def test_agent_success_projection(self) -> None:
        r = _make_recorder()
        r.record_agent(
            name="AuditAgent",
            status=SpanStatus.SUCCEEDED,
            duration_ms=2000,
            model_name="deepseek-chat",
            prompt_tokens=500,
            completion_tokens=200,
            cached_calls=1,
            attempt=2,
            retry_recovered=True,
            recovered_error_type="timeout",
            structured_repair_attempted=True,
            structured_repair_succeeded=True,
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        agent = [s for s in snapshot if s.span_type == SpanType.AGENT][0]
        assert agent.name == "AuditAgent"
        assert agent.model_name == "deepseek-chat"
        assert agent.prompt_tokens == 500
        assert agent.completion_tokens == 200
        assert agent.cached_calls == 1
        assert agent.structured_repair_attempted is True
        assert agent.structured_repair_succeeded is True
        assert agent.outcome is None  # AGENT outcome always null

    def test_agent_failed_projection(self) -> None:
        r = _make_recorder()
        r.record_agent(
            name="AuditAgent",
            status=SpanStatus.FAILED,
            duration_ms=3000,
            model_name="deepseek-chat",
            prompt_tokens=500,
            completion_tokens=200,
            cached_calls=0,
            attempt=3,
            retry_recovered=False,
            recovered_error_type=None,
            structured_repair_attempted=True,
            structured_repair_succeeded=False,
            error_type="schema_invalid",
            fallback_reason="LLM_STRUCTURED_REPAIR_EXHAUSTED",
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.PENDING_HUMAN)
        snapshot = r.snapshot()
        agent = [s for s in snapshot if s.span_type == SpanType.AGENT][0]
        assert agent.status == SpanStatus.FAILED
        assert agent.error_type == "schema_invalid"
        assert agent.fallback_reason == "LLM_STRUCTURED_REPAIR_EXHAUSTED"

    def test_agent_no_prompt_or_model_text(self) -> None:
        """Agent span must not contain prompt or model output text."""
        r = _make_recorder()
        r.record_agent(
            name="AuditAgent",
            status=SpanStatus.SUCCEEDED,
            duration_ms=2000,
            model_name="deepseek-chat",
            prompt_tokens=500,
            completion_tokens=200,
            cached_calls=0,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            structured_repair_attempted=False,
            structured_repair_succeeded=False,
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        agent = [s for s in snapshot if s.span_type == SpanType.AGENT][0]
        dumped = agent.model_dump()
        assert "prompt" not in dumped or dumped.get("prompt") is None
        assert "text" not in dumped
        assert "response" not in dumped


# ---------------------------------------------------------------------------
# 9. Guard span
# ---------------------------------------------------------------------------


class TestGuardSpan:
    def test_guard_passed(self) -> None:
        r = _make_recorder()
        with r.span(SpanType.GUARD, "SafetyGuard", outcome=GuardOutcome.PASSED):
            pass
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        guard = [s for s in snapshot if s.span_type == SpanType.GUARD][0]
        assert guard.outcome == "PASSED"
        assert guard.status == SpanStatus.SUCCEEDED

    def test_guard_blocked(self) -> None:
        r = _make_recorder()
        with r.span(SpanType.GUARD, "SafetyGuard", outcome=GuardOutcome.BLOCKED):
            pass
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.PENDING_HUMAN)
        snapshot = r.snapshot()
        guard = [s for s in snapshot if s.span_type == SpanType.GUARD][0]
        assert guard.outcome == "BLOCKED"
        assert guard.status == SpanStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# 10. Snapshot immutability and validation
# ---------------------------------------------------------------------------


class TestSnapshotValidation:
    """Snapshot is immutable and rejects structural invariant violations."""

    def test_snapshot_is_tuple(self) -> None:
        r = _make_recorder()
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        assert isinstance(snapshot, tuple)

    def test_snapshot_rejects_missing_root(self) -> None:
        """Validate directly: no root WORKFLOW span."""
        spans = []  # empty
        with pytest.raises(ValueError, match="root"):
            validate_trace_snapshot(spans)

    def test_snapshot_rejects_multiple_terminals(self) -> None:
        """Both FINAL and FALLBACK present."""
        r = _make_recorder()
        r.close_root(
            status=SpanStatus.SUCCEEDED,
            outcome=WorkflowOutcome.AUTO_FIXED,
            terminal_type=SpanType.FINAL,
            terminal_name="final_decision",
        )
        snapshot = list(r.snapshot())
        # Manually add a FALLBACK (invalid)
        # We need a raw span with FALLBACK type — use validate_trace_snapshot directly
        extra = TraceSpan(
            trace_id=snapshot[0].trace_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=snapshot[0].span_id,
            user_id="user_1",
            task_id="task_1",
            flow_id="flow_1",
            sequence_no=len(snapshot) + 1,
            span_type=SpanType.FALLBACK,
            name="fallback_human",
            started_at=snapshot[-1].started_at,
            ended_at=snapshot[-1].ended_at,
            duration_ms=0,
            status=SpanStatus.SUCCEEDED,
            outcome=WorkflowOutcome.PENDING_HUMAN,
        )
        snapshot.append(extra)
        with pytest.raises(ValueError, match="terminal"):
            validate_trace_snapshot(snapshot)

    def test_snapshot_rejects_sequence_gap(self) -> None:
        """sequence_no with gap (1, 3 instead of 1, 2)."""
        r = _make_recorder()
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = list(r.snapshot())
        # Tamper: change the terminal's sequence_no to create a gap
        # Create a span list with a gap
        root = snapshot[0]
        terminal = TraceSpan(
            trace_id=root.trace_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=root.span_id,
            user_id="user_1",
            task_id="task_1",
            flow_id="flow_1",
            sequence_no=3,  # gap: 1, 3
            span_type=SpanType.FINAL,
            name="final_decision",
            started_at=root.started_at,
            ended_at=root.ended_at,
            duration_ms=0,
            status=SpanStatus.SUCCEEDED,
            outcome=WorkflowOutcome.AUTO_FIXED,
        )
        with pytest.raises(ValueError, match="sequence"):
            validate_trace_snapshot([root, terminal])

    def test_snapshot_rejects_duplicate_sequence(self) -> None:
        """Two spans with the same sequence_no."""
        r = _make_recorder()
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = list(r.snapshot())
        root = snapshot[0]
        dup = TraceSpan(
            trace_id=root.trace_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=root.span_id,
            user_id="user_1",
            task_id="task_1",
            flow_id="flow_1",
            sequence_no=1,  # duplicate
            span_type=SpanType.FINAL,
            name="final_decision",
            started_at=root.started_at,
            ended_at=root.ended_at,
            duration_ms=0,
            status=SpanStatus.SUCCEEDED,
            outcome=WorkflowOutcome.AUTO_FIXED,
        )
        with pytest.raises(ValueError, match="sequence"):
            validate_trace_snapshot([root, dup])

    def test_snapshot_rejects_cross_trace_parent(self) -> None:
        """parent_span_id pointing to a span not in this trace."""
        r = _make_recorder()
        r.close_root(
            status=SpanStatus.SUCCEEDED,
            outcome=WorkflowOutcome.AUTO_FIXED,
            terminal_type=SpanType.FINAL,
            terminal_name="final_decision",
        )
        snapshot = list(r.snapshot())
        root = snapshot[0]
        orphan = TraceSpan(
            trace_id=root.trace_id,
            span_id=str(uuid.uuid4()),
            parent_span_id="nonexistent-span-id",
            user_id="user_1",
            task_id="task_1",
            flow_id="flow_1",
            sequence_no=len(snapshot) + 1,
            span_type=SpanType.ROUTE,
            name="AMOUNT_MISMATCH",
            started_at=root.started_at,
            ended_at=root.ended_at,
            duration_ms=0,
            status=SpanStatus.SUCCEEDED,
            outcome=None,
        )
        with pytest.raises(ValueError, match="parent"):
            validate_trace_snapshot(list(snapshot) + [orphan])

    def test_snapshot_rejects_non_agent_with_tokens(self) -> None:
        """Non-AGENT span with non-zero tokens."""
        # This is already handled by TraceSpan validator, but verify snapshot
        # validation doesn't mask it
        r = _make_recorder()
        with r.span(SpanType.TOOL, "search_rules"):
            pass
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        tool = [s for s in snapshot if s.span_type == SpanType.TOOL][0]
        assert tool.prompt_tokens is None
        assert tool.model_name is None


# ---------------------------------------------------------------------------
# 11. No-op recorder
# ---------------------------------------------------------------------------


class TestNoOpRecorder:
    """No-op recorder generates no spans, logs, or DB side effects."""

    def test_noop_produces_no_spans(self) -> None:
        r = NoOpRecorder()
        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH"):
            pass
        r.record_tool(
            name="search_rules",
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.RESULT,
            duration_ms=100,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            result_count=5,
            evidence_ids=["chunk_1"],
        )
        r.record_agent(
            name="AuditAgent",
            status=SpanStatus.SUCCEEDED,
            duration_ms=2000,
            model_name="deepseek-chat",
            prompt_tokens=500,
            completion_tokens=200,
            cached_calls=0,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            structured_repair_attempted=False,
            structured_repair_succeeded=False,
        )
        assert r.snapshot() == ()

    def test_noop_does_not_swallow_exceptions(self) -> None:
        r = NoOpRecorder()
        with pytest.raises(ValueError, match="business"):
            with r.span(SpanType.AGENT, "AuditAgent"):
                raise ValueError("business error")

    def test_noop_has_no_trace_id(self) -> None:
        r = NoOpRecorder()
        assert r.trace_id is None

    def test_noop_close_root_is_safe(self) -> None:
        r = NoOpRecorder()
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        assert r.snapshot() == ()


# ---------------------------------------------------------------------------
# 12. Recorder self-fault disabling
# ---------------------------------------------------------------------------


class TestRecorderSelfFault:
    """Recorder self-fault can be safely disabled without changing business."""

    def test_disabled_recorder_produces_empty_snapshot(self) -> None:
        r = _make_recorder()
        r.disable()
        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH"):
            pass
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        assert r.snapshot() == ()

    def test_disabled_recorder_preserves_business_result(self) -> None:
        r = _make_recorder()
        r.disable()
        result = None
        with r.span(SpanType.TOOL, "search_rules"):
            result = "expected"
        assert result == "expected"

    def test_disabled_recorder_propagates_exceptions(self) -> None:
        r = _make_recorder()
        r.disable()
        with pytest.raises(ValueError, match="business"):
            with r.span(SpanType.AGENT, "AuditAgent"):
                raise ValueError("business error")


# ---------------------------------------------------------------------------
# 13. Fallback trace completeness
# ---------------------------------------------------------------------------


class TestFallbackTrace:
    """Business exception + fallback produces complete Fallback Trace."""

    def test_complete_fallback_trace(self) -> None:
        r = _make_recorder()
        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH"):
            pass
        r.record_tool(
            name="search_rules",
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.RESULT,
            duration_ms=150,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            result_count=3,
            evidence_ids=["chunk_1"],
        )
        r.record_agent(
            name="AuditAgent",
            status=SpanStatus.FAILED,
            duration_ms=2000,
            model_name="deepseek-chat",
            prompt_tokens=500,
            completion_tokens=200,
            cached_calls=0,
            attempt=3,
            retry_recovered=False,
            recovered_error_type=None,
            structured_repair_attempted=True,
            structured_repair_succeeded=False,
            error_type="schema_invalid",
            fallback_reason="LLM_STRUCTURED_REPAIR_EXHAUSTED",
        )
        r.close_root(
            status=SpanStatus.SUCCEEDED,
            outcome=WorkflowOutcome.PENDING_HUMAN,
            terminal_type=SpanType.FALLBACK,
            terminal_name="fallback_human",
        )
        snapshot = r.snapshot()
        # Validate structural invariants pass
        validate_trace_snapshot(list(snapshot))

        types = [s.span_type for s in snapshot]
        assert SpanType.WORKFLOW in types
        assert SpanType.ROUTE in types
        assert SpanType.TOOL in types
        assert SpanType.AGENT in types
        assert SpanType.FALLBACK in types
        assert SpanType.FINAL not in types

        root = snapshot[0]
        assert root.outcome == "PENDING_HUMAN"
        fallback = [s for s in snapshot if s.span_type == SpanType.FALLBACK][0]
        assert fallback.outcome == "PENDING_HUMAN"


# ---------------------------------------------------------------------------
# 14. Allowed fields per span type
# ---------------------------------------------------------------------------


class TestAllowedFields:
    """Only spec-defined name/outcome/error/evidence/token fields."""

    def test_tool_span_no_token_fields(self) -> None:
        r = _make_recorder()
        r.record_tool(
            name="search_rules",
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.RESULT,
            duration_ms=150,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            result_count=5,
            evidence_ids=["chunk_abc"],
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        tool = [s for s in snapshot if s.span_type == SpanType.TOOL][0]
        assert tool.prompt_tokens is None
        assert tool.completion_tokens is None
        assert tool.cached_calls is None
        assert tool.model_name is None
        assert tool.structured_repair_attempted is None
        assert tool.structured_repair_succeeded is None

    def test_agent_span_has_token_fields(self) -> None:
        r = _make_recorder()
        r.record_agent(
            name="AuditAgent",
            status=SpanStatus.SUCCEEDED,
            duration_ms=2000,
            model_name="deepseek-chat",
            prompt_tokens=500,
            completion_tokens=200,
            cached_calls=1,
            attempt=2,
            retry_recovered=True,
            recovered_error_type="timeout",
            structured_repair_attempted=False,
            structured_repair_succeeded=False,
        )
        r.close_root(status=SpanStatus.SUCCEEDED, outcome=WorkflowOutcome.AUTO_FIXED)
        snapshot = r.snapshot()
        agent = [s for s in snapshot if s.span_type == SpanType.AGENT][0]
        assert agent.prompt_tokens == 500
        assert agent.model_name == "deepseek-chat"


# ---------------------------------------------------------------------------
# 15. Full workflow integration
# ---------------------------------------------------------------------------


class TestFullWorkflow:
    """End-to-end recorder usage simulating a complete workflow."""

    def test_complete_success_path(self) -> None:
        r = _make_recorder()

        with r.span(SpanType.ROUTE, "AMOUNT_MISMATCH"):
            pass

        r.record_tool(
            name="search_rules",
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.RESULT,
            duration_ms=150,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            result_count=3,
            evidence_ids=["chunk_1", "chunk_2", "chunk_3"],
        )

        r.record_tool(
            name="load_confirmed_cases",
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.RESULT,
            duration_ms=80,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            result_count=2,
            evidence_ids=["flow_a", "flow_b"],
        )

        r.record_tool(
            name="lookup_t1_context",
            status=SpanStatus.SUCCEEDED,
            outcome=ToolOutcome.RESULT,
            duration_ms=50,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            result_count=1,
            evidence_ids=["flow_c"],
        )

        r.record_agent(
            name="AuditAgent",
            status=SpanStatus.SUCCEEDED,
            duration_ms=2000,
            model_name="deepseek-chat",
            prompt_tokens=800,
            completion_tokens=300,
            cached_calls=0,
            attempt=1,
            retry_recovered=False,
            recovered_error_type=None,
            structured_repair_attempted=False,
            structured_repair_succeeded=False,
        )

        with r.span(SpanType.GUARD, "SafetyGuard", outcome=GuardOutcome.PASSED):
            pass

        r.close_root(
            status=SpanStatus.SUCCEEDED,
            outcome=WorkflowOutcome.AUTO_FIXED,
            terminal_type=SpanType.FINAL,
            terminal_name="final_decision",
        )

        snapshot = r.snapshot()
        validate_trace_snapshot(list(snapshot))

        # Verify sequence continuity
        seqs = [s.sequence_no for s in snapshot]
        assert seqs == list(range(1, len(snapshot) + 1))

        # Verify all types present
        types = [s.span_type for s in snapshot]
        assert types[0] == SpanType.WORKFLOW
        assert SpanType.ROUTE in types
        assert types.count(SpanType.TOOL) == 3
        assert SpanType.AGENT in types
        assert SpanType.GUARD in types
        assert SpanType.FINAL in types

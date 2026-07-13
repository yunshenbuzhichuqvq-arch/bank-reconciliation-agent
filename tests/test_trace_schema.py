"""Tests for TraceSpan schema validation — positive and negative cases.

Covers: identity, UTC time, non-negative duration, sequence, type-specific
outcome, token fields, forbidden field rejection, and evidence_ids validation.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 7, 13, 0, 0, 0, tzinfo=timezone.utc)
_LATER = datetime(2026, 7, 13, 0, 0, 1, tzinfo=timezone.utc)


def _base_span(**overrides: object) -> dict:
    """Return a minimal valid WORKFLOW span dict, merged with *overrides*."""
    defaults: dict[str, object] = {
        "trace_id": str(uuid.uuid4()),
        "span_id": str(uuid.uuid4()),
        "parent_span_id": None,
        "user_id": "user_1",
        "task_id": "task_1",
        "flow_id": "flow_1",
        "sequence_no": 1,
        "span_type": SpanType.WORKFLOW,
        "name": "reconciliation_workflow",
        "started_at": _NOW,
        "ended_at": _LATER,
        "duration_ms": 1000,
        "status": SpanStatus.SUCCEEDED,
        "outcome": WorkflowOutcome.AUTO_FIXED,
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


class TestTraceSpanPositive:
    """Valid TraceSpan construction."""

    def test_minimal_workflow_span(self) -> None:
        span = TraceSpan(**_base_span())
        assert span.span_type == SpanType.WORKFLOW
        assert span.schema_version == "1.0"
        assert span.evidence_ids == []

    def test_route_span(self) -> None:
        span = TraceSpan(
            **_base_span(
                span_type=SpanType.ROUTE,
                name="AMOUNT_MISMATCH",
                sequence_no=2,
                outcome=None,
            )
        )
        assert span.span_type == SpanType.ROUTE
        assert span.outcome is None

    def test_tool_span_with_result(self) -> None:
        span = TraceSpan(
            **_base_span(
                span_type=SpanType.TOOL,
                name="search_rules",
                sequence_no=3,
                outcome=ToolOutcome.RESULT,
                attempt=2,
                retry_recovered=True,
                recovered_error_type="TIMEOUT",
                result_count=5,
                evidence_ids=["chunk_abc"],
            )
        )
        assert span.result_count == 5
        assert span.evidence_ids == ["chunk_abc"]
        assert span.retry_recovered is True

    def test_tool_span_empty(self) -> None:
        span = TraceSpan(
            **_base_span(
                span_type=SpanType.TOOL,
                name="load_confirmed_cases",
                sequence_no=3,
                outcome=ToolOutcome.EMPTY,
                result_count=0,
            )
        )
        assert span.outcome == "EMPTY"

    def test_tool_span_failed_null_outcome(self) -> None:
        """Tool technical failure: status=FAILED, outcome=null."""
        span = TraceSpan(
            **_base_span(
                span_type=SpanType.TOOL,
                name="search_rules",
                sequence_no=3,
                status=SpanStatus.FAILED,
                outcome=None,
                error_type="TIMEOUT",
                fallback_reason="TOOL_TIMEOUT",
            )
        )
        assert span.status == SpanStatus.FAILED
        assert span.outcome is None
        assert span.error_type == "TIMEOUT"

    def test_agent_span_with_tokens(self) -> None:
        span = TraceSpan(
            **_base_span(
                span_type=SpanType.AGENT,
                name="AuditAgent",
                sequence_no=4,
                outcome=None,
                model_name="deepseek-chat",
                prompt_tokens=500,
                completion_tokens=200,
                cached_calls=1,
                structured_repair_attempted=True,
                structured_repair_succeeded=True,
            )
        )
        assert span.prompt_tokens == 500
        assert span.completion_tokens == 200
        assert span.cached_calls == 1
        assert span.structured_repair_attempted is True

    def test_guard_passed(self) -> None:
        span = TraceSpan(
            **_base_span(
                span_type=SpanType.GUARD,
                name="SafetyGuard",
                sequence_no=5,
                outcome=GuardOutcome.PASSED,
            )
        )
        assert span.outcome == "PASSED"

    def test_guard_blocked(self) -> None:
        span = TraceSpan(
            **_base_span(
                span_type=SpanType.GUARD,
                name="SafetyGuard",
                sequence_no=5,
                status=SpanStatus.SUCCEEDED,
                outcome=GuardOutcome.BLOCKED,
            )
        )
        assert span.outcome == "BLOCKED"

    def test_final_span(self) -> None:
        span = TraceSpan(
            **_base_span(
                span_type=SpanType.FINAL,
                name="final_decision",
                sequence_no=6,
                outcome=WorkflowOutcome.AUTO_FIXED,
            )
        )
        assert span.span_type == SpanType.FINAL

    def test_fallback_span(self) -> None:
        span = TraceSpan(
            **_base_span(
                span_type=SpanType.FALLBACK,
                name="fallback_human",
                sequence_no=6,
                outcome=WorkflowOutcome.PENDING_HUMAN,
            )
        )
        assert span.span_type == SpanType.FALLBACK

    def test_zero_duration_allowed(self) -> None:
        span = TraceSpan(
            **_base_span(
                started_at=_NOW,
                ended_at=_NOW,
                duration_ms=0,
            )
        )
        assert span.duration_ms == 0

    def test_evidence_ids_empty_list(self) -> None:
        span = TraceSpan(**_base_span(evidence_ids=[]))
        assert span.evidence_ids == []

    def test_evidence_ids_with_values(self) -> None:
        ids = ["chunk_1", "flow_2", "flow_3"]
        span = TraceSpan(**_base_span(evidence_ids=ids))
        assert span.evidence_ids == ids


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------


class TestTraceSpanNegative:
    """Invalid TraceSpan construction must raise ValidationError."""

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(Exception, match="extra"):
            TraceSpan(**_base_span(input_payload={"data": "secret"}))

    def test_extra_arbitrary_attributes(self) -> None:
        with pytest.raises(Exception, match="extra"):
            TraceSpan(**_base_span(attributes={"foo": "bar"}))

    def test_empty_trace_id(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(trace_id=""))

    def test_empty_span_id(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(span_id=""))

    def test_empty_user_id(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(user_id=""))

    def test_empty_task_id(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(task_id=""))

    def test_empty_flow_id(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(flow_id=""))

    def test_empty_name(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(name=""))

    def test_negative_sequence_no(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(sequence_no=0))

    def test_negative_duration(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(duration_ms=-1))

    def test_ended_before_started(self) -> None:
        with pytest.raises(Exception, match="ended_at must not be earlier"):
            TraceSpan(
                **_base_span(
                    started_at=_LATER,
                    ended_at=_NOW,
                )
            )

    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(Exception, match="UTC"):
            TraceSpan(
                **_base_span(
                    started_at=datetime(2026, 7, 13, 0, 0, 0),
                )
            )

    def test_non_utc_timezone_rejected(self) -> None:
        from datetime import timedelta

        cst = timezone(timedelta(hours=8))
        with pytest.raises(Exception, match="UTC"):
            TraceSpan(
                **_base_span(
                    started_at=datetime(2026, 7, 13, 8, 0, 0, tzinfo=cst),
                )
            )

    def test_invalid_span_type(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(span_type="RAG"))

    def test_invalid_status(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(status="RUNNING"))

    def test_invalid_schema_version(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(schema_version="2.0"))

    # -- outcome by type ---------------------------------------------------

    def test_workflow_invalid_outcome(self) -> None:
        with pytest.raises(Exception, match="not allowed"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.WORKFLOW,
                    outcome="RESULT",
                )
            )

    def test_route_non_null_outcome(self) -> None:
        with pytest.raises(Exception, match="requires outcome=null"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.ROUTE,
                    name="AMOUNT_MISMATCH",
                    outcome="PASSED",
                )
            )

    def test_agent_non_null_outcome(self) -> None:
        with pytest.raises(Exception, match="requires outcome=null"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.AGENT,
                    name="AuditAgent",
                    outcome="RESULT",
                    model_name="deepseek-chat",
                )
            )

    def test_tool_invalid_outcome(self) -> None:
        with pytest.raises(Exception, match="not allowed"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.TOOL,
                    name="search_rules",
                    outcome="PASSED",
                )
            )

    def test_guard_invalid_outcome(self) -> None:
        with pytest.raises(Exception, match="not allowed"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.GUARD,
                    name="SafetyGuard",
                    outcome="RESULT",
                )
            )

    def test_final_invalid_outcome(self) -> None:
        with pytest.raises(Exception, match="not allowed"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.FINAL,
                    name="final_decision",
                    outcome="EMPTY",
                )
            )

    def test_fallback_invalid_outcome(self) -> None:
        with pytest.raises(Exception, match="not allowed"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.FALLBACK,
                    name="fallback_human",
                    outcome="PASSED",
                )
            )

    def test_fallback_rejects_auto_fixed_outcome(self) -> None:
        """FALLBACK is a safe hand-off; AUTO_FIXED must never reach it."""
        with pytest.raises(Exception, match="not allowed"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.FALLBACK,
                    name="fallback_human",
                    outcome=WorkflowOutcome.AUTO_FIXED,
                )
            )

    def test_fallback_rejects_unresolved_outcome(self) -> None:
        """FALLBACK only carries PENDING_HUMAN; UNRESOLVED is rejected."""
        with pytest.raises(Exception, match="not allowed"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.FALLBACK,
                    name="fallback_human",
                    outcome=WorkflowOutcome.UNRESOLVED,
                )
            )

    def test_fallback_accepts_pending_human_outcome(self) -> None:
        span = TraceSpan(
            **_base_span(
                span_type=SpanType.FALLBACK,
                name="fallback_human",
                outcome=WorkflowOutcome.PENDING_HUMAN,
            )
        )
        assert span.outcome == "PENDING_HUMAN"

    # -- token field restrictions ------------------------------------------

    def test_non_agent_with_prompt_tokens(self) -> None:
        with pytest.raises(Exception, match="non-AGENT"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.TOOL,
                    name="search_rules",
                    outcome=ToolOutcome.RESULT,
                    prompt_tokens=100,
                )
            )

    def test_non_agent_with_completion_tokens(self) -> None:
        with pytest.raises(Exception, match="non-AGENT"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.TOOL,
                    name="search_rules",
                    outcome=ToolOutcome.RESULT,
                    completion_tokens=100,
                )
            )

    def test_non_agent_with_model_name(self) -> None:
        with pytest.raises(Exception, match="non-AGENT"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.TOOL,
                    name="search_rules",
                    outcome=ToolOutcome.RESULT,
                    model_name="deepseek-chat",
                )
            )

    def test_non_agent_with_cached_calls(self) -> None:
        with pytest.raises(Exception, match="non-AGENT"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.GUARD,
                    name="SafetyGuard",
                    outcome=GuardOutcome.PASSED,
                    cached_calls=3,
                )
            )

    def test_non_agent_with_structured_repair(self) -> None:
        with pytest.raises(Exception, match="non-AGENT"):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.TOOL,
                    name="search_rules",
                    outcome=ToolOutcome.RESULT,
                    structured_repair_attempted=True,
                )
            )

    def test_negative_attempt(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(**_base_span(attempt=0))

    def test_negative_prompt_tokens(self) -> None:
        with pytest.raises(Exception):
            TraceSpan(
                **_base_span(
                    span_type=SpanType.AGENT,
                    name="AuditAgent",
                    outcome=None,
                    model_name="deepseek-chat",
                    prompt_tokens=-1,
                )
            )


# ---------------------------------------------------------------------------
# Enum completeness
# ---------------------------------------------------------------------------


class TestEnumCompleteness:
    """Verify all seven span types and status values exist."""

    def test_seven_span_types(self) -> None:
        assert len(SpanType) == 7

    def test_three_statuses(self) -> None:
        assert len(SpanStatus) == 3

    def test_workflow_outcomes(self) -> None:
        assert set(WorkflowOutcome) == {"AUTO_FIXED", "PENDING_HUMAN", "UNRESOLVED"}

    def test_tool_outcomes(self) -> None:
        assert set(ToolOutcome) == {"RESULT", "EMPTY"}

    def test_guard_outcomes(self) -> None:
        assert set(GuardOutcome) == {"PASSED", "BLOCKED"}

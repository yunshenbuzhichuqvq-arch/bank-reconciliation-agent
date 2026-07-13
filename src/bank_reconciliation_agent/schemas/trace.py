"""Canonical TraceSpan schema and related models.

Defines the single source of truth Pydantic models shared by database
persistence, Replay API and SSE safe projection.  All models use
``extra="forbid"`` to reject unknown fields at validation time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------


class SpanType(StrEnum):
    """Seven closed span types per spec."""

    WORKFLOW = "WORKFLOW"
    ROUTE = "ROUTE"
    TOOL = "TOOL"
    AGENT = "AGENT"
    GUARD = "GUARD"
    FINAL = "FINAL"
    FALLBACK = "FALLBACK"


class SpanStatus(StrEnum):
    """Technical execution result."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkflowOutcome(StrEnum):
    """Outcomes shared by WORKFLOW, FINAL, FALLBACK."""

    AUTO_FIXED = "AUTO_FIXED"
    PENDING_HUMAN = "PENDING_HUMAN"
    UNRESOLVED = "UNRESOLVED"


class ToolOutcome(StrEnum):
    """Outcomes for TOOL spans."""

    RESULT = "RESULT"
    EMPTY = "EMPTY"


class GuardOutcome(StrEnum):
    """Outcomes for GUARD spans."""

    PASSED = "PASSED"
    BLOCKED = "BLOCKED"


# Union of all valid outcome values (used for field constraint).
_ALL_OUTCOMES = {v.value for v in (*WorkflowOutcome, *ToolOutcome, *GuardOutcome)}

# Mapping from span_type to the set of allowed outcome string values.
# ``None`` means outcome must be null.
_ALLOWED_OUTCOMES: dict[SpanType, set[str] | None] = {
    SpanType.WORKFLOW: {v.value for v in WorkflowOutcome},
    SpanType.ROUTE: None,
    SpanType.TOOL: {v.value for v in ToolOutcome},
    SpanType.AGENT: None,
    SpanType.GUARD: {v.value for v in GuardOutcome},
    SpanType.FINAL: {v.value for v in WorkflowOutcome},
    # FALLBACK is a safe hand-off to humans; it may only carry PENDING_HUMAN.
    # AUTO_FIXED / UNRESOLVED on a FALLBACK is rejected at the schema/snapshot
    # boundary so a wrong terminal never reaches the DB, Replay or SSE.
    SpanType.FALLBACK: {WorkflowOutcome.PENDING_HUMAN.value},
}


# ---------------------------------------------------------------------------
# TraceSpan — canonical model
# ---------------------------------------------------------------------------


class TraceSpan(BaseModel):
    """Canonical execution span shared by DB, API and SSE projection.

    ``schema_version`` is fixed at ``"1.0"`` per spec.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")

    # Identity & ordering --------------------------------------------------
    trace_id: str = Field(min_length=1)
    span_id: str = Field(min_length=1)
    parent_span_id: str | None = None
    user_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    flow_id: str = Field(min_length=1)
    sequence_no: Annotated[int, Field(ge=1)]
    span_type: SpanType
    name: str = Field(min_length=1)

    # Time -----------------------------------------------------------------
    started_at: datetime
    ended_at: datetime
    duration_ms: Annotated[int, Field(ge=0)]

    # Status / outcome -----------------------------------------------------
    status: SpanStatus
    outcome: str | None = None

    # Optional safe observation fields -------------------------------------
    attempt: Annotated[int, Field(ge=1)] = 1
    retry_recovered: bool = False
    recovered_error_type: str | None = None
    structured_repair_attempted: bool | None = None
    structured_repair_succeeded: bool | None = None
    model_name: str | None = None
    prompt_tokens: Annotated[int, Field(ge=0)] | None = None
    completion_tokens: Annotated[int, Field(ge=0)] | None = None
    cached_calls: Annotated[int, Field(ge=0)] | None = None
    result_count: Annotated[int, Field(ge=0)] | None = None
    error_type: str | None = None
    fallback_reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    # -- validators --------------------------------------------------------

    @field_validator("started_at", "ended_at")
    @classmethod
    def _must_be_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("timestamp must be UTC")
        return v

    @model_validator(mode="after")
    def _validate_time_order(self) -> TraceSpan:
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must not be earlier than started_at")
        return self

    @model_validator(mode="after")
    def _validate_outcome_by_type(self) -> TraceSpan:
        allowed = _ALLOWED_OUTCOMES[self.span_type]
        if allowed is None:
            # outcome must be null for ROUTE and AGENT
            if self.outcome is not None:
                raise ValueError(
                    f"span_type {self.span_type} requires outcome=null, got '{self.outcome}'"
                )
        else:
            # outcome can be null (e.g. TOOL failure) or one of allowed
            if self.outcome is not None and self.outcome not in allowed:
                raise ValueError(
                    f"outcome '{self.outcome}' not allowed for "
                    f"span_type {self.span_type}; "
                    f"allowed: {sorted(allowed)}"
                )
        return self

    @model_validator(mode="after")
    def _validate_token_fields(self) -> TraceSpan:
        """Only AGENT spans may have non-zero token/model/cache/repair fields."""
        if self.span_type != SpanType.AGENT:
            if self.prompt_tokens is not None and self.prompt_tokens != 0:
                raise ValueError("prompt_tokens must be null or 0 for non-AGENT spans")
            if self.completion_tokens is not None and self.completion_tokens != 0:
                raise ValueError("completion_tokens must be null or 0 for non-AGENT spans")
            if self.cached_calls is not None and self.cached_calls != 0:
                raise ValueError("cached_calls must be null or 0 for non-AGENT spans")
            if self.model_name is not None:
                raise ValueError("model_name must be null for non-AGENT spans")
            if self.structured_repair_attempted is not None:
                raise ValueError("structured_repair_attempted must be null for non-AGENT spans")
            if self.structured_repair_succeeded is not None:
                raise ValueError("structured_repair_succeeded must be null for non-AGENT spans")
        return self


# ---------------------------------------------------------------------------
# Replay API response models (safe projection, never expose user_id)
# ---------------------------------------------------------------------------


class ReplayStatus(StrEnum):
    """Closed enum for the replay availability of a task/flow."""

    AVAILABLE = "AVAILABLE"
    IN_PROGRESS = "IN_PROGRESS"
    TRACE_NOT_AVAILABLE = "TRACE_NOT_AVAILABLE"


class TraceSpanView(BaseModel):
    """Safe, tenant-stripped view of a persisted span for API/SSE.

    Deliberately omits ``user_id`` and database internal ``id``; only
    allowlisted observation fields are exposed.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    task_id: str
    flow_id: str
    sequence_no: int
    span_type: SpanType
    name: str
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    status: SpanStatus
    outcome: str | None = None
    attempt: int = 1
    retry_recovered: bool = False
    recovered_error_type: str | None = None
    structured_repair_attempted: bool | None = None
    structured_repair_succeeded: bool | None = None
    model_name: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_calls: int | None = None
    result_count: int | None = None
    error_type: str | None = None
    fallback_reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_span(cls, span: TraceSpan) -> TraceSpanView:
        return cls(
            schema_version=span.schema_version,
            trace_id=span.trace_id,
            span_id=span.span_id,
            parent_span_id=span.parent_span_id,
            task_id=span.task_id,
            flow_id=span.flow_id,
            sequence_no=span.sequence_no,
            span_type=span.span_type,
            name=span.name,
            started_at=span.started_at,
            ended_at=span.ended_at,
            duration_ms=span.duration_ms,
            status=span.status,
            outcome=span.outcome,
            attempt=span.attempt,
            retry_recovered=span.retry_recovered,
            recovered_error_type=span.recovered_error_type,
            structured_repair_attempted=span.structured_repair_attempted,
            structured_repair_succeeded=span.structured_repair_succeeded,
            model_name=span.model_name,
            prompt_tokens=span.prompt_tokens,
            completion_tokens=span.completion_tokens,
            cached_calls=span.cached_calls,
            result_count=span.result_count,
            error_type=span.error_type,
            fallback_reason=span.fallback_reason,
            evidence_ids=list(span.evidence_ids),
        )


class TraceRunSummary(BaseModel):
    """Condensed per-run summary, most-recent first in the replay response."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    started_at: datetime
    status: SpanStatus
    outcome: str | None = None


class TraceReplayData(BaseModel):
    """Replay payload returned inside ``ApiResponse``."""

    model_config = ConfigDict(extra="forbid")

    replay_status: ReplayStatus
    selected_trace_id: str | None = None
    execution_count: int = 0
    runs: list[TraceRunSummary] = Field(default_factory=list)
    spans: list[TraceSpanView] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

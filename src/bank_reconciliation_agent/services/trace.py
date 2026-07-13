"""Trace persistence service.

Contains:
- ``t_trace_span`` SQLAlchemy Core Table definition.
- ``TraceService`` with tenant-scoped batch insert, query, best-effort
  persistence with failure isolation and process-local metrics.
- ``TraceRecorder`` — flow-scoped, in-memory span collector (TASK-29.2).
- ``NoOpRecorder`` — zero-side-effect substitute when tracing is disabled.
- ``validate_trace_snapshot`` — structural invariant checker.
"""

from __future__ import annotations

import json
import time as _time
import uuid as _uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Lock
from typing import ClassVar, Generator

import structlog

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.schemas.trace import (
    SpanStatus,
    SpanType,
    TraceSpan,
)


# ---------------------------------------------------------------------------
# SQLAlchemy Core Table
# ---------------------------------------------------------------------------

metadata = MetaData()

t_trace_span = Table(
    "t_trace_span",
    metadata,
    Column(
        "id",
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    # Identity & tenant isolation
    Column("trace_id", String(64), nullable=False),
    Column("span_id", String(64), nullable=False),
    Column("parent_span_id", String(64), nullable=True),
    Column("user_id", String(64), nullable=False),
    Column("task_id", String(64), nullable=False),
    Column("flow_id", String(64), nullable=False),
    # Ordering
    Column("sequence_no", Integer, nullable=False),
    # Type & name
    Column("span_type", String(32), nullable=False),
    Column("name", String(128), nullable=False),
    # Time
    Column("started_at", DateTime, nullable=False),
    Column("ended_at", DateTime, nullable=False),
    Column("duration_ms", Integer, nullable=False),
    # Status / outcome
    Column("status", String(32), nullable=False),
    Column("outcome", String(32), nullable=True),
    # Optional safe observation fields
    Column("attempt", Integer, nullable=False, server_default="1"),
    Column("retry_recovered", Integer, nullable=False, server_default="0"),
    Column("recovered_error_type", String(64), nullable=True),
    Column("structured_repair_attempted", Integer, nullable=True),
    Column("structured_repair_succeeded", Integer, nullable=True),
    Column("model_name", String(128), nullable=True),
    Column("prompt_tokens", Integer, nullable=True),
    Column("completion_tokens", Integer, nullable=True),
    Column("cached_calls", Integer, nullable=True),
    Column("result_count", Integer, nullable=True),
    Column("error_type", String(64), nullable=True),
    Column("fallback_reason", String(128), nullable=True),
    Column(
        "evidence_ids",
        JSON().with_variant(Text, "sqlite"),
        nullable=False,
        server_default="[]",
    ),
    Column("schema_version", String(8), nullable=False, server_default="1.0"),
    Column("created_at", DateTime, server_default=func.now()),
    # Unique constraints
    UniqueConstraint("trace_id", "span_id", name="uq_trace_span_id"),
    UniqueConstraint("trace_id", "sequence_no", name="uq_trace_sequence"),
    # Tenant replay query index
    Index("idx_trace_tenant_replay", "user_id", "task_id", "flow_id", "trace_id"),
)


# ---------------------------------------------------------------------------
# TraceService
# ---------------------------------------------------------------------------


class TraceService:
    """Tenant-scoped, append-only Trace persistence."""

    # Process-local best-effort write counters. These are never aggregated
    # across backend/worker processes; ``source`` is fixed to
    # ``runtime_memory`` so callers cannot mistake them for cluster metrics.
    _metrics_lock: ClassVar[Lock] = Lock()
    _write_success_count: ClassVar[int] = 0
    _write_failure_count: ClassVar[int] = 0

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    # -- write -------------------------------------------------------------

    def save_trace(
        self,
        *,
        user_id: str,
        spans: list[TraceSpan],
    ) -> None:
        """Batch-insert a complete Trace within a single transaction.

        The caller must ensure all *spans* belong to the same
        ``trace_id`` / ``task_id`` / ``flow_id`` and that they have
        passed schema and structural validation **before** calling
        this method.

        Raises on duplicate ``span_id`` or ``sequence_no`` within the
        same ``trace_id`` (enforced by DB unique constraints).
        """
        if not spans:
            return
        self._ensure_initialized()
        rows = [self._span_to_row(user_id, s) for s in spans]
        with self._engine.begin() as conn:
            conn.execute(insert(t_trace_span), rows)

    def persist_snapshot(
        self,
        *,
        user_id: str,
        task_id: str,
        flow_id: str,
        spans: tuple[TraceSpan, ...] | list[TraceSpan],
    ) -> bool:
        """Best-effort persist a flow snapshot with full failure isolation.

        Validates structural invariants and writes the whole batch inside a
        single transaction. Any validation or write failure is swallowed after
        recording a process-local counter and a sanitized warning; it never
        raises, so business results stay unchanged. Returns ``True`` on
        success, ``False`` on isolated failure or empty snapshot.
        """
        span_list = list(spans)
        if not span_list:
            return False

        trace_id = span_list[0].trace_id
        try:
            validate_trace_snapshot(span_list)
            self.save_trace(user_id=user_id, spans=span_list)
        except Exception as exc:
            self._record_write_failure()
            _log.warning(
                "trace_write_failed",
                task_id=task_id,
                flow_id=flow_id,
                trace_id=trace_id,
                error_type=type(exc).__name__,
                expected_span_count=len(span_list),
            )
            return False
        self._record_write_success()
        return True

    @classmethod
    def _record_write_success(cls) -> None:
        with cls._metrics_lock:
            cls._write_success_count += 1

    @classmethod
    def _record_write_failure(cls) -> None:
        with cls._metrics_lock:
            cls._write_failure_count += 1

    @classmethod
    def metrics_snapshot(cls) -> dict[str, object]:
        """Return process-local Trace write counters.

        ``source`` is fixed to ``runtime_memory``; these counters are never
        aggregated across backend/worker processes.
        """
        with cls._metrics_lock:
            return {
                "source": "runtime_memory",
                "trace_write_success_count": cls._write_success_count,
                "trace_write_failure_count": cls._write_failure_count,
            }

    # -- read --------------------------------------------------------------

    def list_runs(
        self,
        *,
        user_id: str,
        task_id: str,
        flow_id: str,
    ) -> list[dict[str, object]]:
        """Return summary of each Trace run for a tenant+task+flow.

        Returns rows ordered by most-recent first, each containing:
        ``trace_id``, ``started_at``, ``status``, ``outcome``.
        """
        self._ensure_initialized()
        # Root WORKFLOW span (sequence_no=1) carries run-level summary
        stmt = (
            select(
                t_trace_span.c.trace_id,
                t_trace_span.c.started_at,
                t_trace_span.c.status,
                t_trace_span.c.outcome,
            )
            .where(
                t_trace_span.c.user_id == user_id,
                t_trace_span.c.task_id == task_id,
                t_trace_span.c.flow_id == flow_id,
                t_trace_span.c.sequence_no == 1,
            )
            .order_by(t_trace_span.c.started_at.desc())
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(r) for r in rows]

    def get_spans(
        self,
        *,
        user_id: str,
        task_id: str,
        flow_id: str,
        trace_id: str | None = None,
    ) -> list[TraceSpan]:
        """Return spans for a specific Trace run.

        If *trace_id* is ``None``, selects the most recent run.
        Returns spans ordered by ``sequence_no`` ascending.
        """
        self._ensure_initialized()

        # Resolve trace_id if not provided
        resolved_trace_id = trace_id
        if resolved_trace_id is None:
            runs = self.list_runs(user_id=user_id, task_id=task_id, flow_id=flow_id)
            if not runs:
                return []
            resolved_trace_id = str(runs[0]["trace_id"])

        stmt = (
            select(t_trace_span)
            .where(
                t_trace_span.c.user_id == user_id,
                t_trace_span.c.task_id == task_id,
                t_trace_span.c.flow_id == flow_id,
                t_trace_span.c.trace_id == resolved_trace_id,
            )
            .order_by(t_trace_span.c.sequence_no.asc())
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        return [self._row_to_span(r) for r in rows]

    def count_runs(
        self,
        *,
        user_id: str,
        task_id: str,
        flow_id: str,
    ) -> int:
        """Return the number of Trace runs for a tenant+task+flow."""
        self._ensure_initialized()
        stmt = (
            select(func.count())
            .select_from(t_trace_span)
            .where(
                t_trace_span.c.user_id == user_id,
                t_trace_span.c.task_id == task_id,
                t_trace_span.c.flow_id == flow_id,
                t_trace_span.c.sequence_no == 1,
            )
        )
        with self._engine.connect() as conn:
            return conn.execute(stmt).scalar_one()

    # -- internals ---------------------------------------------------------

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[t_trace_span])
        self._initialized = True

    def _span_to_row(self, user_id: str, span: TraceSpan) -> dict[str, object]:
        """Convert a validated ``TraceSpan`` to a DB insert dict."""
        evidence = span.evidence_ids
        # SQLite needs JSON serialized as text
        if self._engine.dialect.name == "sqlite":
            evidence = json.dumps(evidence, ensure_ascii=False)

        return {
            "trace_id": span.trace_id,
            "span_id": span.span_id,
            "parent_span_id": span.parent_span_id,
            "user_id": user_id,
            "task_id": span.task_id,
            "flow_id": span.flow_id,
            "sequence_no": span.sequence_no,
            "span_type": span.span_type.value,
            "name": span.name,
            "started_at": span.started_at.replace(tzinfo=None),
            "ended_at": span.ended_at.replace(tzinfo=None),
            "duration_ms": span.duration_ms,
            "status": span.status.value,
            "outcome": span.outcome,
            "attempt": span.attempt,
            "retry_recovered": int(span.retry_recovered),
            "recovered_error_type": span.recovered_error_type,
            "structured_repair_attempted": (
                int(span.structured_repair_attempted)
                if span.structured_repair_attempted is not None
                else None
            ),
            "structured_repair_succeeded": (
                int(span.structured_repair_succeeded)
                if span.structured_repair_succeeded is not None
                else None
            ),
            "model_name": span.model_name,
            "prompt_tokens": span.prompt_tokens,
            "completion_tokens": span.completion_tokens,
            "cached_calls": span.cached_calls,
            "result_count": span.result_count,
            "error_type": span.error_type,
            "fallback_reason": span.fallback_reason,
            "evidence_ids": evidence,
            "schema_version": span.schema_version,
        }

    def _row_to_span(self, row: dict[str, object] | object) -> TraceSpan:
        """Reconstruct a ``TraceSpan`` from a DB row mapping."""
        # Accept both dict and RowMapping
        r = dict(row)

        # Parse evidence_ids back from JSON text when needed
        evidence = r.get("evidence_ids", [])
        if isinstance(evidence, str):
            evidence = json.loads(evidence)

        from datetime import timezone

        def _ensure_utc(dt: object) -> object:
            from datetime import datetime as dt_cls

            if isinstance(dt, dt_cls) and dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        return TraceSpan(
            schema_version=str(r.get("schema_version", "1.0")),
            trace_id=str(r["trace_id"]),
            span_id=str(r["span_id"]),
            parent_span_id=r["parent_span_id"],
            user_id=str(r["user_id"]),
            task_id=str(r["task_id"]),
            flow_id=str(r["flow_id"]),
            sequence_no=int(r["sequence_no"]),  # type: ignore[arg-type]
            span_type=str(r["span_type"]),
            name=str(r["name"]),
            started_at=_ensure_utc(r["started_at"]),
            ended_at=_ensure_utc(r["ended_at"]),
            duration_ms=int(r["duration_ms"]),  # type: ignore[arg-type]
            status=str(r["status"]),
            outcome=r.get("outcome"),
            attempt=int(r.get("attempt", 1)),  # type: ignore[arg-type]
            retry_recovered=bool(r.get("retry_recovered", False)),
            recovered_error_type=r.get("recovered_error_type"),
            structured_repair_attempted=(
                bool(r["structured_repair_attempted"])
                if r.get("structured_repair_attempted") is not None
                else None
            ),
            structured_repair_succeeded=(
                bool(r["structured_repair_succeeded"])
                if r.get("structured_repair_succeeded") is not None
                else None
            ),
            model_name=r.get("model_name"),
            prompt_tokens=r.get("prompt_tokens"),
            completion_tokens=r.get("completion_tokens"),
            cached_calls=r.get("cached_calls"),
            result_count=r.get("result_count"),
            error_type=r.get("error_type"),
            fallback_reason=r.get("fallback_reason"),
            evidence_ids=evidence,
        )


# ---------------------------------------------------------------------------
# Structural invariant validation
# ---------------------------------------------------------------------------


def validate_trace_snapshot(spans: list[TraceSpan] | tuple[TraceSpan, ...]) -> None:
    """Validate structural invariants for a complete Trace snapshot.

    Raises ``ValueError`` on any violation.  Per spec:
    - Exactly one WORKFLOW root span with ``sequence_no=1``.
    - Exactly one FINAL or FALLBACK terminal, not both.
    - ``sequence_no`` continuous, unique, starting from 1.
    - All ``parent_span_id`` point to spans within the same Trace.
    - No non-AGENT spans with non-zero token/model/cache/repair fields
      (already enforced by ``TraceSpan`` validator).
    """
    if not spans:
        raise ValueError("Trace snapshot must have at least one root span")

    span_list = list(spans)

    # 1. Exactly one WORKFLOW root span at sequence_no=1
    roots = [s for s in span_list if s.span_type == SpanType.WORKFLOW]
    if len(roots) != 1:
        raise ValueError(f"Trace must have exactly one WORKFLOW root span, found {len(roots)}")
    root = roots[0]
    if root.sequence_no != 1:
        raise ValueError(f"WORKFLOW root span must have sequence_no=1, got {root.sequence_no}")
    if root.parent_span_id is not None:
        raise ValueError("WORKFLOW root span must have parent_span_id=null")

    # 2. Exactly one terminal: FINAL or FALLBACK (not both)
    finals = [s for s in span_list if s.span_type == SpanType.FINAL]
    fallbacks = [s for s in span_list if s.span_type == SpanType.FALLBACK]
    terminal_count = len(finals) + len(fallbacks)
    if terminal_count == 0:
        raise ValueError(
            "Trace must have exactly one terminal span (FINAL or FALLBACK), found none"
        )
    if terminal_count > 1:
        raise ValueError(
            f"Trace must have exactly one terminal span, "
            f"found {len(finals)} FINAL and {len(fallbacks)} FALLBACK"
        )

    # 3. sequence_no: continuous, unique, starting from 1
    seq_numbers = sorted(s.sequence_no for s in span_list)
    expected = list(range(1, len(span_list) + 1))
    if seq_numbers != expected:
        seen = set()
        duplicates = []
        for sn in (s.sequence_no for s in span_list):
            if sn in seen:
                duplicates.append(sn)
            seen.add(sn)
        if duplicates:
            raise ValueError(f"Trace has duplicate sequence numbers: {duplicates}")
        raise ValueError(
            f"Trace sequence numbers must be continuous from 1; "
            f"got {seq_numbers}, expected {expected}"
        )

    # 4. All parent_span_id must point to spans within this Trace
    span_ids = {s.span_id for s in span_list}
    for s in span_list:
        if s.parent_span_id is not None and s.parent_span_id not in span_ids:
            raise ValueError(
                f"Span {s.span_id} has parent_span_id={s.parent_span_id} "
                f"which does not exist in this Trace"
            )

    # 5. All spans must share the same trace_id
    trace_ids = {s.trace_id for s in span_list}
    if len(trace_ids) != 1:
        raise ValueError(f"All spans must share the same trace_id, found {trace_ids}")


# ---------------------------------------------------------------------------
# Internal span builder (in-memory, mutable until snapshot)
# ---------------------------------------------------------------------------

_log = structlog.get_logger("trace.recorder")


class _SpanBuilder:
    """Mutable span state used internally by ``TraceRecorder``."""

    __slots__ = (
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
        "_mono_start",
    )

    def __init__(
        self,
        *,
        trace_id: str,
        span_id: str,
        parent_span_id: str | None,
        user_id: str,
        task_id: str,
        flow_id: str,
        sequence_no: int,
        span_type: SpanType,
        name: str,
        mono_start: float,
    ) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.user_id = user_id
        self.task_id = task_id
        self.flow_id = flow_id
        self.sequence_no = sequence_no
        self.span_type = span_type
        self.name = name
        self.started_at: datetime = datetime.now(timezone.utc)
        self.ended_at: datetime | None = None
        self.duration_ms: int = 0
        self.status: SpanStatus = SpanStatus.SUCCEEDED
        self.outcome: str | None = None
        self._mono_start = mono_start

        # Optional fields — defaults
        self.attempt: int = 1
        self.retry_recovered: bool = False
        self.recovered_error_type: str | None = None
        self.structured_repair_attempted: bool | None = None
        self.structured_repair_succeeded: bool | None = None
        self.model_name: str | None = None
        self.prompt_tokens: int | None = None
        self.completion_tokens: int | None = None
        self.cached_calls: int | None = None
        self.result_count: int | None = None
        self.error_type: str | None = None
        self.fallback_reason: str | None = None
        self.evidence_ids: list[str] = []

    def close(self, *, status: SpanStatus | None = None) -> None:
        mono_end = _time.monotonic()
        self.ended_at = datetime.now(timezone.utc)
        self.duration_ms = max(0, int((mono_end - self._mono_start) * 1000))
        if status is not None:
            self.status = status

    def to_span(self) -> TraceSpan:
        return TraceSpan(
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            user_id=self.user_id,
            task_id=self.task_id,
            flow_id=self.flow_id,
            sequence_no=self.sequence_no,
            span_type=self.span_type,
            name=self.name,
            started_at=self.started_at,
            ended_at=self.ended_at or datetime.now(timezone.utc),
            duration_ms=self.duration_ms,
            status=self.status,
            outcome=self.outcome,
            attempt=self.attempt,
            retry_recovered=self.retry_recovered,
            recovered_error_type=self.recovered_error_type,
            structured_repair_attempted=self.structured_repair_attempted,
            structured_repair_succeeded=self.structured_repair_succeeded,
            model_name=self.model_name,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            cached_calls=self.cached_calls,
            result_count=self.result_count,
            error_type=self.error_type,
            fallback_reason=self.fallback_reason,
            evidence_ids=self.evidence_ids,
        )


# ---------------------------------------------------------------------------
# TraceRecorder — flow-scoped, in-memory span collector
# ---------------------------------------------------------------------------


class TraceRecorder:
    """Flow-scoped recorder that collects spans in memory.

    Creates a new ``trace_id`` and root ``WORKFLOW`` span on init.
    Use ``span()`` context manager for Route/Tool/Agent/Guard nodes.
    Use ``record_tool()`` / ``record_agent()`` for direct projection.
    Call ``close_root()`` when the flow completes, then ``snapshot()``.

    The recorder does **not** write to the database; that is the
    caller's responsibility (via ``TraceService.save_trace``).
    """

    def __init__(
        self,
        *,
        user_id: str,
        task_id: str,
        flow_id: str,
        root_name: str = "reconciliation_workflow",
    ) -> None:
        self._user_id = user_id
        self._task_id = task_id
        self._flow_id = flow_id
        self._trace_id = str(_uuid.uuid4())
        self._sequence_counter = 0
        self._spans: list[_SpanBuilder] = []
        self._parent_stack: list[str] = []  # stack of span_ids
        self._disabled = False
        self._snapshot: tuple[TraceSpan, ...] | None = None

        # Create root WORKFLOW span
        self._root = self._new_builder(SpanType.WORKFLOW, root_name)
        self._parent_stack.append(self._root.span_id)

    @property
    def trace_id(self) -> str:
        return self._trace_id

    # -- context manager for generic spans ---------------------------------

    @contextmanager
    def span(
        self,
        span_type: SpanType,
        name: str,
        *,
        outcome: str | None = None,
        model_name: str | None = None,
    ) -> Generator[_SpanBuilder, None, None]:
        """Context manager for recording a span.

        On normal exit the span status is ``SUCCEEDED``; on exception
        the span is marked ``FAILED`` and the exception re-raised.
        """
        if self._disabled:
            yield _SpanBuilder(
                trace_id="",
                span_id="",
                parent_span_id=None,
                user_id="",
                task_id="",
                flow_id="",
                sequence_no=0,
                span_type=span_type,
                name=name,
                mono_start=_time.monotonic(),
            )
            return

        builder = self._new_builder(span_type, name)
        if outcome is not None:
            builder.outcome = outcome
        if model_name is not None:
            builder.model_name = model_name

        self._parent_stack.append(builder.span_id)
        try:
            yield builder
        except Exception:
            builder.close(status=SpanStatus.FAILED)
            self._parent_stack.pop()
            raise
        else:
            builder.close(status=SpanStatus.SUCCEEDED)
            self._parent_stack.pop()

    # -- direct projection methods -----------------------------------------

    def record_tool(
        self,
        *,
        name: str,
        status: SpanStatus,
        outcome: str | None,
        duration_ms: int | float,
        attempt: int,
        retry_recovered: bool,
        recovered_error_type: str | None,
        result_count: int = 0,
        evidence_ids: list[str] | None = None,
        error_type: str | None = None,
        fallback_reason: str | None = None,
    ) -> None:
        """Record a completed Tool span from safe projection data."""
        if self._disabled:
            return

        builder = self._new_builder(SpanType.TOOL, name)
        builder.status = status
        builder.outcome = outcome
        builder.duration_ms = max(0, int(duration_ms))
        builder.attempt = attempt
        builder.retry_recovered = retry_recovered
        builder.recovered_error_type = recovered_error_type
        builder.result_count = result_count
        builder.evidence_ids = evidence_ids or []
        builder.error_type = error_type
        builder.fallback_reason = fallback_reason

        # Close with pre-set duration (not monotonic, already provided)
        builder.ended_at = datetime.now(timezone.utc)

    def record_agent(
        self,
        *,
        name: str,
        status: SpanStatus,
        duration_ms: int | float,
        model_name: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_calls: int = 0,
        attempt: int = 1,
        retry_recovered: bool = False,
        recovered_error_type: str | None = None,
        structured_repair_attempted: bool = False,
        structured_repair_succeeded: bool = False,
        error_type: str | None = None,
        fallback_reason: str | None = None,
    ) -> None:
        """Record a completed Agent span from LLM summary data."""
        if self._disabled:
            return

        builder = self._new_builder(SpanType.AGENT, name)
        builder.status = status
        builder.duration_ms = max(0, int(duration_ms))
        builder.model_name = model_name
        builder.prompt_tokens = prompt_tokens
        builder.completion_tokens = completion_tokens
        builder.cached_calls = cached_calls
        builder.attempt = attempt
        builder.retry_recovered = retry_recovered
        builder.recovered_error_type = recovered_error_type
        builder.structured_repair_attempted = structured_repair_attempted
        builder.structured_repair_succeeded = structured_repair_succeeded
        builder.error_type = error_type
        builder.fallback_reason = fallback_reason

        builder.ended_at = datetime.now(timezone.utc)

    # -- lifecycle ---------------------------------------------------------

    def close_root(
        self,
        *,
        status: SpanStatus,
        outcome: str,
        terminal_type: SpanType | None = None,
        terminal_name: str | None = None,
    ) -> None:
        """Close the root WORKFLOW span and optionally add a terminal span.

        If ``terminal_type`` is provided (``FINAL`` or ``FALLBACK``), a
        terminal span is appended before closing the root.
        """
        if self._disabled:
            return

        # Add terminal span if requested
        if terminal_type is not None:
            t_name = terminal_name or (
                "final_decision" if terminal_type == SpanType.FINAL else "fallback_human"
            )
            terminal = self._new_builder(terminal_type, t_name)
            terminal.status = status
            terminal.outcome = outcome
            terminal.close()

        # Close root span
        self._root.status = status
        self._root.outcome = outcome
        self._root.close()

    def snapshot(self) -> tuple[TraceSpan, ...]:
        """Return an immutable, validated tuple of ``TraceSpan`` objects.

        The snapshot is cached after first call.  Returns empty tuple
        if the recorder has been disabled.
        """
        if self._disabled:
            return ()

        if self._snapshot is not None:
            return self._snapshot

        spans = tuple(b.to_span() for b in self._spans)
        self._snapshot = spans
        return spans

    def disable(self) -> None:
        """Disable this recorder.

        Used when the recorder itself encounters a fault.  After
        disabling, ``span()`` becomes a no-op pass-through and
        ``snapshot()`` returns an empty tuple.  Business control flow
        is never affected.
        """
        self._disabled = True
        self._spans.clear()
        self._snapshot = ()

    # -- internals ---------------------------------------------------------

    def _next_sequence(self) -> int:
        self._sequence_counter += 1
        return self._sequence_counter

    def _current_parent_id(self) -> str | None:
        return self._parent_stack[-1] if self._parent_stack else None

    def _new_builder(self, span_type: SpanType, name: str) -> _SpanBuilder:
        builder = _SpanBuilder(
            trace_id=self._trace_id,
            span_id=str(_uuid.uuid4()),
            parent_span_id=self._current_parent_id(),
            user_id=self._user_id,
            task_id=self._task_id,
            flow_id=self._flow_id,
            sequence_no=self._next_sequence(),
            span_type=span_type,
            name=name,
            mono_start=_time.monotonic(),
        )
        self._spans.append(builder)
        return builder


# ---------------------------------------------------------------------------
# NoOpRecorder — zero-side-effect substitute
# ---------------------------------------------------------------------------


class NoOpRecorder:
    """Drop-in substitute for ``TraceRecorder`` that does nothing.

    Used when the caller does not provide a recorder or when tracing
    is not desired.  All methods are safe no-ops.
    """

    @property
    def trace_id(self) -> str | None:
        return None

    @contextmanager
    def span(
        self,
        span_type: SpanType,
        name: str,
        *,
        outcome: str | None = None,
        model_name: str | None = None,
    ) -> Generator[None, None, None]:
        yield

    def record_tool(self, **kwargs: object) -> None:
        pass

    def record_agent(self, **kwargs: object) -> None:
        pass

    def close_root(self, **kwargs: object) -> None:
        pass

    def snapshot(self) -> tuple[()]:
        return ()

    def disable(self) -> None:
        pass


trace_service = TraceService()

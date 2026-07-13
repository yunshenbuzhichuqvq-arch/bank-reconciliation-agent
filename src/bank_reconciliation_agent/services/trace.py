"""Trace persistence service.

Contains:
- ``t_trace_span`` SQLAlchemy Core Table definition.
- ``TraceService`` with tenant-scoped batch insert and query methods.
- Legacy ``TraceWriter`` (to be removed in TASK-29.3).
"""

from __future__ import annotations

import json
from pathlib import Path

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

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.schemas.trace import TraceSpan


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
# Legacy TraceWriter — retained temporarily for TASK-29.1.
# Must be removed in TASK-29.3.
# ---------------------------------------------------------------------------


class TraceWriter:
    def __init__(self, trace_dir: str | None = None) -> None:
        self.trace_dir = Path(trace_dir or settings.trace_dir)

    def write(self, *, task_id: str, flow_id: str, payload: dict) -> Path:
        task_trace_dir = self.trace_dir / task_id
        task_trace_dir.mkdir(parents=True, exist_ok=True)
        trace_path = task_trace_dir / f"{flow_id}.json"
        trace_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return trace_path


trace_writer = TraceWriter()

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    delete,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.services.memory.engine import get_memory_engine


metadata = MetaData()

short_term_memory_table = Table(
    "t_short_term_memory",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("thread_id", String(64), nullable=False),
    Column("queue_id", Integer, nullable=False),
    Column("flow_id", String(64), nullable=True),
    Column("error_type", String(32), nullable=False),
    Column("risk_level", String(16), nullable=True),
    Column("decision", String(32), nullable=False),
    Column("confidence", Numeric(5, 4), nullable=False),
    Column("expires_at", DateTime, nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
    Index("idx_short_term_thread_created", "thread_id", "created_at"),
    Index("idx_short_term_expires_at", "expires_at"),
)


class ShortTermMemoryService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_memory_engine()
        self._initialized = False

    def append(
        self,
        *,
        thread_id: str,
        queue_id: int,
        flow_id: str | None = None,
        error_type: str,
        risk_level: str | None = None,
        decision: str,
        confidence: Decimal,
        expires_at: datetime,
    ) -> None:
        self._ensure_initialized()
        values = {
            "thread_id": thread_id,
            "queue_id": queue_id,
            "flow_id": flow_id,
            "error_type": error_type,
            "risk_level": risk_level,
            "decision": decision,
            "confidence": confidence,
            "expires_at": expires_at,
        }
        with self._engine.begin() as connection:
            connection.execute(insert(short_term_memory_table).values(values))

    def recent(self, *, thread_id: str, limit: int = 10) -> list[dict[str, object]]:
        self._ensure_initialized()
        statement = (
            select(short_term_memory_table)
            .where(
                short_term_memory_table.c.thread_id == thread_id,
                self._not_expired_clause(),
            )
            .order_by(short_term_memory_table.c.created_at.desc(), short_term_memory_table.c.id.desc())
            .limit(limit)
        )
        with self._engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def count(self, *, thread_id: str) -> int:
        self._ensure_initialized()
        statement = (
            select(func.count())
            .select_from(short_term_memory_table)
            .where(
                short_term_memory_table.c.thread_id == thread_id,
                self._not_expired_clause(),
            )
        )
        with self._engine.connect() as connection:
            return connection.execute(statement).scalar_one()

    def delete_by_queue(self, *, thread_id: str, queue_id: int) -> int:
        self._ensure_initialized()
        statement = delete(short_term_memory_table).where(
            short_term_memory_table.c.thread_id == thread_id,
            short_term_memory_table.c.queue_id == queue_id,
        )
        with self._engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount or 0

    def purge_expired(self) -> int:
        self._ensure_initialized()
        statement = delete(short_term_memory_table).where(
            short_term_memory_table.c.expires_at < datetime.utcnow()
        )
        with self._engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount or 0

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[short_term_memory_table])
        self._initialized = True

    def _not_expired_clause(self):
        return short_term_memory_table.c.expires_at >= datetime.utcnow()


short_term_memory_service = ShortTermMemoryService()

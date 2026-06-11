from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.services.memory.engine import get_memory_engine


metadata = MetaData()

summary_memory_table = Table(
    "t_summary_memory",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("thread_id", String(64), nullable=False, unique=True),
    Column("summary_text", Text, nullable=False),
    Column("compressed_count", Integer, nullable=False, default=0),
    Column("last_compressed_at", DateTime, nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now()),
)


class SummaryMemoryService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_memory_engine()
        self._initialized = False

    def get(self, *, thread_id: str) -> dict[str, object] | None:
        self._ensure_initialized()
        statement = select(summary_memory_table).where(summary_memory_table.c.thread_id == thread_id)
        with self._engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        if row is None:
            return None
        return dict(row)

    def upsert(
        self,
        *,
        thread_id: str,
        summary_text: str,
        compressed_count: int,
        last_compressed_at: datetime,
    ) -> None:
        self._ensure_initialized()
        values = {
            "thread_id": thread_id,
            "summary_text": summary_text,
            "compressed_count": compressed_count,
            "last_compressed_at": last_compressed_at,
        }
        with self._engine.begin() as connection:
            existing_id = connection.execute(
                select(summary_memory_table.c.id).where(summary_memory_table.c.thread_id == thread_id)
            ).scalar_one_or_none()
            if existing_id is None:
                connection.execute(insert(summary_memory_table).values(values))
                return
            connection.execute(
                update(summary_memory_table)
                .where(summary_memory_table.c.id == existing_id)
                .values(
                    summary_text=summary_text,
                    compressed_count=compressed_count,
                    last_compressed_at=last_compressed_at,
                )
            )

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[summary_memory_table])
        self._initialized = True


summary_memory_service = SummaryMemoryService()

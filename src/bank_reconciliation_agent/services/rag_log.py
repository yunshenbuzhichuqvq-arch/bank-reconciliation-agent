from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    delete,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.schemas.rag import RagSearchItem


metadata = MetaData()

rag_retrieval_log_table = Table(
    "t_rag_retrieval_log",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("task_id", String(64), nullable=False),
    Column("queue_id", BigInteger, nullable=True),
    Column("query_text", Text, nullable=False),
    Column("top_k", Integer, nullable=False),
    Column("best_score", Numeric(8, 4), nullable=True),
    Column("sources", JSON, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Index("idx_rag_task_queue", "task_id", "queue_id"),
)


class RagLogService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def replace_task_rows(self, task_id: str, rows: list[dict[str, object]]) -> None:
        """覆盖写入同一任务上传处理期间产生的 RAG 检索记录。"""
        self._ensure_initialized()
        with self._engine.begin() as connection:
            connection.execute(
                delete(rag_retrieval_log_table).where(rag_retrieval_log_table.c.task_id == task_id)
            )
            if rows:
                connection.execute(insert(rag_retrieval_log_table), rows)

    def build_row(
        self,
        *,
        task_id: str,
        query_text: str,
        top_k: int,
        items: list[RagSearchItem],
    ) -> dict[str, object]:
        best_score = max((Decimal(str(item.score)) for item in items), default=None)
        return {
            "task_id": task_id,
            "queue_id": None,
            "query_text": query_text,
            "top_k": top_k,
            "best_score": best_score,
            "sources": [item.chunk_id for item in items],
        }

    def count_rows(self, task_id: str) -> int:
        self._ensure_initialized()
        statement = (
            select(func.count())
            .select_from(rag_retrieval_log_table)
            .where(rag_retrieval_log_table.c.task_id == task_id)
        )
        with self._engine.connect() as connection:
            return connection.execute(statement).scalar_one()

    def get_latest_row(self, task_id: str, query_marker: str) -> dict[str, object] | None:
        self._ensure_initialized()
        statement = (
            select(rag_retrieval_log_table)
            .where(
                rag_retrieval_log_table.c.task_id == task_id,
                rag_retrieval_log_table.c.query_text.contains(query_marker),
            )
            .order_by(rag_retrieval_log_table.c.id.desc())
            .limit(1)
        )
        with self._engine.connect() as connection:
            row = connection.execute(statement).mappings().first()

        if row is None:
            return None
        result = dict(row)
        if isinstance(result["sources"], str):
            result["sources"] = json.loads(result["sources"])
        return result

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[rag_retrieval_log_table])
        self._initialized = True


rag_log_service = RagLogService()

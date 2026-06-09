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
from bank_reconciliation_agent.rag.scoring import representative_score
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse


metadata = MetaData()

rag_retrieval_log_table = Table(
    "t_rag_retrieval_log",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("task_id", String(64), nullable=False),
    Column("user_id", String(64), nullable=False, server_default="demo_user"),
    Column("scenario_type", String(32), nullable=False, server_default="BANK_ENTERPRISE"),
    Column("queue_id", BigInteger, nullable=True),
    Column("query_text", Text, nullable=False),
    Column("top_k", Integer, nullable=False),
    Column("best_score", Numeric(8, 4), nullable=True),
    Column("sources", JSON, nullable=True),
    Column("rewritten_query", Text, nullable=True),
    Column("dense_score", Numeric(8, 4), nullable=True),
    Column("bm25_score", Numeric(8, 4), nullable=True),
    Column("reranker_score", Numeric(8, 4), nullable=True),
    Column("fusion_rank", Integer, nullable=True),
    Column("selected_chunk_id", String(128), nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Index("idx_rag_task_queue", "task_id", "queue_id"),
)


class RagLogService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def replace_task_rows(
        self,
        *,
        user_id: str,
        task_id: str,
        rows: list[dict[str, object]],
    ) -> None:
        """覆盖写入同一任务上传处理期间产生的 RAG 检索记录。"""
        self._ensure_initialized()
        with self._engine.begin() as connection:
            connection.execute(
                delete(rag_retrieval_log_table).where(
                    rag_retrieval_log_table.c.user_id == user_id,
                    rag_retrieval_log_table.c.task_id == task_id,
                )
            )
            if rows:
                connection.execute(
                    insert(rag_retrieval_log_table),
                    [dict(row, user_id=user_id) for row in rows],
                )

    def build_row(
        self,
        *,
        user_id: str,
        task_id: str,
        query_text: str,
        top_k: int,
        items: list[RagSearchItem],
        response: RagSearchResponse | None = None,
    ) -> dict[str, object]:
        selected_item = items[0] if items else None
        best_score = max(
            (
                Decimal(str(score))
                for item in items
                if (score := representative_score(item)) is not None
            ),
            default=None,
        )
        return {
            "user_id": user_id,
            "task_id": task_id,
            "queue_id": None,
            "query_text": query_text,
            "top_k": top_k,
            "best_score": best_score,
            "sources": [item.chunk_id for item in items],
            "rewritten_query": response.rewritten_query if response is not None else None,
            "dense_score": _to_decimal(selected_item.dense_score) if selected_item is not None else None,
            "bm25_score": _to_decimal(selected_item.bm25_score) if selected_item is not None else None,
            "reranker_score": (
                _to_decimal(selected_item.reranker_score) if selected_item is not None else None
            ),
            "fusion_rank": selected_item.fusion_rank if selected_item is not None else None,
            "selected_chunk_id": selected_item.chunk_id if selected_item is not None else None,
        }

    def count_rows(self, *, user_id: str, task_id: str) -> int:
        self._ensure_initialized()
        statement = (
            select(func.count())
            .select_from(rag_retrieval_log_table)
            .where(
                rag_retrieval_log_table.c.user_id == user_id,
                rag_retrieval_log_table.c.task_id == task_id,
            )
        )
        with self._engine.connect() as connection:
            return connection.execute(statement).scalar_one()

    def get_latest_row(
        self,
        *,
        user_id: str,
        task_id: str,
        query_marker: str,
    ) -> dict[str, object] | None:
        self._ensure_initialized()
        statement = (
            select(rag_retrieval_log_table)
            .where(
                rag_retrieval_log_table.c.user_id == user_id,
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


def _to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    MetaData,
    Numeric,
    String,
    Table,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.services.memory.engine import get_memory_engine


metadata = MetaData()

long_term_memory_table = Table(
    "t_long_term_memory",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("error_type", String(32), nullable=False),
    Column("exception_branch", String(32), nullable=True),
    Column("flow_id", String(64), nullable=False),
    Column("bank_amount", Numeric(18, 2), nullable=True),
    Column("clear_amount", Numeric(18, 2), nullable=True),
    Column("amount_diff", Numeric(18, 2), nullable=True),
    Column("summary_keywords", JSON, nullable=False),
    Column("human_decision", String(32), nullable=False),
    Column("ai_suggestion", String(32), nullable=False),
    Column("ai_confidence", Numeric(5, 4), nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
    Index("idx_long_term_user_error", "user_id", "error_type"),
)


class LongTermMemoryService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_memory_engine()
        self._initialized = False

    def append(
        self,
        *,
        user_id: str,
        error_type: str,
        exception_branch: str | None,
        flow_id: str,
        bank_amount: Decimal | None,
        clear_amount: Decimal | None,
        amount_diff: Decimal | None,
        summary_keywords: list[str],
        human_decision: str,
        ai_suggestion: str,
        ai_confidence: Decimal,
    ) -> None:
        self._ensure_initialized()
        values = {
            "user_id": user_id,
            "error_type": error_type,
            "exception_branch": exception_branch,
            "flow_id": flow_id,
            "bank_amount": bank_amount,
            "clear_amount": clear_amount,
            "amount_diff": amount_diff,
            "summary_keywords": summary_keywords,
            "human_decision": human_decision,
            "ai_suggestion": ai_suggestion,
            "ai_confidence": ai_confidence,
        }
        with self._engine.begin() as connection:
            connection.execute(insert(long_term_memory_table).values(values))

    def recall(
        self,
        *,
        user_id: str,
        error_type: str,
        keywords: list[str],
        limit: int = 5,
    ) -> list[dict[str, object]]:
        self._ensure_initialized()
        statement = (
            select(long_term_memory_table)
            .where(
                long_term_memory_table.c.user_id == user_id,
                long_term_memory_table.c.error_type == error_type,
            )
            .order_by(long_term_memory_table.c.created_at.desc(), long_term_memory_table.c.id.desc())
        )
        with self._engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        query_keywords = {keyword.lower() for keyword in keywords}
        ranked_rows = sorted(
            (dict(row) for row in rows),
            key=lambda row: (
                self._keyword_overlap(row["summary_keywords"], query_keywords),
                row["id"],
            ),
            reverse=True,
        )
        return ranked_rows[:limit]

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[long_term_memory_table])
        self._initialized = True

    def _keyword_overlap(self, value: object, query_keywords: set[str]) -> int:
        if not query_keywords:
            return 0
        if not isinstance(value, list):
            return 0
        row_keywords = {str(keyword).lower() for keyword in value}
        return len(row_keywords & query_keywords)


long_term_memory_service = LongTermMemoryService()

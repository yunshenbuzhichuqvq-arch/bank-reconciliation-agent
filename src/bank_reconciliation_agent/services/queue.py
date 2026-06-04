from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.db.session import get_engine


metadata = MetaData()

reconciliation_queue_table = Table(
    "t_reconciliation_queue",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("task_id", String(64), nullable=False),
    Column("scenario_type", String(32), nullable=False, default="BANK_ENTERPRISE"),
    Column("source_a_transaction_id", BigInteger, nullable=True),
    Column("source_b_transaction_id", BigInteger, nullable=True),
    Column("error_type", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("risk_level", String(16), nullable=False, default="LOW"),
    Column("retry_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now()),
    Index("idx_user_task_status", "user_id", "task_id", "status"),
    Index("idx_user_error_type", "user_id", "error_type"),
)


class QueueService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def replace_task_rows(
        self,
        task_id: str,
        rows: list[dict[str, object]],
        user_id: str = "demo_user",
    ) -> None:
        """覆盖写入同一用户/任务的异常处理队列。"""
        self._ensure_initialized()
        with self._engine.begin() as connection:
            connection.execute(
                delete(reconciliation_queue_table).where(
                    reconciliation_queue_table.c.user_id == user_id,
                    reconciliation_queue_table.c.task_id == task_id,
                )
            )
            if rows:
                connection.execute(insert(reconciliation_queue_table), rows)

    def count_rows(self, task_id: str, user_id: str = "demo_user") -> int:
        self._ensure_initialized()
        statement = (
            select(func.count())
            .select_from(reconciliation_queue_table)
            .where(
                reconciliation_queue_table.c.user_id == user_id,
                reconciliation_queue_table.c.task_id == task_id,
            )
        )
        with self._engine.connect() as connection:
            return connection.execute(statement).scalar_one()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[reconciliation_queue_table])
        self._initialized = True


queue_service = QueueService()

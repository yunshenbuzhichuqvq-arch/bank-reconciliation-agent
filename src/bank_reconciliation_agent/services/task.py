from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

from sqlalchemy.engine import Connection

from bank_reconciliation_agent.db.session import get_engine


metadata = MetaData()

reconciliation_task_table = Table(
    "t_reconciliation_task",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("task_id", String(64), nullable=False),
    Column("user_id", String(64), nullable=False, server_default="demo_user"),
    Column("scenario_type", String(32), nullable=False, server_default="BANK_ENTERPRISE"),
    Column("batch_id", String(64), nullable=True),
    Column("task_name", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("total_bank_rows", Integer, nullable=False, default=0),
    Column("total_clear_rows", Integer, nullable=False, default=0),
    Column("auto_fixed_rows", Integer, nullable=False, default=0),
    Column("pending_ai_rows", Integer, nullable=False, default=0),
    Column("pending_human_rows", Integer, nullable=False, default=0),
    Column("unresolved_rows", Integer, nullable=False, default=0),
    Column("ai_processed_rows", Integer, nullable=False, server_default="0"),
    Column("fallback_l2_rows", Integer, nullable=False, server_default="0"),
    Column("fallback_l3_rows", Integer, nullable=False, server_default="0"),
    Column("total_llm_tokens", Integer, nullable=False, server_default="0"),
    Column("total_llm_cost", Numeric(10, 4), nullable=False, server_default="0.0000"),
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now()),
    UniqueConstraint("user_id", "task_id", name="uk_task_user_task"),
    Index("idx_status_created", "status", "created_at"),
)


class ReconciliationTaskRow(NamedTuple):
    task_id: str
    status: str
    total_bank_rows: int
    total_clear_rows: int
    auto_fixed_rows: int
    pending_ai_rows: int
    pending_human_rows: int
    unresolved_rows: int
    ai_processed_rows: int
    fallback_l2_rows: int
    fallback_l3_rows: int
    total_llm_tokens: int
    total_llm_cost: Decimal


class TaskService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def replace_task(
        self,
        *,
        user_id: str,
        task_id: str,
        total_bank_rows: int,
        total_clear_rows: int,
        auto_fixed_rows: int,
        pending_ai_rows: int,
        pending_human_rows: int,
        connection: Connection | None = None,
    ) -> None:
        """写入上传后的任务状态；同 task_id 重试时覆盖旧任务统计。"""
        self._ensure_initialized()
        unresolved_rows = pending_ai_rows + pending_human_rows

        def _execute(conn: Connection) -> None:
            conn.execute(
                delete(reconciliation_task_table).where(
                    reconciliation_task_table.c.user_id == user_id,
                    reconciliation_task_table.c.task_id == task_id
                )
            )
            conn.execute(
                insert(reconciliation_task_table).values(
                    user_id=user_id,
                    task_id=task_id,
                    task_name=f"{task_id} reconciliation",
                    status="UPLOADED",
                    total_bank_rows=total_bank_rows,
                    total_clear_rows=total_clear_rows,
                    auto_fixed_rows=auto_fixed_rows,
                    pending_ai_rows=pending_ai_rows,
                    pending_human_rows=pending_human_rows,
                    unresolved_rows=unresolved_rows,
                )
            )

        if connection is not None:
            _execute(connection)
        else:
            with self._engine.begin() as conn:
                _execute(conn)

    def update_status(self, *, user_id: str, task_id: str, status: str) -> bool:
        self._ensure_initialized()
        with self._engine.begin() as connection:
            result = connection.execute(
                update(reconciliation_task_table)
                .where(
                    reconciliation_task_table.c.user_id == user_id,
                    reconciliation_task_table.c.task_id == task_id,
                )
                .values(status=status)
            )
        return result.rowcount > 0

    def increment_ai_stats(
        self,
        *,
        user_id: str,
        task_id: str,
        ai_processed_rows: int,
        fallback_l2_rows: int,
        fallback_l3_rows: int,
        total_llm_tokens: int,
        total_llm_cost: Decimal,
        connection: Connection | None = None,
    ) -> None:
        self._ensure_initialized()

        def _execute(conn: Connection) -> None:
            conn.execute(
                update(reconciliation_task_table)
                .where(
                    reconciliation_task_table.c.user_id == user_id,
                    reconciliation_task_table.c.task_id == task_id,
                )
                .values(
                    ai_processed_rows=(
                        reconciliation_task_table.c.ai_processed_rows + ai_processed_rows
                    ),
                    fallback_l2_rows=(
                        reconciliation_task_table.c.fallback_l2_rows + fallback_l2_rows
                    ),
                    fallback_l3_rows=(
                        reconciliation_task_table.c.fallback_l3_rows + fallback_l3_rows
                    ),
                    total_llm_tokens=(
                        reconciliation_task_table.c.total_llm_tokens + total_llm_tokens
                    ),
                    total_llm_cost=(
                        reconciliation_task_table.c.total_llm_cost + total_llm_cost
                    ),
                    updated_at=func.now(),
                )
            )

        if connection is not None:
            _execute(connection)
        else:
            with self._engine.begin() as conn:
                _execute(conn)

    def get(self, *, user_id: str, task_id: str) -> ReconciliationTaskRow | None:
        self._ensure_initialized()
        statement = select(reconciliation_task_table).where(
            reconciliation_task_table.c.user_id == user_id,
            reconciliation_task_table.c.task_id == task_id
        )
        with self._engine.connect() as connection:
            row = connection.execute(statement).mappings().first()

        if row is None:
            return None
        return ReconciliationTaskRow(
            task_id=row["task_id"],
            status=row["status"],
            total_bank_rows=row["total_bank_rows"],
            total_clear_rows=row["total_clear_rows"],
            auto_fixed_rows=row["auto_fixed_rows"],
            pending_ai_rows=row["pending_ai_rows"],
            pending_human_rows=row["pending_human_rows"],
            unresolved_rows=row["unresolved_rows"],
            ai_processed_rows=row["ai_processed_rows"],
            fallback_l2_rows=row["fallback_l2_rows"],
            fallback_l3_rows=row["fallback_l3_rows"],
            total_llm_tokens=row["total_llm_tokens"],
            total_llm_cost=Decimal(str(row["total_llm_cost"])),
        )

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[reconciliation_task_table])
        self._initialized = True


task_service = TaskService()

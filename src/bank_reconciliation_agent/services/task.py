from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine

from bank_reconciliation_agent.db.session import get_engine


metadata = MetaData()

reconciliation_task_table = Table(
    "t_reconciliation_task",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("task_id", String(64), nullable=False),
    Column("task_name", String(128), nullable=False),
    Column("scenario_type", String(32), nullable=False, default="BANK_ENTERPRISE"),
    Column("status", String(32), nullable=False),
    Column("total_source_a_rows", Integer, nullable=False, default=0),
    Column("total_source_b_rows", Integer, nullable=False, default=0),
    Column("auto_fixed_rows", Integer, nullable=False, default=0),
    Column("pending_ai_rows", Integer, nullable=False, default=0),
    Column("pending_human_rows", Integer, nullable=False, default=0),
    Column("unresolved_rows", Integer, nullable=False, default=0),
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now()),
    UniqueConstraint("user_id", "task_id", name="uk_user_task"),
    Index("idx_user_scenario", "user_id", "scenario_type"),
    Index("idx_user_status", "user_id", "status"),
)


class ReconciliationTaskRow(NamedTuple):
    task_id: str
    status: str
    scenario_type: str
    total_source_a_rows: int
    total_source_b_rows: int
    auto_fixed_rows: int
    pending_ai_rows: int
    pending_human_rows: int
    unresolved_rows: int


class TaskService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def replace_task(
        self,
        *,
        task_id: str,
        total_source_a_rows: int,
        total_source_b_rows: int,
        auto_fixed_rows: int,
        pending_ai_rows: int,
        pending_human_rows: int,
        user_id: str = "demo_user",
        scenario_type: str = "BANK_ENTERPRISE",
        connection: Connection | None = None,
    ) -> None:
        """写入上传后的任务状态；同 user/task 重试时覆盖旧任务统计。"""
        self._ensure_initialized()
        unresolved_rows = pending_ai_rows + pending_human_rows

        def _execute(conn: Connection) -> None:
            conn.execute(
                delete(reconciliation_task_table).where(
                    reconciliation_task_table.c.user_id == user_id,
                    reconciliation_task_table.c.task_id == task_id,
                )
            )
            conn.execute(
                insert(reconciliation_task_table).values(
                    user_id=user_id,
                    task_id=task_id,
                    task_name=f"{task_id} reconciliation",
                    scenario_type=scenario_type,
                    status="UPLOADED",
                    total_source_a_rows=total_source_a_rows,
                    total_source_b_rows=total_source_b_rows,
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

    def update_status(self, task_id: str, status: str, user_id: str = "demo_user") -> bool:
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

    def get(self, task_id: str, user_id: str = "demo_user") -> ReconciliationTaskRow | None:
        self._ensure_initialized()
        statement = select(reconciliation_task_table).where(
            reconciliation_task_table.c.user_id == user_id,
            reconciliation_task_table.c.task_id == task_id,
        )
        with self._engine.connect() as connection:
            row = connection.execute(statement).mappings().first()

        if row is None:
            return None
        return ReconciliationTaskRow(
            task_id=row["task_id"],
            status=row["status"],
            scenario_type=row["scenario_type"],
            total_source_a_rows=row["total_source_a_rows"],
            total_source_b_rows=row["total_source_b_rows"],
            auto_fixed_rows=row["auto_fixed_rows"],
            pending_ai_rows=row["pending_ai_rows"],
            pending_human_rows=row["pending_human_rows"],
            unresolved_rows=row["unresolved_rows"],
        )

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[reconciliation_task_table])
        self._initialized = True


task_service = TaskService()

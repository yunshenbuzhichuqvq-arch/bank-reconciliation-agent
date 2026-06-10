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
from sqlalchemy.engine import Connection
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.db.session import get_engine


metadata = MetaData()

reconciliation_queue_table = Table(
    "t_reconciliation_queue",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("task_id", String(64), nullable=False),
    Column("user_id", String(64), nullable=False, server_default="demo_user"),
    Column("scenario_type", String(32), nullable=False, server_default="BANK_ENTERPRISE"),
    Column("flow_id", String(64), nullable=False),
    Column("bank_transaction_id", BigInteger, nullable=True),
    Column("clear_transaction_id", BigInteger, nullable=True),
    Column("error_type", String(32), nullable=False),
    Column("exception_branch", String(32), nullable=True),
    Column("status", String(32), nullable=False),
    Column("risk_level", String(16), nullable=False, default="LOW"),
    Column("retry_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now()),
    Index("idx_queue_task_flow", "task_id", "flow_id"),
    Index("idx_queue_task_status", "task_id", "status"),
    Index("idx_queue_error_type", "error_type"),
    Index("idx_error_branch", "error_type", "exception_branch"),
)


class QueueService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def replace_task_rows(
        self,
        *,
        user_id: str,
        task_id: str,
        scenario_type: str,
        rows: list[dict[str, object]],
        connection: Connection | None = None,
    ) -> None:
        """覆盖写入同一任务的异常处理队列。"""
        self._ensure_initialized()
        def _execute(conn: Connection) -> None:
            conn.execute(
                delete(reconciliation_queue_table).where(
                    reconciliation_queue_table.c.user_id == user_id,
                    reconciliation_queue_table.c.task_id == task_id
                )
            )
            if rows:
                conn.execute(
                    insert(reconciliation_queue_table),
                    [dict(row, user_id=user_id, scenario_type=scenario_type) for row in rows],
                )

        if connection is not None:
            _execute(connection)
        else:
            with self._engine.begin() as conn:
                _execute(conn)

    def count_rows(self, *, user_id: str, task_id: str) -> int:
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

    def get_row(self, *, user_id: str, task_id: str, flow_id: str) -> dict[str, object] | None:
        self._ensure_initialized()
        statement = select(reconciliation_queue_table).where(
            reconciliation_queue_table.c.user_id == user_id,
            reconciliation_queue_table.c.task_id == task_id,
            reconciliation_queue_table.c.flow_id == flow_id,
        )
        with self._engine.connect() as connection:
            row = connection.execute(statement).mappings().first()

        if row is None:
            return None
        return dict(row)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[reconciliation_queue_table])
        self._initialized = True


queue_service = QueueService()

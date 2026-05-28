from __future__ import annotations

from decimal import Decimal

import pandas as pd
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
    delete,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.db.session import get_engine


metadata = MetaData()

bank_transaction_table = Table(
    "t_bank_transaction",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("task_id", String(64), nullable=False),
    Column("flow_id", String(64), nullable=True),
    Column("account_no_masked", String(64), nullable=True),
    Column("customer_name_masked", String(64), nullable=True),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("trade_time", DateTime, nullable=False),
    Column("summary", String(255), nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Index("idx_bank_task_flow", "task_id", "flow_id"),
    Index("idx_bank_task_time", "task_id", "trade_time"),
)

clear_transaction_table = Table(
    "t_clear_transaction",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("task_id", String(64), nullable=False),
    Column("flow_id", String(64), nullable=True),
    Column("channel", String(32), nullable=True),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("trade_time", DateTime, nullable=False),
    Column("summary", String(255), nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Index("idx_clear_task_flow", "task_id", "flow_id"),
    Index("idx_clear_task_time", "task_id", "trade_time"),
)


class TransactionService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def replace_task_rows(
        self,
        task_id: str,
        bank_df: pd.DataFrame,
        clear_df: pd.DataFrame,
    ) -> None:
        """覆盖写入同一对账任务的银行端和清算端标准流水。"""
        self._ensure_initialized()
        with self._engine.begin() as connection:
            connection.execute(
                delete(bank_transaction_table).where(bank_transaction_table.c.task_id == task_id)
            )
            connection.execute(
                delete(clear_transaction_table).where(
                    clear_transaction_table.c.task_id == task_id
                )
            )
            if not bank_df.empty:
                connection.execute(
                    insert(bank_transaction_table),
                    [self._to_bank_insert_values(task_id, row) for row in bank_df.to_dict("records")],
                )
            if not clear_df.empty:
                connection.execute(
                    insert(clear_transaction_table),
                    [
                        self._to_clear_insert_values(task_id, row)
                        for row in clear_df.to_dict("records")
                    ],
                )

    def count_bank_rows(self, task_id: str) -> int:
        return self._count_rows(bank_transaction_table, task_id)

    def count_clear_rows(self, task_id: str) -> int:
        return self._count_rows(clear_transaction_table, task_id)

    def get_bank_row(self, task_id: str, flow_id: str) -> dict[str, object] | None:
        return self._get_row(bank_transaction_table, task_id, flow_id)

    def get_clear_row(self, task_id: str, flow_id: str) -> dict[str, object] | None:
        return self._get_row(clear_transaction_table, task_id, flow_id)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[bank_transaction_table, clear_transaction_table])
        self._initialized = True

    def _count_rows(self, table: Table, task_id: str) -> int:
        self._ensure_initialized()
        statement = select(func.count()).select_from(table).where(table.c.task_id == task_id)
        with self._engine.connect() as connection:
            return connection.execute(statement).scalar_one()

    def _get_row(self, table: Table, task_id: str, flow_id: str) -> dict[str, object] | None:
        self._ensure_initialized()
        statement = select(table).where(table.c.task_id == task_id, table.c.flow_id == flow_id)
        with self._engine.connect() as connection:
            row = connection.execute(statement).mappings().first()

        if row is None:
            return None
        return {
            key: self._normalize_value(value)
            for key, value in row.items()
        }

    def _to_bank_insert_values(self, task_id: str, row: dict[str, object]) -> dict[str, object]:
        return {
            "task_id": task_id,
            "flow_id": str(row["flow_id"]),
            "account_no_masked": row.get("account_no_masked"),
            "customer_name_masked": row.get("customer_name_masked"),
            "amount": self._to_decimal(row["amount"]),
            "trade_time": pd.to_datetime(row["trade_time"]).to_pydatetime(),
            "summary": row.get("summary"),
        }

    def _to_clear_insert_values(self, task_id: str, row: dict[str, object]) -> dict[str, object]:
        return {
            "task_id": task_id,
            "flow_id": str(row["flow_id"]),
            "channel": row.get("channel"),
            "amount": self._to_decimal(row["amount"]),
            "trade_time": pd.to_datetime(row["trade_time"]).to_pydatetime(),
            "summary": row.get("summary"),
        }

    def _to_decimal(self, value: object) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"))

    def _normalize_value(self, value: object) -> object:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return value


transaction_service = TransactionService()

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import cast

import pandas as pd
from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Time,
    UniqueConstraint,
    delete,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Connection, Engine

from bank_reconciliation_agent.db.session import get_engine


metadata = MetaData()

bank_transaction_table = Table(
    "t_bank_transaction",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("task_id", String(64), nullable=False),
    Column("flow_id", String(64), nullable=True),
    Column("bank_serial_no", String(64), nullable=True),
    Column("accounting_date", Date, nullable=True),
    Column("accounting_time", Time, nullable=True),
    Column("value_date", Date, nullable=True),
    Column("self_account_no_masked", String(64), nullable=True),
    Column("self_account_name_masked", String(128), nullable=True),
    Column("self_bank_name", String(128), nullable=True),
    Column("currency", String(8), nullable=False, default="CNY"),
    Column("transaction_type", String(32), nullable=True),
    Column("transaction_direction", String(16), nullable=True),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("debit_amount", Numeric(18, 2), nullable=False, default=Decimal("0.00")),
    Column("credit_amount", Numeric(18, 2), nullable=False, default=Decimal("0.00")),
    Column("fee_amount", Numeric(18, 2), nullable=False, default=Decimal("0.00")),
    Column("balance_after", Numeric(18, 2), nullable=True),
    Column("trade_time", DateTime, nullable=False),
    Column("account_no_masked", String(64), nullable=True),
    Column("customer_name_masked", String(128), nullable=True),
    Column("counterparty_account_no_masked", String(64), nullable=True),
    Column("counterparty_name_masked", String(128), nullable=True),
    Column("counterparty_bank_name", String(128), nullable=True),
    Column("channel", String(32), nullable=True),
    Column("summary", String(255), nullable=True),
    Column("purpose", String(128), nullable=True),
    Column("posting_status", String(32), nullable=True),
    Column("branch_no", String(32), nullable=True),
    Column("teller_id", String(64), nullable=True),
    Column("transaction_code", String(32), nullable=True),
    Column("source_system", String(64), nullable=True),
    Column("remark", String(255), nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    UniqueConstraint("task_id", "flow_id", name="uk_bank_task_flow"),
    Index("idx_bank_task_flow", "task_id", "flow_id"),
    Index("idx_bank_task_time", "task_id", "trade_time"),
    Index("idx_bank_serial", "bank_serial_no"),
)

clear_transaction_table = Table(
    "t_clear_transaction",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("task_id", String(64), nullable=False),
    Column("flow_id", String(64), nullable=True),
    Column("clearing_serial_no", String(64), nullable=True),
    Column("merchant_id", String(64), nullable=True),
    Column("merchant_name", String(128), nullable=True),
    Column("store_name", String(128), nullable=True),
    Column("terminal_id", String(64), nullable=True),
    Column("channel", String(32), nullable=True),
    Column("transaction_type", String(32), nullable=True),
    Column("trade_date", Date, nullable=True),
    Column("trade_time", DateTime, nullable=False),
    Column("settlement_date", Date, nullable=True),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("transaction_amount", Numeric(18, 2), nullable=False),
    Column("fee_amount", Numeric(18, 2), nullable=False, default=Decimal("0.00")),
    Column("net_amount", Numeric(18, 2), nullable=False),
    Column("currency", String(8), nullable=False, default="CNY"),
    Column("status", String(32), nullable=True),
    Column("summary", String(255), nullable=True),
    Column("batch_no", String(64), nullable=True),
    Column("voucher_no", String(64), nullable=True),
    Column("reference_no", String(64), nullable=True),
    Column("merchant_order_no", String(64), nullable=True),
    Column("payer_account_no_masked", String(64), nullable=True),
    Column("payer_name_masked", String(128), nullable=True),
    Column("payee_account_no_masked", String(64), nullable=True),
    Column("payee_name_masked", String(128), nullable=True),
    Column("order_description", String(255), nullable=True),
    Column("remark", String(255), nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    UniqueConstraint("task_id", "flow_id", name="uk_clear_task_flow"),
    Index("idx_clear_task_flow", "task_id", "flow_id"),
    Index("idx_clear_task_time", "task_id", "trade_time"),
    Index("idx_clear_serial", "clearing_serial_no"),
    Index("idx_clear_merchant_order", "merchant_order_no"),
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
        connection: Connection | None = None,
    ) -> None:
        """覆盖写入同一对账任务的银行端和清算端标准流水。"""
        self._ensure_initialized()

        def _execute(conn: Connection) -> None:
            conn.execute(
                delete(bank_transaction_table).where(bank_transaction_table.c.task_id == task_id)
            )
            conn.execute(
                delete(clear_transaction_table).where(
                    clear_transaction_table.c.task_id == task_id
                )
            )
            if not bank_df.empty:
                conn.execute(
                    insert(bank_transaction_table),
                    [self._to_bank_insert_values(task_id, row) for row in self._records(bank_df)],
                )
            if not clear_df.empty:
                conn.execute(
                    insert(clear_transaction_table),
                    [
                        self._to_clear_insert_values(task_id, row)
                        for row in self._records(clear_df)
                    ],
                )

        if connection is not None:
            _execute(connection)
        else:
            with self._engine.begin() as conn:
                _execute(conn)

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
            "bank_serial_no": self._to_optional_string(row.get("bank_serial_no")),
            "accounting_date": self._to_date(row.get("accounting_date")),
            "accounting_time": self._to_time(row.get("accounting_time")),
            "value_date": self._to_date(row.get("value_date")),
            "self_account_no_masked": self._to_optional_string(row.get("self_account_no_masked")),
            "self_account_name_masked": self._to_optional_string(row.get("self_account_name_masked")),
            "self_bank_name": self._to_optional_string(row.get("self_bank_name")),
            "currency": self._to_optional_string(row.get("currency")) or "CNY",
            "transaction_type": self._to_optional_string(row.get("transaction_type")),
            "transaction_direction": self._to_optional_string(row.get("transaction_direction")),
            "amount": self._to_decimal(row["amount"]),
            "debit_amount": self._to_decimal(row.get("debit_amount", 0)),
            "credit_amount": self._to_decimal(row.get("credit_amount", 0)),
            "fee_amount": self._to_decimal(row.get("fee_amount", 0)),
            "balance_after": self._to_optional_decimal(row.get("balance_after")),
            "trade_time": self._to_datetime(row["trade_time"]),
            "account_no_masked": self._to_optional_string(row.get("account_no_masked")),
            "customer_name_masked": self._to_optional_string(row.get("customer_name_masked")),
            "counterparty_account_no_masked": self._to_optional_string(
                row.get("counterparty_account_no_masked")
            ),
            "counterparty_name_masked": self._to_optional_string(row.get("counterparty_name_masked")),
            "counterparty_bank_name": self._to_optional_string(row.get("counterparty_bank_name")),
            "channel": self._to_optional_string(row.get("channel")),
            "summary": self._to_optional_string(row.get("summary")),
            "purpose": self._to_optional_string(row.get("purpose")),
            "posting_status": self._to_optional_string(row.get("posting_status")),
            "branch_no": self._to_optional_string(row.get("branch_no")),
            "teller_id": self._to_optional_string(row.get("teller_id")),
            "transaction_code": self._to_optional_string(row.get("transaction_code")),
            "source_system": self._to_optional_string(row.get("source_system")),
            "remark": self._to_optional_string(row.get("remark")),
        }

    def _to_clear_insert_values(self, task_id: str, row: dict[str, object]) -> dict[str, object]:
        return {
            "task_id": task_id,
            "flow_id": str(row["flow_id"]),
            "clearing_serial_no": self._to_optional_string(row.get("clearing_serial_no")),
            "merchant_id": self._to_optional_string(row.get("merchant_id")),
            "merchant_name": self._to_optional_string(row.get("merchant_name")),
            "store_name": self._to_optional_string(row.get("store_name")),
            "terminal_id": self._to_optional_string(row.get("terminal_id")),
            "channel": self._to_optional_string(row.get("channel")),
            "transaction_type": self._to_optional_string(row.get("transaction_type")),
            "trade_date": self._to_date(row.get("trade_date")),
            "trade_time": self._to_datetime(row["trade_time"]),
            "settlement_date": self._to_date(row.get("settlement_date")),
            "amount": self._to_decimal(row["amount"]),
            "transaction_amount": self._to_decimal(row["transaction_amount"]),
            "fee_amount": self._to_decimal(row.get("fee_amount", 0)),
            "net_amount": self._to_decimal(row["net_amount"]),
            "currency": self._to_optional_string(row.get("currency")) or "CNY",
            "status": self._to_optional_string(row.get("status")),
            "summary": self._to_optional_string(row.get("summary")),
            "batch_no": self._to_optional_string(row.get("batch_no")),
            "voucher_no": self._to_optional_string(row.get("voucher_no")),
            "reference_no": self._to_optional_string(row.get("reference_no")),
            "merchant_order_no": self._to_optional_string(row.get("merchant_order_no")),
            "payer_account_no_masked": self._to_optional_string(row.get("payer_account_no_masked")),
            "payer_name_masked": self._to_optional_string(row.get("payer_name_masked")),
            "payee_account_no_masked": self._to_optional_string(row.get("payee_account_no_masked")),
            "payee_name_masked": self._to_optional_string(row.get("payee_name_masked")),
            "order_description": self._to_optional_string(row.get("order_description")),
            "remark": self._to_optional_string(row.get("remark")),
        }

    def _to_decimal(self, value: object) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"))

    def _to_optional_decimal(self, value: object) -> Decimal | None:
        if self._is_empty(value):
            return None
        return self._to_decimal(value)

    def _records(self, dataframe: pd.DataFrame) -> list[dict[str, object]]:
        return cast(list[dict[str, object]], dataframe.to_dict("records"))

    def _to_date(self, value: object) -> date | None:
        if self._is_empty(value):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime().date()
        return date.fromisoformat(str(value))

    def _to_datetime(self, value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        return datetime.fromisoformat(str(value))

    def _to_time(self, value: object) -> time | None:
        if self._is_empty(value):
            return None
        if isinstance(value, datetime):
            return value.time()
        if isinstance(value, time):
            return value
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime().time()
        return time.fromisoformat(str(value))

    def _to_optional_string(self, value: object) -> str | None:
        if self._is_empty(value):
            return None
        return str(value)

    def _is_empty(self, value: object) -> bool:
        return value is None or bool(pd.isna(value))

    def _normalize_value(self, value: object) -> object:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return value


transaction_service = TransactionService()

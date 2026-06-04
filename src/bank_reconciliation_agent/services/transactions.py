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
    delete,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Connection, Engine

from bank_reconciliation_agent.db.session import get_engine


metadata = MetaData()

source_a_transaction_table = Table(
    "t_source_a_transaction",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("task_id", String(64), nullable=False),
    Column("scenario_type", String(32), nullable=False, default="BANK_ENTERPRISE"),
    Column("source_side", String(1), nullable=False, default="A"),
    Column("source_type", String(32), nullable=False, default="ENTERPRISE_BOOK"),
    Column("flow_id", String(64), nullable=True),
    Column("bank_serial_no", String(64), nullable=True),
    Column("voucher_no", String(64), nullable=True),
    Column("accounting_period", String(16), nullable=True),
    Column("accounting_date", Date, nullable=True),
    Column("accounting_time", Time, nullable=True),
    Column("value_date", Date, nullable=True),
    Column("self_account_no_masked", String(64), nullable=True),
    Column("self_account_name_masked", String(128), nullable=True),
    Column("self_bank_name", String(128), nullable=True),
    Column("account_no_masked", String(64), nullable=True),
    Column("customer_name_masked", String(128), nullable=True),
    Column("counterparty_account_no_masked", String(64), nullable=True),
    Column("counterparty_name_masked", String(128), nullable=True),
    Column("counterparty_bank_name", String(128), nullable=True),
    Column("currency", String(8), nullable=False, default="CNY"),
    Column("transaction_type", String(32), nullable=True),
    Column("transaction_direction", String(16), nullable=True),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("debit_amount", Numeric(18, 2), nullable=False, default=Decimal("0.00")),
    Column("credit_amount", Numeric(18, 2), nullable=False, default=Decimal("0.00")),
    Column("fee_amount", Numeric(18, 2), nullable=False, default=Decimal("0.00")),
    Column("balance_after", Numeric(18, 2), nullable=True),
    Column("trade_time", DateTime, nullable=False),
    Column("channel", String(32), nullable=True),
    Column("summary", String(255), nullable=True),
    Column("purpose", String(128), nullable=True),
    Column("posting_status", String(32), nullable=True),
    Column("branch_no", String(32), nullable=True),
    Column("teller_id", String(64), nullable=True),
    Column("transaction_code", String(32), nullable=True),
    Column("source_system", String(64), nullable=True),
    Column("remark", String(255), nullable=True),
    Column("match_status", String(32), nullable=True),
    Column("matched_source_b_id", BigInteger, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Index("idx_user_task_flow", "user_id", "task_id", "flow_id"),
    Index("idx_source_a_user_task_time", "user_id", "task_id", "trade_time"),
)

source_b_transaction_table = Table(
    "t_source_b_transaction",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("task_id", String(64), nullable=False),
    Column("scenario_type", String(32), nullable=False, default="BANK_ENTERPRISE"),
    Column("source_side", String(1), nullable=False, default="B"),
    Column("source_type", String(32), nullable=False, default="BANK_STATEMENT"),
    Column("flow_id", String(64), nullable=True),
    Column("clearing_serial_no", String(64), nullable=True),
    Column("bank_serial_no", String(64), nullable=True),
    Column("trade_date", Date, nullable=True),
    Column("settlement_date", Date, nullable=True),
    Column("currency", String(8), nullable=False, default="CNY"),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("transaction_amount", Numeric(18, 2), nullable=False),
    Column("fee_amount", Numeric(18, 2), nullable=False, default=Decimal("0.00")),
    Column("net_amount", Numeric(18, 2), nullable=False),
    Column("trade_time", DateTime, nullable=False),
    Column("status", String(32), nullable=True),
    Column("summary", String(255), nullable=True),
    Column("balance_after", Numeric(18, 2), nullable=True),
    Column("account_no_masked", String(64), nullable=True),
    Column("customer_name_masked", String(128), nullable=True),
    Column("counterparty_account_no_masked", String(64), nullable=True),
    Column("counterparty_name_masked", String(128), nullable=True),
    Column("counterparty_bank_name", String(128), nullable=True),
    Column("channel", String(32), nullable=True),
    Column("remark", String(255), nullable=True),
    Column("match_status", String(32), nullable=True),
    Column("matched_source_a_id", BigInteger, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Index("idx_user_task_flow_b", "user_id", "task_id", "flow_id"),
    Index("idx_source_b_user_task_time", "user_id", "task_id", "trade_time"),
)


class TransactionService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def replace_task_rows(
        self,
        task_id: str,
        source_a_df: pd.DataFrame,
        source_b_df: pd.DataFrame,
        user_id: str = "demo_user",
        scenario_type: str = "BANK_ENTERPRISE",
        connection: Connection | None = None,
    ) -> None:
        """覆盖写入同一用户/任务的 Source A 和 Source B 标准流水。"""
        self._ensure_initialized()

        def _execute(conn: Connection) -> None:
            conn.execute(
                delete(source_a_transaction_table).where(
                    source_a_transaction_table.c.user_id == user_id,
                    source_a_transaction_table.c.task_id == task_id,
                )
            )
            conn.execute(
                delete(source_b_transaction_table).where(
                    source_b_transaction_table.c.user_id == user_id,
                    source_b_transaction_table.c.task_id == task_id,
                )
            )
            if not source_a_df.empty:
                conn.execute(
                    insert(source_a_transaction_table),
                    [
                        self._to_source_a_insert_values(task_id, row, user_id, scenario_type)
                        for row in self._records(source_a_df)
                    ],
                )
            if not source_b_df.empty:
                conn.execute(
                    insert(source_b_transaction_table),
                    [
                        self._to_source_b_insert_values(task_id, row, user_id, scenario_type)
                        for row in self._records(source_b_df)
                    ],
                )

        if connection is not None:
            _execute(connection)
        else:
            with self._engine.begin() as conn:
                _execute(conn)

    def count_source_a_rows(self, task_id: str, user_id: str = "demo_user") -> int:
        return self._count_rows(source_a_transaction_table, task_id, user_id)

    def count_source_b_rows(self, task_id: str, user_id: str = "demo_user") -> int:
        return self._count_rows(source_b_transaction_table, task_id, user_id)

    def get_source_a_row(
        self, task_id: str, flow_id: str, user_id: str = "demo_user",
    ) -> dict[str, object] | None:
        return self._get_row(source_a_transaction_table, task_id, flow_id, user_id)

    def get_source_b_row(
        self, task_id: str, flow_id: str, user_id: str = "demo_user",
    ) -> dict[str, object] | None:
        return self._get_row(source_b_transaction_table, task_id, flow_id, user_id)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(
            self._engine,
            tables=[source_a_transaction_table, source_b_transaction_table],
        )
        self._initialized = True

    def _count_rows(self, table: Table, task_id: str, user_id: str) -> int:
        self._ensure_initialized()
        statement = (
            select(func.count())
            .select_from(table)
            .where(table.c.user_id == user_id, table.c.task_id == task_id)
        )
        with self._engine.connect() as connection:
            return connection.execute(statement).scalar_one()

    def _get_row(
        self, table: Table, task_id: str, flow_id: str, user_id: str,
    ) -> dict[str, object] | None:
        self._ensure_initialized()
        statement = select(table).where(
            table.c.user_id == user_id,
            table.c.task_id == task_id,
            table.c.flow_id == flow_id,
        )
        with self._engine.connect() as connection:
            row = connection.execute(statement).mappings().first()

        if row is None:
            return None
        return {key: self._normalize_value(value) for key, value in row.items()}

    def _to_source_a_insert_values(
        self,
        task_id: str,
        row: dict[str, object],
        user_id: str,
        scenario_type: str,
    ) -> dict[str, object]:
        amount = self._to_decimal(row["amount"])
        direction = self._to_optional_string(row.get("transaction_direction"))
        return {
            "user_id": user_id,
            "task_id": task_id,
            "scenario_type": scenario_type,
            "source_side": "A",
            "source_type": "ENTERPRISE_BOOK",
            "flow_id": str(row["flow_id"]),
            "bank_serial_no": self._to_optional_string(row.get("bank_serial_no")),
            "voucher_no": self._to_optional_string(row.get("voucher_no")),
            "accounting_period": self._to_optional_string(row.get("accounting_period")),
            "accounting_date": self._to_date(row.get("accounting_date")),
            "accounting_time": self._to_time(row.get("accounting_time")),
            "value_date": self._to_date(row.get("value_date")),
            "self_account_no_masked": self._to_optional_string(row.get("self_account_no_masked")),
            "self_account_name_masked": self._to_optional_string(row.get("self_account_name_masked")),
            "self_bank_name": self._to_optional_string(row.get("self_bank_name")),
            "account_no_masked": self._to_optional_string(row.get("account_no_masked")),
            "customer_name_masked": self._to_optional_string(row.get("customer_name_masked")),
            "counterparty_account_no_masked": self._to_optional_string(
                row.get("counterparty_account_no_masked")
            ),
            "counterparty_name_masked": self._to_optional_string(row.get("counterparty_name_masked")),
            "counterparty_bank_name": self._to_optional_string(row.get("counterparty_bank_name")),
            "currency": self._to_optional_string(row.get("currency")) or "CNY",
            "transaction_type": self._to_optional_string(row.get("transaction_type")),
            "transaction_direction": direction,
            "amount": amount,
            "debit_amount": amount if direction == "DEBIT" else self._to_decimal(row.get("debit_amount", 0)),
            "credit_amount": amount if direction == "CREDIT" else self._to_decimal(row.get("credit_amount", 0)),
            "fee_amount": self._to_decimal(row.get("fee_amount", 0)),
            "balance_after": self._to_optional_decimal(row.get("balance_after")),
            "trade_time": self._to_datetime(row["trade_time"]),
            "channel": self._to_optional_string(row.get("channel")),
            "summary": self._to_optional_string(row.get("summary")),
            "purpose": self._to_optional_string(row.get("purpose")),
            "posting_status": self._to_optional_string(row.get("posting_status")),
            "branch_no": self._to_optional_string(row.get("branch_no")),
            "teller_id": self._to_optional_string(row.get("teller_id")),
            "transaction_code": self._to_optional_string(row.get("transaction_code")),
            "source_system": self._to_optional_string(row.get("source_system")),
            "remark": self._to_optional_string(row.get("remark")),
            "match_status": self._to_optional_string(row.get("match_status")),
            "matched_source_b_id": None,
        }

    def _to_source_b_insert_values(
        self,
        task_id: str,
        row: dict[str, object],
        user_id: str,
        scenario_type: str,
    ) -> dict[str, object]:
        amount = self._to_decimal(row["amount"])
        return {
            "user_id": user_id,
            "task_id": task_id,
            "scenario_type": scenario_type,
            "source_side": "B",
            "source_type": "BANK_STATEMENT",
            "flow_id": str(row["flow_id"]),
            "clearing_serial_no": self._to_optional_string(row.get("clearing_serial_no")),
            "bank_serial_no": self._to_optional_string(row.get("bank_serial_no")),
            "trade_date": self._to_date(row.get("trade_date")),
            "settlement_date": self._to_date(row.get("settlement_date")),
            "currency": self._to_optional_string(row.get("currency")) or "CNY",
            "amount": amount,
            "transaction_amount": self._to_decimal(row.get("transaction_amount", amount)),
            "fee_amount": self._to_decimal(row.get("fee_amount", 0)),
            "net_amount": self._to_decimal(row.get("net_amount", amount)),
            "trade_time": self._to_datetime(row["trade_time"]),
            "status": self._to_optional_string(row.get("status")),
            "summary": self._to_optional_string(row.get("summary")),
            "balance_after": self._to_optional_decimal(row.get("balance_after")),
            "account_no_masked": self._to_optional_string(row.get("account_no_masked")),
            "customer_name_masked": self._to_optional_string(row.get("customer_name_masked")),
            "counterparty_account_no_masked": self._to_optional_string(
                row.get("counterparty_account_no_masked")
            ),
            "counterparty_name_masked": self._to_optional_string(row.get("counterparty_name_masked")),
            "counterparty_bank_name": self._to_optional_string(row.get("counterparty_bank_name")),
            "channel": self._to_optional_string(row.get("channel")),
            "remark": self._to_optional_string(row.get("remark")),
            "match_status": self._to_optional_string(row.get("match_status")),
            "matched_source_a_id": None,
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

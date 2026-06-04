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
from bank_reconciliation_agent.schemas.common import Page
from bank_reconciliation_agent.schemas.ledger import LedgerQuery, LedgerRow


metadata = MetaData()

error_ledger_table = Table(
    "t_error_ledger",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("queue_id", BigInteger, nullable=False, default=0),
    Column("task_id", String(64), nullable=False),
    Column("scenario_type", String(32), nullable=False, default="BANK_ENTERPRISE"),
    Column("flow_id", String(64), nullable=False),
    Column("error_type", String(32), nullable=False),
    Column("discrepancy_amount", Numeric(18, 2), nullable=False),
    Column("ai_cleaned_json", JSON, nullable=True),
    Column("ai_audit_opinion", Text, nullable=True),
    Column("ai_confidence", Numeric(5, 4), nullable=True),
    Column("rag_source", String(512), nullable=True),
    Column("handle_status", String(32), nullable=False),
    Column("handler_username", String(64), nullable=True),
    Column("handle_remark", String(255), nullable=True),
    Column("handled_at", DateTime, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Index("idx_user_task_error", "user_id", "task_id", "error_type"),
    Index("idx_user_handle_status", "user_id", "handle_status"),
)


class LedgerService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def replace_task_rows(
        self,
        task_id: str,
        rows: list[LedgerRow],
        user_id: str = "demo_user",
    ) -> None:
        """用同一用户/任务的最新异常结果覆盖旧台账。"""
        self._ensure_initialized()
        with self._engine.begin() as connection:
            connection.execute(
                delete(error_ledger_table).where(
                    error_ledger_table.c.user_id == user_id,
                    error_ledger_table.c.task_id == task_id,
                )
            )
            if rows:
                connection.execute(
                    insert(error_ledger_table),
                    [self._to_insert_values(row, user_id) for row in rows],
                )

    def list(self, query: LedgerQuery) -> Page[LedgerRow]:
        """根据查询条件返回差错台账分页结果。"""
        self._ensure_initialized()
        filters = self._build_filters(query)
        count_statement = select(func.count()).select_from(error_ledger_table).where(*filters)
        rows_statement = (
            select(error_ledger_table)
            .where(*filters)
            .order_by(error_ledger_table.c.id)
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )

        with self._engine.connect() as connection:
            total = connection.execute(count_statement).scalar_one()
            rows = [
                self._to_ledger_row(row)
                for row in connection.execute(rows_statement).mappings().all()
            ]

        return Page(items=rows, total=total, page=query.page, page_size=query.page_size)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[error_ledger_table])
        self._initialized = True

    def _build_filters(self, query: LedgerQuery) -> list[object]:
        filters: list[object] = [error_ledger_table.c.user_id == query.user_id]
        if query.task_id:
            filters.append(error_ledger_table.c.task_id == query.task_id)
        if query.scenario_type:
            filters.append(error_ledger_table.c.scenario_type == query.scenario_type)
        if query.error_type:
            filters.append(error_ledger_table.c.error_type == query.error_type)
        if query.handle_status:
            filters.append(error_ledger_table.c.handle_status == query.handle_status)
        return filters

    def _to_insert_values(self, row: LedgerRow, user_id: str) -> dict[str, object]:
        return {
            "user_id": user_id,
            "task_id": row.task_id,
            "queue_id": 0,
            "scenario_type": row.scenario_type,
            "flow_id": row.flow_id,
            "error_type": row.error_type,
            "discrepancy_amount": row.discrepancy_amount,
            "ai_cleaned_json": row.ai_cleaned_json,
            "ai_audit_opinion": row.ai_audit_opinion,
            "ai_confidence": row.ai_confidence,
            "rag_source": row.rag_source,
            "handle_status": row.handle_status,
        }

    def _to_ledger_row(self, row: object) -> LedgerRow:
        return LedgerRow(
            id=row["id"],
            task_id=row["task_id"],
            scenario_type=row["scenario_type"],
            flow_id=row["flow_id"],
            error_type=row["error_type"],
            discrepancy_amount=Decimal(str(row["discrepancy_amount"])),
            ai_cleaned_json=self._to_json_dict(row["ai_cleaned_json"]),
            ai_audit_opinion=row["ai_audit_opinion"],
            ai_confidence=self._to_decimal_or_none(row["ai_confidence"]),
            rag_source=row["rag_source"],
            handle_status=row["handle_status"],
        )

    def _to_json_dict(self, value: object) -> dict[str, str | None] | None:
        if value is None:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return value

    def _to_decimal_or_none(self, value: object) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))


ledger_service = LedgerService()

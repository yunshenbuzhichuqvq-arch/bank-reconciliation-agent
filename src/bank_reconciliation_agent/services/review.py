from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    and_,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.agents.audit_agent import BRANCH_PROFILE
from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.schemas.review import (
    PendingReviewItem,
    PendingReviewListResponse,
    RagSourceRef,
    ReviewResultResponse,
)
from bank_reconciliation_agent.services.ledger import error_ledger_table
from bank_reconciliation_agent.services.queue import reconciliation_queue_table
from bank_reconciliation_agent.services.task import reconciliation_task_table


metadata = MetaData()

human_review_table = Table(
    "t_human_review",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("scenario_type", String(32), nullable=False, default="BANK_ENTERPRISE"),
    Column("queue_id", BigInteger, nullable=False),
    Column("task_id", String(64), nullable=False),
    Column("ai_suggestion", String(32), nullable=False),
    Column("ai_confidence", Numeric(5, 4), nullable=True),
    Column("ai_reason", Text, nullable=True),
    Column("ai_fallback_level", Integer, nullable=False, default=0),
    Column("action", String(32), nullable=False),
    Column("handler_username", String(64), nullable=False),
    Column("remark", String(255), nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
)


class ReviewService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def list_pending(
        self,
        *,
        user_id: str,
        task_id: str | None,
        page: int,
        page_size: int,
    ) -> PendingReviewListResponse:
        self._ensure_initialized()
        filters = [
            reconciliation_queue_table.c.user_id == user_id,
            reconciliation_queue_table.c.status == "PENDING_HUMAN",
        ]
        if task_id:
            filters.append(reconciliation_queue_table.c.task_id == task_id)

        join_condition = and_(
            error_ledger_table.c.user_id == reconciliation_queue_table.c.user_id,
            error_ledger_table.c.task_id == reconciliation_queue_table.c.task_id,
            error_ledger_table.c.flow_id == reconciliation_queue_table.c.flow_id,
        )
        joined_tables = reconciliation_queue_table.join(error_ledger_table, join_condition)
        count_statement = select(func.count()).select_from(joined_tables).where(*filters)
        rows_statement = (
            select(
                reconciliation_queue_table.c.id.label("queue_id"),
                reconciliation_queue_table.c.error_type,
                reconciliation_queue_table.c.exception_branch,
                reconciliation_queue_table.c.risk_level,
                error_ledger_table.c.ai_confidence,
                error_ledger_table.c.ai_audit_opinion,
                error_ledger_table.c.rag_source,
            )
            .select_from(joined_tables)
            .where(*filters)
            .order_by(reconciliation_queue_table.c.created_at, reconciliation_queue_table.c.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        with self._engine.connect() as connection:
            total = connection.execute(count_statement).scalar_one()
            rows = connection.execute(rows_statement).mappings().all()

        return PendingReviewListResponse(
            items=[self._to_pending_item(row) for row in rows],
            total=total,
        )

    def approve(
        self,
        *,
        user_id: str,
        queue_id: int,
        action: str,
        handler_username: str,
        remark: str | None,
    ) -> ReviewResultResponse:
        self._ensure_initialized()
        current_status = self._status_for_action(action)
        now = func.now()

        with self._engine.begin() as connection:
            queue_row = connection.execute(
                select(reconciliation_queue_table).where(
                    reconciliation_queue_table.c.id == queue_id,
                    reconciliation_queue_table.c.user_id == user_id,
                )
            ).mappings().first()
            if queue_row is None:
                raise HTTPException(status_code=404, detail="review item not found")

            ledger_row = connection.execute(
                select(error_ledger_table).where(
                    error_ledger_table.c.user_id == user_id,
                    error_ledger_table.c.task_id == queue_row["task_id"],
                    error_ledger_table.c.flow_id == queue_row["flow_id"],
                )
            ).mappings().first()

            ai_suggestion = self._ai_suggestion(queue_row["exception_branch"])
            connection.execute(
                insert(human_review_table).values(
                    user_id=user_id,
                    scenario_type=queue_row["scenario_type"],
                    queue_id=queue_id,
                    task_id=queue_row["task_id"],
                    ai_suggestion=ai_suggestion,
                    ai_confidence=ledger_row["ai_confidence"] if ledger_row else None,
                    ai_reason=ledger_row["ai_audit_opinion"] if ledger_row else None,
                    ai_fallback_level=0,
                    action=action,
                    handler_username=handler_username,
                    remark=remark,
                )
            )
            connection.execute(
                update(error_ledger_table)
                .where(
                    error_ledger_table.c.user_id == user_id,
                    error_ledger_table.c.task_id == queue_row["task_id"],
                    error_ledger_table.c.flow_id == queue_row["flow_id"],
                )
                .values(
                    handle_status=current_status,
                    handler_username=handler_username,
                    handle_remark=remark,
                    handled_at=now,
                )
            )
            connection.execute(
                update(reconciliation_queue_table)
                .where(
                    reconciliation_queue_table.c.id == queue_id,
                    reconciliation_queue_table.c.user_id == user_id,
                )
                .values(status=current_status, updated_at=now)
            )
            connection.execute(
                update(reconciliation_task_table)
                .where(
                    reconciliation_task_table.c.user_id == user_id,
                    reconciliation_task_table.c.task_id == queue_row["task_id"],
                )
                .values(
                    pending_human_rows=reconciliation_task_table.c.pending_human_rows - 1,
                    unresolved_rows=reconciliation_task_table.c.unresolved_rows - 1,
                    updated_at=now,
                )
            )

        return ReviewResultResponse(queue_id=queue_id, current_status=current_status)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        reconciliation_task_table.create(self._engine, checkfirst=True)
        reconciliation_queue_table.create(self._engine, checkfirst=True)
        error_ledger_table.create(self._engine, checkfirst=True)
        metadata.create_all(self._engine, tables=[human_review_table])
        self._initialized = True

    def _to_pending_item(self, row: object) -> PendingReviewItem:
        return PendingReviewItem(
            queue_id=row["queue_id"],
            error_type=row["error_type"],
            exception_branch=row["exception_branch"],
            risk_level=row["risk_level"],
            ai_suggestion=self._ai_suggestion(row["exception_branch"]),
            ai_confidence=self._to_float_or_none(row["ai_confidence"]),
            ai_reason=row["ai_audit_opinion"],
            rag_sources=self._rag_sources(row["rag_source"]),
        )

    def _ai_suggestion(self, exception_branch: str | None) -> str:
        profile = BRANCH_PROFILE.get(exception_branch or "")
        if profile is None:
            return "PENDING_HUMAN"
        return profile.ai_suggestion

    def _rag_sources(self, rag_source: str | None) -> list[RagSourceRef]:
        if not rag_source:
            return []
        return [
            RagSourceRef(source=source.strip())
            for source in rag_source.split(",")
            if source.strip()
        ]

    def _to_float_or_none(self, value: Decimal | None) -> float | None:
        if value is None:
            return None
        return float(value)

    def _status_for_action(self, action: str) -> str:
        if action == "APPROVED_MATCH":
            return "FIXED"
        return "HELD"


review_service = ReviewService()

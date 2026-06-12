from __future__ import annotations

from decimal import Decimal
from typing import Any

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

from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.agents.audit_agent import BRANCH_PROFILE
from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.schemas.review import (
    PendingReviewItem,
    PendingReviewListResponse,
    RagSourceRef,
    ReviewResultResponse,
)
from bank_reconciliation_agent.services.hooks import auth_hook
from bank_reconciliation_agent.services.ledger import error_ledger_table
from bank_reconciliation_agent.services.memory.manager import memory_manager
from bank_reconciliation_agent.services.queue import reconciliation_queue_table
from bank_reconciliation_agent.services.task import reconciliation_task_table


metadata = MetaData()
_AGENT_LENIENT = {"APPROVED_MATCH", "AUTO_FIXED"}
_HUMAN_BLOCK = {"FORCE_HOLD", "HELD"}

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
        if settings.checkpoint_enabled:
            return self._approve_via_checkpoint(
                user_id=user_id,
                queue_id=queue_id,
                action=action,
                handler_username=handler_username,
                remark=remark,
            )
        return self._approve_plain(
            user_id=user_id,
            queue_id=queue_id,
            action=action,
            handler_username=handler_username,
            remark=remark,
        )

    def _approve_plain(
        self,
        *,
        user_id: str,
        queue_id: int,
        action: str,
        handler_username: str,
        remark: str | None,
    ) -> ReviewResultResponse:
        current_status = self._status_for_action(action)
        queue_row, ledger_row = self._load_review_context(user_id=user_id, queue_id=queue_id)

        with self._engine.begin() as connection:
            self._apply_review_core(
                connection,
                user_id=user_id,
                queue_id=queue_id,
                action=action,
                handler_username=handler_username,
                remark=remark,
                queue_row=queue_row,
                ledger_row=ledger_row,
            )

        memory_updated = self._apply_review_side_effects(
            user_id=user_id,
            task_id=queue_row["task_id"],
            queue_id=queue_id,
            action=action,
            remark=remark,
            queue_row=queue_row,
            ledger_row=ledger_row,
        )

        return ReviewResultResponse(
            queue_id=queue_id,
            current_status=current_status,
            memory_updated=memory_updated,
        )

    def _approve_via_checkpoint(
        self,
        *,
        user_id: str,
        queue_id: int,
        action: str,
        handler_username: str,
        remark: str | None,
    ) -> ReviewResultResponse:
        from langgraph.types import Command

        from bank_reconciliation_agent.services.review_graph import get_review_graph

        queue_row, ledger_row = self._load_review_context(user_id=user_id, queue_id=queue_id)
        if self._is_terminal_queue_status(queue_row["status"]):
            return self._build_existing_result(queue_id=queue_id, current_status=queue_row["status"])

        graph = get_review_graph()
        config = {"configurable": {"thread_id": f"{queue_row['task_id']}:{queue_id}"}}
        graph.invoke(
            {
                "task_id": queue_row["task_id"],
                "user_id": user_id,
                "queue_id": queue_id,
                "handler_username": handler_username,
                "remark": remark,
            },
            config,
        )
        result = graph.invoke(Command(resume=action), config)
        result_payload = result["result"]
        return ReviewResultResponse(
            queue_id=result_payload["queue_id"],
            current_status=result_payload["current_status"],
            memory_updated=result_payload["memory_updated"],
        )

    def apply_checkpoint_decision(
        self,
        *,
        user_id: str,
        task_id: str,
        queue_id: int,
        action: str,
        handler_username: str,
        remark: str | None,
    ) -> ReviewResultResponse:
        queue_row, ledger_row = self._load_review_context(user_id=user_id, queue_id=queue_id)
        if queue_row["task_id"] != task_id:
            raise HTTPException(status_code=409, detail="checkpoint task mismatch")
        if self._is_terminal_queue_status(queue_row["status"]):
            return self._build_existing_result(queue_id=queue_id, current_status=queue_row["status"])

        current_status = self._status_for_action(action)
        with self._engine.begin() as connection:
            self._apply_review_core(
                connection,
                user_id=user_id,
                queue_id=queue_id,
                action=action,
                handler_username=handler_username,
                remark=remark,
                queue_row=queue_row,
                ledger_row=ledger_row,
            )
        memory_updated = self._apply_review_side_effects(
            user_id=user_id,
            task_id=task_id,
            queue_id=queue_id,
            action=action,
            remark=remark,
            queue_row=queue_row,
            ledger_row=ledger_row,
        )
        return ReviewResultResponse(
            queue_id=queue_id,
            current_status=current_status,
            memory_updated=memory_updated,
        )

    def _apply_review_core(
        self,
        connection,
        *,
        user_id: str,
        queue_id: int,
        action: str,
        handler_username: str,
        remark: str | None,
        queue_row,
        ledger_row,
    ) -> None:
        current_status = self._status_for_action(action)
        now = func.now()
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

    def _apply_review_side_effects(
        self,
        *,
        user_id: str,
        task_id: str,
        queue_id: int,
        action: str,
        remark: str | None,
        queue_row,
        ledger_row,
    ) -> dict[str, bool]:
        current_status = self._status_for_action(action)
        ai_suggestion = self._ai_suggestion(queue_row["exception_branch"])
        if self._is_override(ai_suggestion=ai_suggestion, action=action, current_status=current_status):
            try:
                memory_manager._short_term.delete_by_queue(thread_id=task_id, queue_id=queue_id)
                return {"short_term": True, "long_term": False}
            except Exception:
                log.warning(
                    "review_side_effect_failed",
                    queue_id=queue_id,
                    task_id=task_id,
                    side_effect_failed="memory_rollback",
                )
                return {"short_term": False, "long_term": False}
        try:
            memory_manager.update_after_decision(
                user_id=user_id,
                thread_id=task_id,
                error_type=str(queue_row["error_type"]),
                decision={
                    "queue_id": queue_id,
                    "flow_id": queue_row["flow_id"],
                    "risk_level": queue_row["risk_level"],
                    "decision": current_status,
                    "confidence": ledger_row["ai_confidence"] if ledger_row else None,
                    "exception_branch": queue_row["exception_branch"],
                    "bank_amount": ledger_row["bank_amount"] if ledger_row else None,
                    "clear_amount": ledger_row["clear_amount"] if ledger_row else None,
                    "amount_diff": ledger_row["discrepancy_amount"] if ledger_row else None,
                    "ai_suggestion": ai_suggestion,
                    "human_decision": action,
                    "summary": ledger_row["ai_audit_opinion"] if ledger_row else None,
                    "remark": remark,
                },
                is_human_confirmed=True,
            )
            return {"short_term": False, "long_term": True}
        except Exception:
            log.warning(
                "review_side_effect_failed",
                queue_id=queue_id,
                task_id=task_id,
                side_effect_failed="memory",
            )
            return {"short_term": False, "long_term": False}

    def _load_review_context(self, *, user_id: str, queue_id: int) -> tuple[Any, Any]:
        self._ensure_initialized()
        with self._engine.connect() as connection:
            queue_row = connection.execute(
                select(reconciliation_queue_table).where(reconciliation_queue_table.c.id == queue_id)
            ).mappings().first()
            if queue_row is None:
                raise HTTPException(status_code=404, detail="review item not found")
            auth_hook(user_id=user_id, task_id=queue_row["task_id"])
            ledger_row = connection.execute(
                select(error_ledger_table).where(
                    error_ledger_table.c.user_id == user_id,
                    error_ledger_table.c.task_id == queue_row["task_id"],
                    error_ledger_table.c.flow_id == queue_row["flow_id"],
                )
            ).mappings().first()
        return queue_row, ledger_row

    def _is_terminal_queue_status(self, status: str) -> bool:
        return status != "PENDING_HUMAN"

    def _build_existing_result(self, *, queue_id: int, current_status: str) -> ReviewResultResponse:
        return ReviewResultResponse(
            queue_id=queue_id,
            current_status=current_status,
            memory_updated={"short_term": False, "long_term": False},
        )

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

    def _is_override(self, *, ai_suggestion: str, action: str, current_status: str) -> bool:
        return ai_suggestion in _AGENT_LENIENT and (
            action in _HUMAN_BLOCK or current_status in _HUMAN_BLOCK
        )


review_service = ReviewService()

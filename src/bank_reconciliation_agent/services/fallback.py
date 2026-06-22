from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.services.ledger import error_ledger_table


CONFIDENCE_THRESHOLD = 0.85


class FallbackCaseProvider(Protocol):
    def confirmed_cases(
        self,
        *,
        user_id: str,
        exception_branch: str | None,
        limit: int = 3,
    ) -> list[dict[str, object]]: ...


class LedgerFallbackCaseProvider:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def confirmed_cases(
        self,
        *,
        user_id: str,
        exception_branch: str | None,
        limit: int = 3,
    ) -> list[dict[str, object]]:
        self._ensure_initialized()
        statement = (
            select(
                error_ledger_table.c.flow_id,
                error_ledger_table.c.error_type,
                error_ledger_table.c.exception_branch,
                error_ledger_table.c.ai_audit_opinion,
                error_ledger_table.c.ai_confidence,
                error_ledger_table.c.handle_status,
            )
            .where(
                error_ledger_table.c.user_id == user_id,
                error_ledger_table.c.exception_branch == exception_branch,
                error_ledger_table.c.handle_status.in_(("FIXED", "HELD")),
            )
            .order_by(error_ledger_table.c.handled_at.desc(), error_ledger_table.c.id.desc())
            .limit(limit)
        )
        with self._engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings().all()]

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        error_ledger_table.create(self._engine, checkfirst=True)
        self._initialized = True


def l1_requires_l2(decision: AuditDecision) -> bool:
    return confidence_is_low(decision.confidence)


def confidence_is_low(confidence: float) -> bool:
    return confidence < CONFIDENCE_THRESHOLD


def mark_fallback(
    decision: AuditDecision,
    *,
    fallback_level: int,
    next_action: str | None = None,
) -> AuditDecision:
    decision.fallback_applied = fallback_level > 0
    decision.fallback_level = fallback_level
    if next_action is not None:
        decision.next_action = next_action
        decision.decision = next_action
        decision.ai_suggestion = next_action
    return decision


ledger_fallback_case_provider = LedgerFallbackCaseProvider()

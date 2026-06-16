from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.schemas.metrics import (
    DashboardMetricsResponse,
    OfflineNoSnapshot,
    OnlineMetrics,
    UnavailableMetrics,
)
from bank_reconciliation_agent.services.ledger import error_ledger_table
from bank_reconciliation_agent.services.review import human_review_table
from bank_reconciliation_agent.services.task import reconciliation_task_table


class MetricsService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def get_dashboard(self, *, user_id: str) -> DashboardMetricsResponse:
        self._ensure_initialized()
        with self._engine.connect() as connection:
            task_totals = connection.execute(
                select(
                    func.coalesce(func.sum(reconciliation_task_table.c.auto_fixed_rows), 0),
                    func.coalesce(func.sum(reconciliation_task_table.c.pending_human_rows), 0),
                    func.coalesce(func.sum(reconciliation_task_table.c.total_bank_rows), 0),
                    func.coalesce(func.sum(reconciliation_task_table.c.total_llm_tokens), 0),
                    func.coalesce(func.sum(reconciliation_task_table.c.total_llm_cost), 0),
                    func.coalesce(
                        func.sum(
                            case(
                                (reconciliation_task_table.c.status == "AI_RUNNING", 1),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                ).where(reconciliation_task_table.c.user_id == user_id)
            ).one()
            exception_rows = connection.execute(
                select(error_ledger_table.c.error_type, func.count())
                .where(error_ledger_table.c.user_id == user_id)
                .group_by(error_ledger_table.c.error_type)
            ).all()
            fallback_rows = connection.execute(
                select(error_ledger_table.c.fallback_path, func.count())
                .where(
                    error_ledger_table.c.user_id == user_id,
                    error_ledger_table.c.fallback_path.is_not(None),
                )
                .group_by(error_ledger_table.c.fallback_path)
            ).all()
            confidence_rows = connection.execute(
                select(error_ledger_table.c.ai_confidence).where(error_ledger_table.c.user_id == user_id)
            ).scalars()

        auto_fixed = int(task_totals[0] or 0)
        pending_human = int(task_totals[1] or 0)
        total_items = int(task_totals[2] or 0)
        auto_fix_rate = round(auto_fixed / total_items, 4) if total_items else 0.0

        return DashboardMetricsResponse(
            online=OnlineMetrics(
                auto_fix_rate=auto_fix_rate,
                pending_human_count=pending_human,
                hung_count=int(task_totals[5] or 0),
                exception_dist={str(key): int(value) for key, value in exception_rows},
                fallback_dist={str(key): int(value) for key, value in fallback_rows},
                total_tokens=int(task_totals[3] or 0),
                total_cost=Decimal(str(task_totals[4] or "0")).quantize(Decimal("0.0001")),
                confidence_dist=self._confidence_dist(confidence_rows),
            ),
            offline=OfflineNoSnapshot(status="no_snapshot"),
            unavailable=UnavailableMetrics(
                latency="no_data_source",
                agent_accuracy="no_ground_truth",
            ),
        )

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        reconciliation_task_table.metadata.create_all(self._engine, tables=[reconciliation_task_table])
        error_ledger_table.metadata.create_all(self._engine, tables=[error_ledger_table])
        human_review_table.metadata.create_all(self._engine, tables=[human_review_table])
        self._initialized = True

    def _confidence_dist(self, values) -> dict[str, int]:
        dist = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
        for value in values:
            if value is None:
                dist["unknown"] += 1
                continue
            confidence = Decimal(str(value))
            if confidence >= Decimal("0.85"):
                dist["high"] += 1
            elif confidence >= Decimal("0.60"):
                dist["medium"] += 1
            else:
                dist["low"] += 1
        return dist


metrics_service = MetricsService()

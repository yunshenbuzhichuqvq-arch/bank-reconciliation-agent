from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import case, func, select
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.schemas.metrics import (
    DashboardMetricsResponse,
    OfflineMetrics,
    OfflineNoSnapshot,
    OnlineMetrics,
    UnavailableMetrics,
)
from bank_reconciliation_agent.schemas.report import TaskReportMetrics
from bank_reconciliation_agent.services.ledger import error_ledger_table
from bank_reconciliation_agent.services.rag_log import rag_retrieval_log_table
from bank_reconciliation_agent.services.review import human_review_table
from bank_reconciliation_agent.services.task import reconciliation_task_table


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAG_SNAPSHOT_PATH = PROJECT_ROOT / "reports/rag_eval_metrics.json"
DEFAULT_SCHEMA_SNAPSHOT_PATH = PROJECT_ROOT / "reports/agent_schema_conformance.json"


class MetricsService:
    def __init__(
        self,
        engine: Engine | None = None,
        *,
        rag_snapshot_path: Path = DEFAULT_RAG_SNAPSHOT_PATH,
        schema_snapshot_path: Path = DEFAULT_SCHEMA_SNAPSHOT_PATH,
    ) -> None:
        self._engine = engine or get_engine()
        self._rag_snapshot_path = rag_snapshot_path
        self._schema_snapshot_path = schema_snapshot_path
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
            offline=self._read_offline_snapshot(),
            unavailable=UnavailableMetrics(
                latency="no_data_source",
                agent_accuracy="no_ground_truth",
            ),
        )

    def get_task_report_metrics(
        self,
        *,
        user_id: str,
        task_id: str,
    ) -> TaskReportMetrics | None:
        self._ensure_initialized()
        task_filters = (
            reconciliation_task_table.c.user_id == user_id,
            reconciliation_task_table.c.task_id == task_id,
        )
        ledger_filters = (
            error_ledger_table.c.user_id == user_id,
            error_ledger_table.c.task_id == task_id,
        )
        review_filters = (
            human_review_table.c.user_id == user_id,
            human_review_table.c.task_id == task_id,
        )
        rag_filters = (
            rag_retrieval_log_table.c.user_id == user_id,
            rag_retrieval_log_table.c.task_id == task_id,
        )

        with self._engine.connect() as connection:
            task_row = connection.execute(
                select(reconciliation_task_table).where(*task_filters)
            ).mappings().first()
            if task_row is None:
                return None

            ledger_totals = connection.execute(
                select(
                    func.coalesce(func.sum(error_ledger_table.c.discrepancy_amount), 0),
                    func.coalesce(
                        func.sum(case((error_ledger_table.c.handle_status == "HELD", 1), else_=0)),
                        0,
                    ),
                ).where(*ledger_filters)
            ).one()
            exception_rows = connection.execute(
                select(error_ledger_table.c.exception_branch, func.count())
                .where(*ledger_filters, error_ledger_table.c.exception_branch.is_not(None))
                .group_by(error_ledger_table.c.exception_branch)
            ).all()
            decision_rows = connection.execute(
                select(error_ledger_table.c.handle_status, func.count())
                .where(*ledger_filters)
                .group_by(error_ledger_table.c.handle_status)
            ).all()
            fallback_rows = connection.execute(
                select(error_ledger_table.c.fallback_path, func.count())
                .where(*ledger_filters, error_ledger_table.c.fallback_path.is_not(None))
                .group_by(error_ledger_table.c.fallback_path)
            ).all()
            review_count = connection.execute(
                select(func.count()).select_from(human_review_table).where(*review_filters)
            ).scalar_one()
            ledger_sources = connection.execute(
                select(error_ledger_table.c.rag_source)
                .where(*ledger_filters, error_ledger_table.c.rag_source.is_not(None))
                .order_by(error_ledger_table.c.id)
            ).scalars()
            rag_source_rows = connection.execute(
                select(rag_retrieval_log_table.c.sources)
                .where(*rag_filters, rag_retrieval_log_table.c.sources.is_not(None))
                .order_by(rag_retrieval_log_table.c.id)
            ).scalars()

        total_rows = int(task_row["total_bank_rows"] or 0)
        created_at = task_row["created_at"]
        return TaskReportMetrics(
            task_id=task_id,
            user_id=user_id,
            recon_date=created_at.isoformat() if created_at is not None else "",
            source_a_rows=total_rows,
            source_b_rows=int(task_row["total_clear_rows"] or 0),
            auto_fixed_rows=int(task_row["auto_fixed_rows"] or 0),
            auto_fix_rate=(round(int(task_row["auto_fixed_rows"] or 0) / total_rows, 4) if total_rows else 0.0),
            ai_processed_rows=int(task_row["ai_processed_rows"] or 0),
            pending_human_count=int(task_row["pending_human_rows"] or 0),
            review_count=int(review_count),
            hold_count=int(ledger_totals[1] or 0),
            discrepancy_amount_total=Decimal(str(ledger_totals[0] or "0")),
            exception_dist={str(key): int(value) for key, value in exception_rows},
            agent_decision_dist={str(key): int(value) for key, value in decision_rows},
            fallback_dist={str(key): int(value) for key, value in fallback_rows},
            total_tokens=int(task_row["total_llm_tokens"] or 0),
            total_cost=Decimal(str(task_row["total_llm_cost"] or "0")).quantize(
                Decimal("0.0001")
            ),
            offline=self._read_offline_snapshot(),
            rag_sources=self._collect_rag_sources(ledger_sources, rag_source_rows),
        )

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        reconciliation_task_table.metadata.create_all(self._engine, tables=[reconciliation_task_table])
        error_ledger_table.metadata.create_all(self._engine, tables=[error_ledger_table])
        human_review_table.metadata.create_all(self._engine, tables=[human_review_table])
        rag_retrieval_log_table.metadata.create_all(self._engine, tables=[rag_retrieval_log_table])
        self._initialized = True

    def _collect_rag_sources(self, ledger_sources, rag_source_rows) -> list[str]:
        sources: list[str] = []
        for source in ledger_sources:
            if source not in sources:
                sources.append(source)
        for row in rag_source_rows:
            values = json.loads(row) if isinstance(row, str) else row
            for source in values:
                if source not in sources:
                    sources.append(source)
        return sources

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

    def _read_offline_snapshot(self) -> OfflineMetrics | OfflineNoSnapshot:
        if not self._rag_snapshot_path.exists() or not self._schema_snapshot_path.exists():
            return OfflineNoSnapshot(status="no_snapshot")
        rag_snapshot = json.loads(self._rag_snapshot_path.read_text(encoding="utf-8"))
        schema_snapshot = json.loads(self._schema_snapshot_path.read_text(encoding="utf-8"))
        evaluated_at = max(rag_snapshot["evaluated_at"], schema_snapshot["evaluated_at"])
        return OfflineMetrics(
            rag_recall_at5=rag_snapshot["rag_recall_at5"],
            rag_mrr=rag_snapshot["rag_mrr"],
            schema_conformance_rate=schema_snapshot["schema_conformance_rate"],
            evaluated_at=evaluated_at,
        )


metrics_service = MetricsService()

from decimal import Decimal

from pydantic import BaseModel

from bank_reconciliation_agent.schemas.metrics import OfflineMetrics, OfflineNoSnapshot


class TaskReportMetrics(BaseModel):
    task_id: str
    user_id: str
    recon_date: str
    source_a_rows: int
    source_b_rows: int
    auto_fixed_rows: int
    auto_fix_rate: float
    ai_processed_rows: int
    pending_human_count: int
    review_count: int
    hold_count: int
    discrepancy_amount_total: Decimal
    exception_dist: dict[str, int]
    agent_decision_dist: dict[str, int]
    fallback_dist: dict[str, int]
    total_tokens: int
    total_cost: Decimal
    offline: OfflineMetrics | OfflineNoSnapshot
    rag_sources: list[str]

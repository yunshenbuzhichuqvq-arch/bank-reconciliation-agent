from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class OnlineMetrics(BaseModel):
    auto_fix_rate: float
    pending_human_count: int
    hung_count: int
    exception_dist: dict[str, int]
    fallback_dist: dict[str, int]
    total_tokens: int
    total_cost: Decimal
    confidence_dist: dict[str, int]


class OfflineNoSnapshot(BaseModel):
    status: Literal["no_snapshot"]


class OfflineMetrics(BaseModel):
    rag_recall_at5: float
    rag_mrr: float
    schema_conformance_rate: float
    evaluated_at: str


class UnavailableMetrics(BaseModel):
    latency: Literal["no_data_source"]
    agent_accuracy: Literal["no_ground_truth"]


class DashboardMetricsResponse(BaseModel):
    online: OnlineMetrics
    offline: OfflineMetrics | OfflineNoSnapshot
    unavailable: UnavailableMetrics

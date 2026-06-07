from typing import Literal

from pydantic import BaseModel, Field


class RagSourceRef(BaseModel):
    source: str
    score: float | None = None


class PendingReviewItem(BaseModel):
    queue_id: int
    error_type: str
    exception_branch: str | None
    risk_level: str
    ai_suggestion: str
    ai_confidence: float | None
    ai_reason: str | None
    rag_sources: list[RagSourceRef]
    similar_historical_cases: int = 0
    historical_approve_rate: str = "0%"


class PendingReviewListResponse(BaseModel):
    scenario_type: str = "BANK_ENTERPRISE"
    items: list[PendingReviewItem]
    total: int


class ReviewActionRequest(BaseModel):
    action: Literal["APPROVED_MATCH", "FORCE_HOLD"]
    handler_username: str
    remark: str | None = None


class ReviewResultResponse(BaseModel):
    queue_id: int
    current_status: str
    memory_updated: dict[str, bool] = Field(
        default_factory=lambda: {"short_term": False, "long_term": False}
    )

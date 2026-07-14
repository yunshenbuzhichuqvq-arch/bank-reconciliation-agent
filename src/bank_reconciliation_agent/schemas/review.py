from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_serializer


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
    task_id: str
    flow_id: str
    bank_serial_no: str | None = None
    clearing_serial_no: str | None = None
    bank_amount: Decimal | None = None
    clear_amount: Decimal | None = None
    discrepancy_amount: Decimal

    @field_serializer("bank_amount", "clear_amount", "discrepancy_amount")
    def serialize_decimal_str(self, v: Decimal | None) -> str | None:
        if v is None:
            return None
        return str(v)


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

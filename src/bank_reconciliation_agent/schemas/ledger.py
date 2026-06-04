from decimal import Decimal

from pydantic import BaseModel


class LedgerQuery(BaseModel):
    user_id: str = "demo_user"
    task_id: str | None = None
    scenario_type: str | None = None
    error_type: str | None = None
    handle_status: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    page: int = 1
    page_size: int = 20


class LedgerRow(BaseModel):
    id: int
    task_id: str
    scenario_type: str
    flow_id: str
    error_type: str
    discrepancy_amount: Decimal
    ai_cleaned_json: dict[str, str | None] | None = None
    ai_audit_opinion: str | None
    ai_confidence: Decimal | None
    rag_source: str | None
    handle_status: str

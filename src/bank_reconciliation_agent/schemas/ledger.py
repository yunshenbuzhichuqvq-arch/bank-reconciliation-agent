from decimal import Decimal

from pydantic import BaseModel


class LedgerQuery(BaseModel):
    task_id: str | None = None
    error_type: str | None = None
    handle_status: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    page: int = 1
    page_size: int = 20


class LedgerRow(BaseModel):
    id: int
    task_id: str
    flow_id: str
    error_type: str
    exception_branch: str | None = None
    bank_amount: Decimal | None
    clear_amount: Decimal | None
    discrepancy_amount: Decimal
    ai_audit_opinion: str | None
    ai_confidence: Decimal | None
    rag_source: str | None
    fallback_path: str | None = None
    handle_status: str

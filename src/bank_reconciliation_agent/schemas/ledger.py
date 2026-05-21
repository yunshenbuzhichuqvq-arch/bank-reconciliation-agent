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
    error_type: str
    discrepancy_amount: Decimal
    ai_audit_opinion: str | None
    rag_source: str | None
    handle_status: str


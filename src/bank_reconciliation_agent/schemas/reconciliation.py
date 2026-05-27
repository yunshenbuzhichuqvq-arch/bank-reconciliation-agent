from pydantic import BaseModel


class ReconciliationUploadResponse(BaseModel):
    task_id: str
    total_bank_rows: int
    total_clear_rows: int
    auto_fixed_rows: int
    pending_ai_rows: int
    pending_human_rows: int


class ReconciliationStartResponse(BaseModel):
    task_id: str
    status: str


class ReconciliationStatusResponse(BaseModel):
    task_id: str
    status: str
    auto_fixed_rows: int
    pending_ai_rows: int
    ai_processed_rows: int
    pending_human_rows: int
    unresolved_rows: int


class ReconciliationExceptionItem(BaseModel):
    flow_id: str
    status: str
    error_type: str
    bank_amount: str | None
    clear_amount: str | None
    amount_diff: str | None


class ReconciliationExceptionListResponse(BaseModel):
    task_id: str
    total: int
    items: list[ReconciliationExceptionItem]

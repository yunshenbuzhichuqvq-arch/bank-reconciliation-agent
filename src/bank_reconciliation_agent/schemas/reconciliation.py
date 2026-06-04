from pydantic import BaseModel


class ReconciliationUploadResponse(BaseModel):
    task_id: str
    scenario_type: str = "BANK_ENTERPRISE"
    status: str = "UPLOADED"
    total_source_a_rows: int
    total_source_b_rows: int
    auto_fixed_rows: int
    pending_ai_rows: int
    pending_human_rows: int


class ReconciliationStartResponse(BaseModel):
    task_id: str
    status: str


class ReconciliationStatusResponse(BaseModel):
    task_id: str
    status: str
    scenario_type: str
    auto_fixed_rows: int
    pending_ai_rows: int
    ai_processed_rows: int
    pending_human_rows: int
    unresolved_rows: int


class ReconciliationRagEvidence(BaseModel):
    chunk_id: str
    source: str
    source_name: str
    source_url: str
    source_file: str
    section_title: str
    element_type: str
    business_tags: list[str]
    score: float
    content: str


class ReconciliationAuditDecision(BaseModel):
    flow_id: str
    decision: str
    risk_level: str
    reason: str
    evidence: list[ReconciliationRagEvidence]
    confidence: float


class ReconciliationExceptionItem(BaseModel):
    flow_id: str
    status: str
    error_type: str
    source_a_amount: str | None
    source_b_amount: str | None
    amount_diff: str | None
    rag_evidence: list[ReconciliationRagEvidence]
    audit_decision: ReconciliationAuditDecision


class ReconciliationExceptionListResponse(BaseModel):
    task_id: str
    total: int
    items: list[ReconciliationExceptionItem]

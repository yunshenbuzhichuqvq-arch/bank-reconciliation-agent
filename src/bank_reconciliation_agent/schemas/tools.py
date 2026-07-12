from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from bank_reconciliation_agent.schemas.rag import RagSearchItem


ToolName = Literal["search_rules", "load_confirmed_cases", "lookup_t1_context"]
ToolStatus = Literal["SUCCEEDED", "EMPTY", "FAILED"]
ToolErrorType = Literal[
    "UNKNOWN_TOOL",
    "VALIDATION_ERROR",
    "PERMISSION_DENIED",
    "TIMEOUT",
    "TRANSIENT_READ_ERROR",
    "INTERNAL_ERROR",
    "CIRCUIT_OPEN",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolContext(_StrictModel):
    user_id: str
    task_id: str
    flow_id: str
    scenario_type: Literal["BANK_ENTERPRISE", "BANK_CLEARING"]
    exception_branch: str
    fallback_level: Literal[0, 1, 2, 3] = 0

    @field_validator("user_id", "task_id", "flow_id")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must be a non-empty string")
        return stripped

    @field_validator("exception_branch")
    @classmethod
    def _strip_branch(cls, value: str) -> str:
        return value.strip()


class SearchRulesArgs(_StrictModel):
    query: str


class LoadConfirmedCasesArgs(_StrictModel):
    pass


class LookupT1ContextArgs(_StrictModel):
    pass


class SearchRulesOutput(_StrictModel):
    items: list[RagSearchItem]
    rewritten_query: str | None = None


class ConfirmedCase(_StrictModel):
    flow_id: str
    error_type: str
    exception_branch: str | None = None
    ai_audit_opinion: str | None = None
    ai_confidence: Decimal | None = None
    handle_status: str


class ConfirmedCasesOutput(_StrictModel):
    items: list[ConfirmedCase]


class T1ContextOutput(_StrictModel):
    flow_id: str
    accounting_date: date


class ToolAttemptRecord(_StrictModel):
    attempt: Literal[1, 2]
    status: ToolStatus
    duration_ms: float
    error_type: ToolErrorType | None = None
    retryable: bool = False

    @field_validator("duration_ms")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("duration_ms must be non-negative")
        return round(value, 3)


class ToolCallResult(_StrictModel):
    tool_name: str
    status: ToolStatus
    success: bool = False
    result: object | None = None
    error_type: ToolErrorType | None = None
    fallback_reason: str | None = None
    retryable: bool = False
    attempt: Literal[1, 2]
    retry_recovered: bool = False
    duration_ms: float
    attempts: list[ToolAttemptRecord]

    @field_validator("duration_ms")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("duration_ms must be non-negative")
        return round(value, 3)

    @model_validator(mode="after")
    def _enforce_status_invariants(self) -> ToolCallResult:
        if not self.attempts:
            raise ValueError("attempts must contain at least one record")

        derived_success = self.status != "FAILED"
        if "success" in self.model_fields_set and self.success != derived_success:
            raise ValueError("success is derived from status and cannot be set independently")
        object.__setattr__(self, "success", derived_success)

        if self.status == "SUCCEEDED":
            if self.result is None:
                raise ValueError("SUCCEEDED result must not be None")
            if self.error_type is not None or self.fallback_reason is not None:
                raise ValueError("SUCCEEDED must not carry error metadata")
            if self.retryable:
                raise ValueError("SUCCEEDED must not be retryable")
        elif self.status == "EMPTY":
            if self.result is not None:
                raise ValueError("EMPTY result must be None")
            if self.error_type is not None or self.fallback_reason is not None:
                raise ValueError("EMPTY must not carry error metadata")
            if self.retryable:
                raise ValueError("EMPTY must not be retryable")
        else:  # FAILED
            if self.result is not None:
                raise ValueError("FAILED result must be None")
            if self.error_type is None:
                raise ValueError("FAILED must carry error_type")
            if not self.fallback_reason:
                raise ValueError("FAILED must carry fallback_reason")

        return self

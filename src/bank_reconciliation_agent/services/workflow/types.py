from __future__ import annotations

from typing import Any, NotRequired, Protocol, TypedDict

from bank_reconciliation_agent.schemas.tools import ToolCallResult, ToolContext
from bank_reconciliation_agent.services.trace import NoOpRecorder, TraceRecorder


Recorder = TraceRecorder | NoOpRecorder

REVERSAL_HINTS = ("冲正", "红冲", "退款", "抹账", "撤销")
TRACE_BRANCHES = {"BE-R005", "BE-R006", "BC-R003"}
BANK_ENTERPRISE_LLM_AUDIT_BRANCHES = {"BE-R007"}


class ReconciliationState(TypedDict):
    task_id: str
    user_id: str
    thread_id: str
    scenario_type: str
    current_queue_id: int | None
    source_a_item: dict[str, Any]
    source_b_item: dict[str, Any]
    error_type: str | None
    exception_branch: str | None
    math_result: dict[str, Any]
    extraction_result: dict[str, Any]
    rag_context: list[dict[str, Any]]
    audit_decision: dict[str, Any]
    confidence: float | None
    retry_count: int
    fallback_level: int
    next_action: str
    error_message: str | None
    agent_logs: list[dict[str, Any]]
    stream_seq: NotRequired[int]
    rag_query: NotRequired[str]
    rag_response: NotRequired[dict[str, Any]]
    fallback_path: NotRequired[str]
    fallback_cases: NotRequired[list[dict[str, Any]]]
    t1_candidate: NotRequired[dict[str, str] | None]
    fuzzy_candidate: NotRequired[dict[str, str] | None]
    recorder: NotRequired[Recorder]


class ToolExecutorProtocol(Protocol):
    def execute(
        self,
        name: str,
        args: Any,
        context: ToolContext,
    ) -> ToolCallResult: ...

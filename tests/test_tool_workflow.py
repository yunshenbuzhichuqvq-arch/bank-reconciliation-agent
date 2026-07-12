from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.schemas.rag import RagSearchItem
from bank_reconciliation_agent.schemas.tools import (
    ConfirmedCase,
    ConfirmedCasesOutput,
    SearchRulesOutput,
    T1ContextOutput,
    ToolAttemptRecord,
    ToolCallResult,
    ToolContext,
)
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item


SECRET_QUERY = "SENSITIVE_QUERY_TEXT should never leak"
SECRET_RULE_BODY = "TOP_SECRET_RULE_CONTENT should never leak"
SECRET_OPINION = "PRIVATE_HISTORICAL_OPINION should never leak"


# --------------------------------------------------------------------------- #
# Canned tool results
# --------------------------------------------------------------------------- #


def _rag_item(chunk_id: str = "rule-1") -> RagSearchItem:
    return RagSearchItem(
        chunk_id=chunk_id,
        source="rule",
        source_name="rules",
        source_url="local://rules",
        source_file="rules.yaml",
        section_title="R",
        element_type="rule",
        business_tags=["x"],
        score=0.9,
        content=SECRET_RULE_BODY,
    )


def _succeeded(tool_name: str, result: object) -> ToolCallResult:
    return ToolCallResult(
        tool_name=tool_name,
        status="SUCCEEDED",
        result=result,
        attempt=1,
        duration_ms=1.0,
        attempts=[ToolAttemptRecord(attempt=1, status="SUCCEEDED", duration_ms=1.0)],
    )


def _empty(tool_name: str) -> ToolCallResult:
    return ToolCallResult(
        tool_name=tool_name,
        status="EMPTY",
        attempt=1,
        duration_ms=1.0,
        attempts=[ToolAttemptRecord(attempt=1, status="EMPTY", duration_ms=1.0)],
    )


def _failed(tool_name: str, error_type: str, fallback_reason: str) -> ToolCallResult:
    return ToolCallResult(
        tool_name=tool_name,
        status="FAILED",
        error_type=error_type,
        fallback_reason=fallback_reason,
        retryable=False,
        attempt=1,
        duration_ms=1.0,
        attempts=[
            ToolAttemptRecord(
                attempt=1, status="FAILED", duration_ms=1.0, error_type=error_type
            )
        ],
    )


def _search_succeeded(chunk_id: str = "rule-1") -> ToolCallResult:
    return _succeeded("search_rules", SearchRulesOutput(items=[_rag_item(chunk_id)]))


def _cases_succeeded() -> ToolCallResult:
    return _succeeded(
        "load_confirmed_cases",
        ConfirmedCasesOutput(
            items=[
                ConfirmedCase(
                    flow_id="FC-1",
                    error_type="AMOUNT_MISMATCH",
                    exception_branch="BE-R002",
                    ai_audit_opinion=SECRET_OPINION,
                    ai_confidence=Decimal("0.90"),
                    handle_status="FIXED",
                )
            ]
        ),
    )


def _t1_succeeded(flow_id: str = "CORE-T1") -> ToolCallResult:
    return _succeeded(
        "lookup_t1_context",
        T1ContextOutput(flow_id=flow_id, accounting_date=date(2026, 6, 11)),
    )


class RecordingToolExecutor:
    def __init__(self, responses: dict[str, list[ToolCallResult]]) -> None:
        self._responses = {name: list(items) for name, items in responses.items()}
        self.calls: list[tuple[str, int]] = []
        self.contexts: list[ToolContext] = []

    def execute(self, name: str, args: Any, context: ToolContext) -> ToolCallResult:
        del args
        self.calls.append((name, context.fallback_level))
        self.contexts.append(context)
        queue = self._responses.get(name)
        if not queue:
            raise AssertionError(f"unexpected tool call: {name}")
        return queue.pop(0)

    def count(self, name: str) -> int:
        return sum(1 for call_name, _ in self.calls if call_name == name)


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #


class CountingAuditAgent:
    prompt_version = "vtest"

    def __init__(self, confidences: list[float]) -> None:
        self.confidences = confidences
        self.calls = 0

    def decide_with_llm(self, flow_id: str, **kwargs: Any) -> AuditDecision:
        confidence = self.confidences[min(self.calls, len(self.confidences) - 1)]
        self.calls += 1
        evidence = kwargs["evidence"]
        return AuditDecision(
            flow_id=flow_id,
            decision="PENDING_HUMAN",
            risk_level="MEDIUM",
            reason="audit",
            ai_suggestion="PENDING_HUMAN",
            evidence=evidence,
            confidence=confidence,
            fallback_applied=False,
            fallback_level=0,
            next_action="PENDING_HUMAN",
        )


class CountingTraceAgent:
    prompt_version = "vtest"

    def __init__(self, *, confidence: float = 0.9) -> None:
        self.confidence = confidence
        self.calls: list[dict[str, Any]] = []

    def trace(self, *, flow_id: str, cutoff_t1_context: dict[str, str] | None = None, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        self.calls.append({"flow_id": flow_id, "cutoff_t1_context": cutoff_t1_context})
        return {
            "trace_found": cutoff_t1_context is not None,
            "related_flow_ids": [],
            "trace_summary": "trace",
            "confidence": self.confidence,
        }


class ForbiddenTraceAgent:
    def trace(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("TraceAgent must not be called")


class ForbiddenAuditAgent:
    def decide_with_llm(self, **kwargs: Any) -> AuditDecision:
        raise AssertionError("AuditAgent must not be called")


class NoopExtractionAgent:
    def extract(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("ExtractionAgent must not be called")


def _state(exception_branch: str, *, error_type: str = "AMOUNT_MISMATCH") -> ReconciliationState:
    return {
        "task_id": "TASK-TW",
        "user_id": "demo_user",
        "thread_id": "TASK-TW",
        "scenario_type": "BANK_CLEARING" if exception_branch == "BC-R003" else "BANK_ENTERPRISE",
        "current_queue_id": None,
        "source_a_item": {"flow_id": "FLOW-1", "summary": "s"},
        "source_b_item": {"flow_id": "FLOW-1", "summary": "s"},
        "error_type": error_type,
        "exception_branch": exception_branch,
        "math_result": {"bank_amount": "100.00", "clear_amount": "99.00", "amount_diff": "1.00"},
        "extraction_result": {},
        "rag_context": [],
        "audit_decision": {},
        "confidence": None,
        "retry_count": 0,
        "fallback_level": 0,
        "next_action": "",
        "error_message": None,
        "agent_logs": [],
        "rag_query": SECRET_QUERY,
    }


# --------------------------------------------------------------------------- #
# search_rules matrix
# --------------------------------------------------------------------------- #


def test_search_rules_succeeded_continues_to_audit() -> None:
    executor = RecordingToolExecutor({"search_rules": [_search_succeeded()]})
    audit = CountingAuditAgent([0.9])

    result = run_item(
        _state("BE-R002"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=ForbiddenTraceAgent(),
        audit_agent=audit,
        tool_executor=executor,
    )

    assert audit.calls == 1
    assert result["rag_context"][0]["chunk_id"] == "rule-1"
    assert result["next_action"] == "PENDING_HUMAN"


def test_search_rules_empty_short_circuits_to_human_with_zero_audit() -> None:
    executor = RecordingToolExecutor({"search_rules": [_empty("search_rules")]})
    audit = CountingAuditAgent([0.9])

    result = run_item(
        _state("BE-R002"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=ForbiddenTraceAgent(),
        audit_agent=audit,
        tool_executor=executor,
    )

    assert audit.calls == 0
    assert executor.count("load_confirmed_cases") == 0
    assert result["next_action"] == "PENDING_HUMAN"
    assert result["fallback_path"] == "HUMAN"
    assert result["rag_context"] == []


def test_search_rules_failed_short_circuits_to_human_with_zero_audit() -> None:
    executor = RecordingToolExecutor(
        {"search_rules": [_failed("search_rules", "CIRCUIT_OPEN", "RAG_CIRCUIT_OPEN")]}
    )
    audit = CountingAuditAgent([0.9])

    result = run_item(
        _state("BE-R002"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=ForbiddenTraceAgent(),
        audit_agent=audit,
        tool_executor=executor,
    )

    assert audit.calls == 0
    assert executor.count("load_confirmed_cases") == 0
    assert result["next_action"] == "PENDING_HUMAN"
    assert result["error_message"] == "RAG_CIRCUIT_OPEN"


def test_breaker_open_and_real_empty_are_distinguishable_in_logs_but_both_human() -> None:
    open_executor = RecordingToolExecutor(
        {"search_rules": [_failed("search_rules", "CIRCUIT_OPEN", "RAG_CIRCUIT_OPEN")]}
    )
    empty_executor = RecordingToolExecutor({"search_rules": [_empty("search_rules")]})

    open_result = run_item(
        _state("BE-R002"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=ForbiddenTraceAgent(),
        audit_agent=CountingAuditAgent([0.9]),
        tool_executor=open_executor,
    )
    empty_result = run_item(
        _state("BE-R002"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=ForbiddenTraceAgent(),
        audit_agent=CountingAuditAgent([0.9]),
        tool_executor=empty_executor,
    )

    open_tool_log = next(
        row for row in open_result["agent_logs"] if row["agent_name"] == "ToolExecutor"
    )
    empty_tool_log = next(
        row for row in empty_result["agent_logs"] if row["agent_name"] == "ToolExecutor"
    )
    assert open_tool_log["status"] == "FAILED"
    assert open_tool_log["error_type"] == "CIRCUIT_OPEN"
    assert empty_tool_log["status"] == "EMPTY"
    assert empty_tool_log["error_type"] is None
    assert open_result["next_action"] == "PENDING_HUMAN"
    assert empty_result["next_action"] == "PENDING_HUMAN"


# --------------------------------------------------------------------------- #
# load_confirmed_cases matrix
# --------------------------------------------------------------------------- #


def test_load_confirmed_cases_succeeded_runs_second_audit() -> None:
    executor = RecordingToolExecutor(
        {"search_rules": [_search_succeeded()], "load_confirmed_cases": [_cases_succeeded()]}
    )
    audit = CountingAuditAgent([0.4, 0.9])

    result = run_item(
        _state("BE-R002"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=CountingTraceAgent(),
        audit_agent=audit,
        tool_executor=executor,
    )

    assert audit.calls == 2
    assert executor.calls[-1] == ("load_confirmed_cases", 2)
    assert result["fallback_level"] == 2
    assert result["fallback_path"] == "L1->L2"


def test_load_confirmed_cases_empty_stops_before_second_audit_and_l3() -> None:
    executor = RecordingToolExecutor(
        {"search_rules": [_search_succeeded()], "load_confirmed_cases": [_empty("load_confirmed_cases")]}
    )
    audit = CountingAuditAgent([0.4])
    trace = CountingTraceAgent()

    result = run_item(
        _state("BE-R002"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=trace,
        audit_agent=audit,
        tool_executor=executor,
    )

    assert audit.calls == 1
    assert trace.calls == []
    assert result["fallback_path"] == "L1->L2->HUMAN"
    assert result["next_action"] == "PENDING_HUMAN"


def test_load_confirmed_cases_failed_stops_before_second_audit_and_l3() -> None:
    executor = RecordingToolExecutor(
        {
            "search_rules": [_search_succeeded()],
            "load_confirmed_cases": [
                _failed("load_confirmed_cases", "TIMEOUT", "TOOL_TIMEOUT")
            ],
        }
    )
    audit = CountingAuditAgent([0.4])
    trace = CountingTraceAgent()

    result = run_item(
        _state("BE-R002"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=trace,
        audit_agent=audit,
        tool_executor=executor,
    )

    assert audit.calls == 1
    assert trace.calls == []
    assert result["fallback_path"] == "L1->L2->HUMAN"
    assert result["next_action"] == "PENDING_HUMAN"


def test_high_confidence_l1_never_calls_load_confirmed_cases() -> None:
    executor = RecordingToolExecutor({"search_rules": [_search_succeeded()]})
    audit = CountingAuditAgent([0.95])

    result = run_item(
        _state("BE-R002"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=ForbiddenTraceAgent(),
        audit_agent=audit,
        tool_executor=executor,
    )

    assert executor.count("load_confirmed_cases") == 0
    assert audit.calls == 1
    assert result["fallback_path"] == "L1"


# --------------------------------------------------------------------------- #
# lookup_t1_context matrix (BC-R003)
# --------------------------------------------------------------------------- #


def test_lookup_t1_succeeded_feeds_trace_before_search() -> None:
    executor = RecordingToolExecutor(
        {"lookup_t1_context": [_t1_succeeded("CORE-T1")], "search_rules": [_search_succeeded()]}
    )
    trace = CountingTraceAgent()
    audit = CountingAuditAgent([0.95])

    result = run_item(
        _state("BC-R003", error_type="CUTOFF_CROSS_DAY"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=trace,
        audit_agent=audit,
        tool_executor=executor,
    )

    assert [name for name, _ in executor.calls] == ["lookup_t1_context", "search_rules"]
    assert trace.calls[0]["cutoff_t1_context"] == {
        "flow_id": "CORE-T1",
        "accounting_date": "2026-06-11",
    }
    assert result["next_action"] == "PENDING_HUMAN"


def test_lookup_t1_empty_continues_with_none_context() -> None:
    executor = RecordingToolExecutor(
        {"lookup_t1_context": [_empty("lookup_t1_context")], "search_rules": [_search_succeeded()]}
    )
    trace = CountingTraceAgent()
    audit = CountingAuditAgent([0.95])

    run_item(
        _state("BC-R003", error_type="CUTOFF_CROSS_DAY"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=trace,
        audit_agent=audit,
        tool_executor=executor,
    )

    assert trace.calls[0]["cutoff_t1_context"] is None
    assert executor.count("search_rules") == 1
    assert audit.calls == 1


def test_lookup_t1_failed_stops_before_trace_search_and_audit() -> None:
    executor = RecordingToolExecutor(
        {"lookup_t1_context": [_failed("lookup_t1_context", "TIMEOUT", "TOOL_TIMEOUT")]}
    )
    trace = ForbiddenTraceAgent()
    audit = ForbiddenAuditAgent()

    result = run_item(
        _state("BC-R003", error_type="CUTOFF_CROSS_DAY"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=trace,
        audit_agent=audit,
        tool_executor=executor,
    )

    assert executor.count("search_rules") == 0
    assert result["next_action"] == "PENDING_HUMAN"
    assert result["error_message"] == "TOOL_TIMEOUT"


def test_lookup_t1_ignores_fake_state_t1_candidate() -> None:
    executor = RecordingToolExecutor(
        {"lookup_t1_context": [_t1_succeeded("REAL-CORE")], "search_rules": [_search_succeeded()]}
    )
    trace = CountingTraceAgent()
    state = _state("BC-R003", error_type="CUTOFF_CROSS_DAY")
    state["t1_candidate"] = {"flow_id": "FAKE-INJECTED", "accounting_date": "1999-01-01"}

    run_item(
        state,
        extraction_agent=NoopExtractionAgent(),
        trace_agent=trace,
        audit_agent=CountingAuditAgent([0.95]),
        tool_executor=executor,
    )

    assert trace.calls[0]["cutoff_t1_context"] == {
        "flow_id": "REAL-CORE",
        "accounting_date": "2026-06-11",
    }


# --------------------------------------------------------------------------- #
# Safe projection in agent logs
# --------------------------------------------------------------------------- #

_FORBIDDEN_VALUES = {SECRET_QUERY, SECRET_RULE_BODY, SECRET_OPINION}


def _assert_no_sensitive(node: object) -> None:
    if isinstance(node, dict):
        for value in node.values():
            _assert_no_sensitive(value)
    elif isinstance(node, (list, tuple, set)):
        for item in node:
            _assert_no_sensitive(item)
    elif isinstance(node, str):
        for secret in _FORBIDDEN_VALUES:
            assert secret not in node, f"sensitive value leaked: {node!r}"


def test_tool_executor_logs_only_safe_projection() -> None:
    executor = RecordingToolExecutor(
        {"search_rules": [_search_succeeded()], "load_confirmed_cases": [_cases_succeeded()]}
    )
    audit = CountingAuditAgent([0.4, 0.9])

    result = run_item(
        _state("BE-R002"),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=CountingTraceAgent(),
        audit_agent=audit,
        tool_executor=executor,
    )

    tool_logs = [row for row in result["agent_logs"] if row["agent_name"] == "ToolExecutor"]
    assert len(tool_logs) == 2
    for row in tool_logs:
        assert "query" not in row
        assert "content" not in row
        assert "result" not in row
        assert "evidence_ids" in row
        _assert_no_sensitive(row)

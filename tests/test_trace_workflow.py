"""Tests for TraceRecorder integration into the reconciliation workflow.

Covers: real Route/Tool/Agent/Guard spans recorded by ``run_item``, terminal
close + snapshot managed by the outer service, no ``SKIPPED`` spans on early
Tool short-circuit, complete Fallback Trace for captured agent errors, batch
write failure isolation and process-local counters.

Refs: TASK-29.3
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgentError
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from bank_reconciliation_agent.schemas.trace import SpanStatus, SpanType, WorkflowOutcome
from bank_reconciliation_agent.services.reconciliation import (
    ReconciliationMatchResult,
    ReconciliationService,
)
from bank_reconciliation_agent.services.trace import (
    TraceRecorder,
    TraceService,
    validate_trace_snapshot,
)
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item
from tests.tool_workflow_helpers import RetrieverBackedToolExecutor, failed as _failed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evidence() -> RagSearchItem:
    return RagSearchItem(
        chunk_id="rule-001",
        source="rules.md#rule",
        source_name="规则",
        source_url="https://example.com/rule",
        source_file="rules.md",
        section_title="rule",
        element_type="paragraph",
        business_tags=["bank_enterprise"],
        score=0.9,
        content="规则证据",
    )


class StaticRetriever:
    def search(self, request):
        del request
        return RagSearchResponse(items=[_evidence()])


class SpyExtractionAgent:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, *, flow_id: str, summary: str, remark: str | None):
        del summary, remark
        self.calls.append(flow_id)
        return {
            "standard_type": "REVERSAL",
            "original_flow_id": "FLOW-ORIGINAL-001",
            "cleaned_remark": "客户退款冲正",
            "confidence": 0.92,
        }


class SpyTraceAgent:
    def trace(self, *, flow_id: str, summary, transaction_date, amount, remark):
        del flow_id, summary, transaction_date, amount, remark
        return {
            "trace_found": True,
            "related_flow_ids": ["FLOW-T1-001"],
            "trace_summary": "线索",
            "confidence": 0.9,
        }


class SpyAuditAgent:
    def decide_with_llm(
        self,
        flow_id: str,
        error_type: str,
        exception_branch: str | None,
        bank_amount: str | None,
        clear_amount: str | None,
        amount_diff: str | None,
        evidence: list[RagSearchItem],
    ) -> AuditDecision:
        del error_type, exception_branch, bank_amount, clear_amount, amount_diff
        return AuditDecision(
            flow_id=flow_id,
            decision="PENDING_HUMAN",
            risk_level="MEDIUM",
            reason="spy audit",
            ai_suggestion="PENDING_HUMAN",
            evidence=evidence,
            confidence=0.88,
            fallback_applied=False,
            fallback_level=0,
            next_action="PENDING_HUMAN",
        )


def _state(exception_branch: str, recorder: TraceRecorder) -> ReconciliationState:
    return {
        "task_id": "TASK-TR-001",
        "user_id": "demo_user",
        "thread_id": "THREAD-TR-001",
        "scenario_type": "BANK_ENTERPRISE",
        "current_queue_id": None,
        "source_a_item": {"flow_id": f"FLOW-{exception_branch}", "summary": "普通摘要"},
        "source_b_item": {"flow_id": f"FLOW-{exception_branch}", "summary": "普通摘要"},
        "error_type": "AMOUNT_MISMATCH",
        "exception_branch": exception_branch,
        "math_result": {
            "bank_amount": "100.00",
            "clear_amount": "99.00",
            "amount_diff": "1.00",
        },
        "extraction_result": {},
        "rag_context": [],
        "audit_decision": {},
        "confidence": None,
        "retry_count": 0,
        "fallback_level": 0,
        "next_action": "",
        "error_message": None,
        "agent_logs": [],
        "recorder": recorder,
    }


def _recorder() -> TraceRecorder:
    return TraceRecorder(user_id="demo_user", task_id="TASK-TR-001", flow_id="FLOW-BE-R002")


def _match_result(flow_id: str) -> ReconciliationMatchResult:
    return ReconciliationMatchResult(
        flow_id=flow_id,
        status="PENDING_HUMAN",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount=Decimal("100.00"),
        clear_amount=Decimal("99.00"),
        amount_diff=Decimal("1.00"),
    )


# ---------------------------------------------------------------------------
# 1. Real node spans recorded during run_item
# ---------------------------------------------------------------------------


def test_run_item_records_route_tool_agent_guard_spans() -> None:
    recorder = _recorder()
    run_item(
        _state("BE-R002", recorder),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        tool_executor=RetrieverBackedToolExecutor(retriever=StaticRetriever()),
    )
    recorder.close_root(
        status=SpanStatus.SUCCEEDED,
        outcome=WorkflowOutcome.PENDING_HUMAN,
        terminal_type=SpanType.FALLBACK,
    )
    spans = recorder.snapshot()
    validate_trace_snapshot(list(spans))

    types = [s.span_type for s in spans]
    assert types[0] == SpanType.WORKFLOW
    assert SpanType.ROUTE in types
    assert SpanType.TOOL in types
    assert SpanType.AGENT in types
    assert SpanType.GUARD in types
    # No SKIPPED node exists in the closed enum; only executed nodes are recorded.
    route = [s for s in spans if s.span_type == SpanType.ROUTE][0]
    assert route.name == "BE-R002"
    tool = [s for s in spans if s.span_type == SpanType.TOOL][0]
    assert tool.name == "search_rules"
    assert tool.outcome == "RESULT"
    assert tool.evidence_ids == ["rule-001"]
    agent = [s for s in spans if s.span_type == SpanType.AGENT][0]
    assert agent.name == "AuditAgent"


def test_agent_span_only_holds_token_fields() -> None:
    recorder = _recorder()
    run_item(
        _state("BE-R002", recorder),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        tool_executor=RetrieverBackedToolExecutor(retriever=StaticRetriever()),
    )
    recorder.close_root(
        status=SpanStatus.SUCCEEDED,
        outcome=WorkflowOutcome.PENDING_HUMAN,
        terminal_type=SpanType.FALLBACK,
    )
    spans = recorder.snapshot()
    tool = [s for s in spans if s.span_type == SpanType.TOOL][0]
    assert tool.prompt_tokens is None
    assert tool.model_name is None


# ---------------------------------------------------------------------------
# 2. Tool short-circuit does not emit downstream spans
# ---------------------------------------------------------------------------


class _SearchFailExecutor:
    def execute(self, name, args, context):
        del args, context
        assert name == "search_rules"
        return _failed("search_rules", "CIRCUIT_OPEN", "RAG_CIRCUIT_OPEN")


def test_tool_failed_short_circuit_has_no_agent_or_guard_spans() -> None:
    recorder = _recorder()
    run_item(
        _state("BE-R002", recorder),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        tool_executor=_SearchFailExecutor(),
    )
    recorder.close_root(
        status=SpanStatus.SUCCEEDED,
        outcome=WorkflowOutcome.PENDING_HUMAN,
        terminal_type=SpanType.FALLBACK,
    )
    spans = recorder.snapshot()
    validate_trace_snapshot(list(spans))

    types = [s.span_type for s in spans]
    assert SpanType.TOOL in types
    assert SpanType.AGENT not in types
    assert SpanType.GUARD not in types
    tool = [s for s in spans if s.span_type == SpanType.TOOL][0]
    assert tool.status == SpanStatus.FAILED
    assert tool.outcome is None
    assert tool.error_type == "CIRCUIT_OPEN"


# ---------------------------------------------------------------------------
# 3. Service-managed lifecycle: terminal, snapshot, persistence
# ---------------------------------------------------------------------------


def _sqlite_service() -> tuple[ReconciliationService, TraceService]:
    engine = create_engine("sqlite:///:memory:")
    service = ReconciliationService()
    service._engine = engine
    trace_service = TraceService(engine)
    return service, trace_service


def test_finalize_recorder_appends_fallback_terminal_for_pending_human() -> None:
    service = ReconciliationService()
    recorder = TraceRecorder(user_id="u", task_id="t", flow_id="f")
    decision = AuditDecision(
        flow_id="f",
        decision="PENDING_HUMAN",
        risk_level="MEDIUM",
        reason="r",
        ai_suggestion="PENDING_HUMAN",
        evidence=[],
        confidence=0.0,
        fallback_applied=True,
        next_action="PENDING_HUMAN",
    )
    spans = service._finalize_recorder(recorder, decision)
    validate_trace_snapshot(spans)
    terminals = [s for s in spans if s.span_type in {SpanType.FINAL, SpanType.FALLBACK}]
    assert len(terminals) == 1
    assert terminals[0].span_type == SpanType.FALLBACK
    assert terminals[0].outcome == "PENDING_HUMAN"


def test_finalize_recorder_appends_final_terminal_for_auto_fixed() -> None:
    service = ReconciliationService()
    recorder = TraceRecorder(user_id="u", task_id="t", flow_id="f")
    decision = AuditDecision(
        flow_id="f",
        decision="AUTO_FIXED",
        risk_level="LOW",
        reason="r",
        ai_suggestion="AUTO_FIXED",
        evidence=[_evidence()],
        confidence=0.9,
        next_action="AUTO_FIXED",
    )
    spans = service._finalize_recorder(recorder, decision)
    terminals = [s for s in spans if s.span_type in {SpanType.FINAL, SpanType.FALLBACK}]
    assert len(terminals) == 1
    assert terminals[0].span_type == SpanType.FINAL
    assert terminals[0].outcome == "AUTO_FIXED"


# ---------------------------------------------------------------------------
# 4. Failure isolation and process-local metrics
# ---------------------------------------------------------------------------


def test_persist_snapshot_write_failure_does_not_raise_and_counts_failure() -> None:
    engine = create_engine("sqlite:///:memory:")
    trace_service = TraceService(engine)
    recorder = TraceRecorder(user_id="u", task_id="t", flow_id="f")
    recorder.close_root(
        status=SpanStatus.SUCCEEDED,
        outcome=WorkflowOutcome.PENDING_HUMAN,
        terminal_type=SpanType.FALLBACK,
    )
    spans = list(recorder.snapshot())

    before = TraceService.metrics_snapshot()["trace_write_failure_count"]

    # Force a write failure by pointing save_trace at a broken engine.
    class _BrokenEngine:
        def begin(self):
            raise RuntimeError("db down")

    trace_service._engine = _BrokenEngine()
    trace_service._initialized = True
    ok = trace_service.persist_snapshot(user_id="u", task_id="t", flow_id="f", spans=spans)

    assert ok is False
    after = TraceService.metrics_snapshot()["trace_write_failure_count"]
    assert after == before + 1


def test_persist_snapshot_success_counts_success_and_is_readable() -> None:
    engine = create_engine("sqlite:///:memory:")
    trace_service = TraceService(engine)
    recorder = TraceRecorder(user_id="u", task_id="t", flow_id="f")
    with recorder.span(SpanType.TOOL, "search_rules", outcome="RESULT"):
        pass
    recorder.close_root(
        status=SpanStatus.SUCCEEDED,
        outcome=WorkflowOutcome.PENDING_HUMAN,
        terminal_type=SpanType.FALLBACK,
    )
    spans = list(recorder.snapshot())

    before = TraceService.metrics_snapshot()["trace_write_success_count"]
    ok = trace_service.persist_snapshot(user_id="u", task_id="t", flow_id="f", spans=spans)
    assert ok is True
    after = TraceService.metrics_snapshot()["trace_write_success_count"]
    assert after == before + 1

    stored = trace_service.get_spans(user_id="u", task_id="t", flow_id="f")
    assert [s.span_type for s in stored][0] == SpanType.WORKFLOW
    assert trace_service.count_runs(user_id="u", task_id="t", flow_id="f") == 1
    # Cross-user isolation.
    assert trace_service.count_runs(user_id="other", task_id="t", flow_id="f") == 0


def test_metrics_snapshot_marks_process_local_source() -> None:
    snapshot = TraceService.metrics_snapshot()
    assert snapshot["source"] == "runtime_memory"
    assert "trace_write_success_count" in snapshot
    assert "trace_write_failure_count" in snapshot


# ---------------------------------------------------------------------------
# 5. Captured agent error still yields a complete Fallback Trace
# ---------------------------------------------------------------------------


def test_agent_processing_error_still_produces_complete_fallback_trace(monkeypatch) -> None:
    service, trace_service = _sqlite_service()

    def boom(*, user_id, task_id, scenario_type, result, rag_query, recorder=None):
        del user_id, task_id, scenario_type, result, rag_query, recorder
        raise ExtractionAgentError("invalid LLM JSON")

    monkeypatch.setattr(service, "_run_workflow_for_result", boom)
    monkeypatch.setattr(service, "_engine", trace_service._engine)

    bundle = service._build_write_bundle(
        user_id="demo_user",
        task_id="TASK-TR-FALLBACK",
        scenario_type="BANK_ENTERPRISE",
        results=[_match_result("FLOW-ERR")],
    )
    assert len(bundle.trace_snapshots) == 1
    flow_id, trace_id, spans = bundle.trace_snapshots[0]
    assert flow_id == "FLOW-ERR"
    assert trace_id
    validate_trace_snapshot(spans)
    terminals = [s for s in spans if s.span_type in {SpanType.FINAL, SpanType.FALLBACK}]
    assert len(terminals) == 1
    assert terminals[0].span_type == SpanType.FALLBACK

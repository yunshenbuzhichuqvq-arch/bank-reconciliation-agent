"""Deterministic Trace Replay evidence runner.

Offline + Fake provider + hash embedding + local SQLite + non-production SLA.

All six scenarios enter the real exception workflow (``run_item``), so the
completeness denominator is fixed at 6. Five of them persist a structurally
valid Trace; the sixth deliberately fails the Trace write at the real
``ReconciliationService`` side-effect boundary, so the honest completeness is
``5/6``.

Scenarios:
1. Complete success (FINAL)                      — persisted, read back, validated
2. Tool timeout/failed -> Fallback               — persisted, read back, validated
3. LLM structured repair failure -> Fallback     — real Fake provider + structured boundary
4. Safety Guard blocked -> Fallback              — persisted, read back, validated
5. Cross-tenant Replay rejection                 — real FastAPI HTTP owner/non-owner requests
6. Trace batch write failure isolation           — real ReconciliationService core-txn boundary

``scenario_pass_count`` is judged per-scenario expectation (all six should pass:
6/6), while completeness stays honestly at ``5/6``.

Refs: TASK-29.15
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path


def _lock_offline_environment() -> None:
    """Enforce the offline / hash-embedding / local-SQLite contract this report
    claims, before any project service is imported.

    If the caller has already configured a non-SQLite database, a non-hash
    embedding backend, or enabled RAG reranker/hybrid/rewrite, we fail fast with
    a non-zero exit and touch nothing: no project import, no scenario, no report
    overwrite. When unset, we default to a file-backed local SQLite (visible
    across the connections used by the FastAPI TestClient), hash embedding and
    the three RAG flags disabled. A pre-configured SQLite DSN (e.g. the pytest
    test DB) is accepted as-is and never overridden.
    """
    dsn = os.environ.get("MYSQL_DSN")
    if dsn is not None and not dsn.startswith("sqlite"):
        sys.stderr.write(
            "eval_trace_replay refuses to run: MYSQL_DSN must be a SQLite DSN "
            "(got a non-SQLite database). No reports were written.\n"
        )
        raise SystemExit(2)
    embedding = os.environ.get("EMBEDDING_BACKEND")
    if embedding is not None and embedding != "hash":
        sys.stderr.write(
            "eval_trace_replay refuses to run: EMBEDDING_BACKEND must be 'hash' "
            f"(got {embedding!r}). No reports were written.\n"
        )
        raise SystemExit(2)
    false_values = {"false", "0", "no", "off"}
    for flag in ("ENABLE_RAG_RERANKER", "ENABLE_RAG_HYBRID", "ENABLE_RAG_REWRITE"):
        value = os.environ.get(flag)
        if value is not None and value.strip().lower() not in false_values:
            sys.stderr.write(
                f"eval_trace_replay refuses to run: {flag} must be explicitly disabled. "
                "No reports were written.\n"
            )
            raise SystemExit(2)
    os.environ.setdefault(
        "MYSQL_DSN",
        f"sqlite:///{Path(tempfile.gettempdir()) / 'trace_replay_eval.sqlite'}",
    )
    os.environ.setdefault("EMBEDDING_BACKEND", "hash")
    os.environ.setdefault("ENABLE_RAG_RERANKER", "false")
    os.environ.setdefault("ENABLE_RAG_HYBRID", "false")
    os.environ.setdefault("ENABLE_RAG_REWRITE", "false")


_lock_offline_environment()

from sqlalchemy import create_engine  # noqa: E402

from bank_reconciliation_agent.agents.audit_agent import AuditAgent, AuditDecision  # noqa: E402
from bank_reconciliation_agent.core.llm.provider import LLMResult  # noqa: E402
from bank_reconciliation_agent.db.session import get_engine  # noqa: E402
from bank_reconciliation_agent.schemas.ledger import LedgerQuery  # noqa: E402
from bank_reconciliation_agent.schemas.rag import RagSearchItem  # noqa: E402
from bank_reconciliation_agent.schemas.trace import (  # noqa: E402
    SpanType,
    TraceSpan,
)
from bank_reconciliation_agent.schemas.tools import (  # noqa: E402
    SearchRulesOutput,
    ToolAttemptRecord,
    ToolCallResult,
)
from bank_reconciliation_agent.services.trace import (  # noqa: E402
    TraceRecorder,
    TraceService,
    validate_trace_snapshot,
)
from bank_reconciliation_agent.services.workflow import (  # noqa: E402
    ReconciliationState,
    run_item,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = Path(os.environ.get("TRACE_REPLAY_REPORTS_DIR") or (PROJECT_ROOT / "reports"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evidence() -> RagSearchItem:
    return RagSearchItem(
        chunk_id="rule-001",
        source="rules.md",
        source_name="规则",
        source_url="https://example.com",
        source_file="rules.md",
        section_title="rule",
        element_type="paragraph",
        business_tags=["bank_enterprise"],
        score=0.9,
        content="规则证据",
    )


def _failed_tool(name: str, error_type: str, fallback_reason: str) -> ToolCallResult:
    return ToolCallResult(
        tool_name=name,
        status="FAILED",
        error_type=error_type,
        fallback_reason=fallback_reason,
        retryable=False,
        attempt=1,
        duration_ms=1.0,
        attempts=[
            ToolAttemptRecord(attempt=1, status="FAILED", duration_ms=1.0, error_type=error_type)
        ],
    )


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _SpyToolExecutor:
    def execute(self, name, args, context):
        del args, context
        return ToolCallResult(
            tool_name=name,
            status="SUCCEEDED",
            result=SearchRulesOutput(items=[_evidence()], rewritten_query=""),
            attempt=1,
            duration_ms=10.0,
            attempts=[ToolAttemptRecord(attempt=1, status="SUCCEEDED", duration_ms=10.0)],
        )


class _FailToolExecutor:
    def execute(self, name, args, context):
        del args, context
        return _failed_tool(name, "CIRCUIT_OPEN", "RAG_CIRCUIT_OPEN")


class _SpyAuditAgent:
    def __init__(self) -> None:
        self.last_llm_result = None
        self.last_llm_summary = None

    def decide_with_llm(self, flow_id: str, **kwargs) -> AuditDecision:
        del kwargs
        return AuditDecision(
            flow_id=flow_id,
            decision="PENDING_HUMAN",
            risk_level="MEDIUM",
            reason="Fake agent audit",
            ai_suggestion="PENDING_HUMAN",
            evidence=[_evidence()],
            confidence=0.88,
            fallback_applied=False,
            fallback_level=0,
            next_action="PENDING_HUMAN",
        )

    def decide(self, flow_id: str, **kwargs) -> AuditDecision:
        return self.decide_with_llm(flow_id, **kwargs)


class _AutoFixedAuditAgent:
    def __init__(self) -> None:
        self.last_llm_result = None
        self.last_llm_summary = None

    def decide_with_llm(self, flow_id: str, **kwargs) -> AuditDecision:
        del kwargs
        return AuditDecision(
            flow_id=flow_id,
            decision="AUTO_FIXED",
            risk_level="LOW",
            reason="自动平账",
            ai_suggestion="APPROVED_MATCH",
            evidence=[_evidence()],
            confidence=0.92,
            fallback_applied=False,
            fallback_level=0,
            next_action="AUTO_FIXED",
        )


class _GuardBlockAuditAgent:
    def __init__(self) -> None:
        self.last_llm_result = None
        self.last_llm_summary = None

    def decide_with_llm(self, flow_id: str, **kwargs) -> AuditDecision:
        del kwargs
        return AuditDecision(
            flow_id=flow_id,
            decision="PENDING_HUMAN",
            risk_level="MEDIUM",
            reason="TBD",
            ai_suggestion="PENDING_HUMAN",
            evidence=[_evidence()],
            confidence=0.90,
            fallback_applied=False,
            fallback_level=0,
            next_action="PENDING_HUMAN",
        )


class _StructuredRepairFailureProvider:
    """Fake provider that returns an invalid JSON on every attempt,
    triggering the real structured repair path to exhaust and fallback."""

    model = "fake-repair-fail"

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
        response_validator=None,
    ) -> LLMResult:
        del messages, temperature, response_format, response_validator
        return LLMResult(
            text='{"decision":"INVALID_LITERAL","risk_level":"LOW","reason":"bad",'
            '"ai_suggestion":"INVALID","evidence":[],"confidence":0.9}',
            prompt_tokens=50,
            completion_tokens=10,
            model="fake-repair-fail",
        )


def _noop_extraction_agent():
    class _NoopExtraction:
        last_llm_result = None
        last_llm_summary = None

        def extract(self, *, flow_id, summary, remark):
            del flow_id, summary, remark
            return {}

    return _NoopExtraction()


def _noop_trace_agent():
    class _NoopTrace:
        last_llm_result = None
        last_llm_summary = None

        def trace(self, **kwargs):
            del kwargs
            return {
                "trace_found": False,
                "related_flow_ids": [],
                "trace_summary": "未追溯",
                "confidence": 0.5,
            }

    return _NoopTrace()


# ---------------------------------------------------------------------------
# State builder and workflow driver
# ---------------------------------------------------------------------------


def _state(
    flow_id: str,
    exception_branch: str = "BE-R002",
    *,
    recorder: TraceRecorder | None = None,
) -> ReconciliationState:
    is_fuzzy = exception_branch == "BE-R007"
    state: ReconciliationState = {
        "task_id": "TASK-EVAL",
        "user_id": "eval_user",
        "thread_id": "TASK-EVAL",
        "scenario_type": "BANK_ENTERPRISE",
        "current_queue_id": None,
        "source_a_item": {"flow_id": flow_id, "summary": "摘要"},
        "source_b_item": {"flow_id": flow_id, "summary": "摘要"},
        "error_type": "FUZZY_MATCH_CANDIDATE" if is_fuzzy else "AMOUNT_MISMATCH",
        "exception_branch": exception_branch,
        "math_result": {
            "bank_amount": "100.00",
            "clear_amount": None if is_fuzzy else "99.00",
            "amount_diff": None if is_fuzzy else "1.00",
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
    if is_fuzzy:
        state["fuzzy_candidate"] = {
            "flow_id": f"{flow_id}-CANDIDATE",
            "amount": "100.00",
            "trade_date": "2026-06-22",
            "counterparty": "示例公司",
        }
    return state


def _run_flow(
    flow_id: str,
    recorder: TraceRecorder,
    *,
    exception_branch: str = "BE-R002",
    audit_agent=None,
    tool_executor=None,
) -> ReconciliationState:
    return run_item(
        _state(flow_id, exception_branch, recorder=recorder),
        extraction_agent=_noop_extraction_agent(),
        trace_agent=_noop_trace_agent(),
        audit_agent=audit_agent or _SpyAuditAgent(),
        tool_executor=tool_executor or _SpyToolExecutor(),
    )


def _finalize_from_state(recorder: TraceRecorder, state: ReconciliationState) -> list[TraceSpan]:
    """Close the recorder through the real service terminal-truth logic.

    The terminal type/outcome is derived from the actual audit decision, not a
    hand-set flag, so the evidence reflects real ``FINAL`` / ``FALLBACK`` truth.
    """
    from bank_reconciliation_agent.services.reconciliation import ReconciliationService

    decision = AuditDecision.model_validate(state["audit_decision"])
    return ReconciliationService()._finalize_recorder(recorder, decision)


def _terminal_type(spans: list[TraceSpan]) -> str | None:
    return next(
        (s.span_type.value for s in spans if s.span_type in (SpanType.FINAL, SpanType.FALLBACK)),
        None,
    )


def _persist_and_verify(
    ts: TraceService,
    user_id: str,
    task_id: str,
    flow_id: str,
    spans: list[TraceSpan],
) -> bool:
    """Persist spans to TraceService and confirm they can be read back successfully."""
    ok = ts.persist_snapshot(user_id=user_id, task_id=task_id, flow_id=flow_id, spans=spans)
    if not ok:
        return False
    stored = ts.get_spans(user_id=user_id, task_id=task_id, flow_id=flow_id)
    if not stored:
        return False
    validate_trace_snapshot(stored)
    return len(stored) == len(spans)


def _agent_span_facts(spans: list[TraceSpan]) -> dict[str, object]:
    """Extract auditable facts about the failed structured-repair Agent span."""
    failed_agents = [
        s for s in spans if s.span_type == SpanType.AGENT and s.status.value == "FAILED"
    ]
    non_cached_tokens = sum(
        (s.prompt_tokens or 0) + (s.completion_tokens or 0)
        for s in spans
        if s.span_type == SpanType.AGENT
    )
    failed = failed_agents[0] if failed_agents else None
    return {
        "failed_agent_spans": len(failed_agents),
        "structured_repair_attempted": bool(failed and failed.structured_repair_attempted),
        "structured_repair_succeeded": bool(failed and failed.structured_repair_succeeded),
        "error_type": failed.error_type if failed else None,
        "fallback_reason": failed.fallback_reason if failed else None,
        "non_cached_agent_tokens": non_cached_tokens,
    }


# ---------------------------------------------------------------------------
# Scenario runners
# ---------------------------------------------------------------------------


def _make_trace_service() -> TraceService:
    return TraceService(create_engine("sqlite:///:memory:", future=True))


def _base_scenario(
    name: str,
    spans: list[TraceSpan],
    *,
    trace_persisted: bool,
    scenario_passed: bool,
    expected_persistence: bool = True,
    facts: dict[str, object] | None = None,
    include_spans: bool = True,
) -> dict[str, object]:
    if spans:
        validate_trace_snapshot(spans)
    return {
        "scenario": name,
        "eligible_execution": True,
        "expected_persistence": expected_persistence,
        "trace_persisted": trace_persisted,
        "scenario_passed": scenario_passed,
        "span_sequence": [s.span_type.value for s in spans],
        "terminal_type": _terminal_type(spans),
        "span_count": len(spans),
        "facts": facts or {},
        "all_spans": [s.model_dump(mode="json") for s in spans] if include_spans else [],
    }


def scenario_success() -> dict[str, object]:
    ts = _make_trace_service()
    recorder = TraceRecorder(user_id="eval_user", task_id="TASK-EVAL", flow_id="F-SUCCESS")
    state = _run_flow(
        "F-SUCCESS",
        recorder,
        exception_branch="BE-R007",
        audit_agent=_AutoFixedAuditAgent(),
    )
    spans = _finalize_from_state(recorder, state)
    persisted = _persist_and_verify(ts, "eval_user", "TASK-EVAL", "F-SUCCESS", spans)
    passed = persisted and _terminal_type(spans) == "FINAL"
    return _base_scenario(
        "complete_success",
        spans,
        trace_persisted=persisted,
        scenario_passed=passed,
        facts={"decision": state["audit_decision"].get("decision")},
    )


def scenario_tool_failed() -> dict[str, object]:
    ts = _make_trace_service()
    recorder = TraceRecorder(user_id="eval_user", task_id="TASK-EVAL", flow_id="F-TOOL-FAIL")
    state = _run_flow("F-TOOL-FAIL", recorder, tool_executor=_FailToolExecutor())
    spans = _finalize_from_state(recorder, state)
    persisted = _persist_and_verify(ts, "eval_user", "TASK-EVAL", "F-TOOL-FAIL", spans)
    seq = [s.span_type.value for s in spans]
    passed = (
        persisted
        and _terminal_type(spans) == "FALLBACK"
        and "TOOL" in seq
        and "AGENT" not in seq
        and "GUARD" not in seq
    )
    return _base_scenario(
        "tool_failed_fallback",
        spans,
        trace_persisted=persisted,
        scenario_passed=passed,
        facts={"decision": state["audit_decision"].get("decision")},
    )


def scenario_agent_repair_failure() -> dict[str, object]:
    """Real AuditAgent with a Fake provider that always returns invalid decision
    literals, exhausting the structured repair path and falling back."""
    ts = _make_trace_service()
    recorder = TraceRecorder(user_id="eval_user", task_id="TASK-EVAL", flow_id="F-AGENT-FAIL")
    agent = AuditAgent(provider=_StructuredRepairFailureProvider())
    state = _run_flow(
        "F-AGENT-FAIL",
        recorder,
        exception_branch="BE-R007",
        audit_agent=agent,
    )
    spans = _finalize_from_state(recorder, state)
    persisted = _persist_and_verify(ts, "eval_user", "TASK-EVAL", "F-AGENT-FAIL", spans)
    facts = _agent_span_facts(spans)
    facts["decision"] = state["audit_decision"].get("decision")
    passed = (
        persisted
        and _terminal_type(spans) == "FALLBACK"
        and facts["failed_agent_spans"] >= 1
        and facts["structured_repair_attempted"] is True
        and facts["non_cached_agent_tokens"] > 0
    )
    return _base_scenario(
        "agent_repair_failure_fallback",
        spans,
        trace_persisted=persisted,
        scenario_passed=passed,
        facts=facts,
    )


def scenario_guard_blocked() -> dict[str, object]:
    ts = _make_trace_service()
    recorder = TraceRecorder(user_id="eval_user", task_id="TASK-EVAL", flow_id="F-GUARD")
    state = _run_flow(
        "F-GUARD",
        recorder,
        exception_branch="BE-R007",
        audit_agent=_GuardBlockAuditAgent(),
    )
    spans = _finalize_from_state(recorder, state)
    persisted = _persist_and_verify(ts, "eval_user", "TASK-EVAL", "F-GUARD", spans)
    guard = next((s for s in spans if s.span_type == SpanType.GUARD), None)
    passed = (
        persisted
        and _terminal_type(spans) == "FALLBACK"
        and guard is not None
        and guard.outcome == "BLOCKED"
    )
    return _base_scenario(
        "guard_blocked_fallback",
        spans,
        trace_persisted=persisted,
        scenario_passed=passed,
        facts={"guard_outcome": guard.outcome if guard else None},
    )


def scenario_cross_tenant_replay_rejection() -> dict[str, object]:
    """Cross-user rejection proven via the real FastAPI HTTP Replay endpoint.

    An owner persists a Trace and can read it (200 AVAILABLE); a non-owner gets
    a 404 with a stable error code and no Trace payload. A storage-level empty
    read is recorded only as supplementary evidence.
    """
    from fastapi.testclient import TestClient

    from bank_reconciliation_agent.core.security import create_access_token
    from bank_reconciliation_agent.main import app
    from bank_reconciliation_agent.services.queue import queue_service
    from bank_reconciliation_agent.services.task import task_service
    from bank_reconciliation_agent.services.trace import trace_service as global_trace_service

    owner, intruder = "eval_owner", "eval_intruder"
    task_id, flow_id = "TASK-XTEN", "F-XTEN"

    task_service.replace_task(
        user_id=owner,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
        status="COMPLETED",
    )
    queue_service.replace_task_rows(
        user_id=owner,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        rows=[
            {
                "task_id": task_id,
                "flow_id": flow_id,
                "bank_transaction_id": None,
                "clear_transaction_id": None,
                "error_type": "AMOUNT_MISMATCH",
                "exception_branch": "BE-R002",
                "status": "PENDING_HUMAN",
                "risk_level": "MEDIUM",
                "retry_count": 0,
            }
        ],
    )

    recorder = TraceRecorder(user_id=owner, task_id=task_id, flow_id=flow_id)
    state = _run_flow(flow_id, recorder, audit_agent=_SpyAuditAgent())
    spans = _finalize_from_state(recorder, state)
    persisted = global_trace_service.persist_snapshot(
        user_id=owner, task_id=task_id, flow_id=flow_id, spans=spans
    )

    client = TestClient(app)
    url = f"/api/v1/traces/{task_id}/flows/{flow_id}"
    owner_resp = client.get(url, headers={"Authorization": f"Bearer {create_access_token(owner)}"})
    intruder_resp = client.get(
        url, headers={"Authorization": f"Bearer {create_access_token(intruder)}"}
    )

    owner_data = owner_resp.json().get("data", {}) if owner_resp.status_code == 200 else {}
    owner_available = (
        owner_resp.status_code == 200 and owner_data.get("replay_status") == "AVAILABLE"
    )
    non_owner_status = intruder_resp.status_code
    non_owner_error = intruder_resp.json().get("detail")
    non_owner_leaked = (recorder.trace_id in intruder_resp.text) or (
        '"span_id"' in intruder_resp.text
    )
    storage_empty = not global_trace_service.get_spans(
        user_id=intruder, task_id=task_id, flow_id=flow_id
    )

    passed = (
        bool(persisted)
        and owner_available
        and non_owner_status == 404
        and non_owner_error == "TASK_NOT_FOUND"
        and not non_owner_leaked
        and storage_empty
    )
    return _base_scenario(
        "cross_tenant_replay_rejection",
        spans,
        trace_persisted=bool(persisted),
        scenario_passed=passed,
        facts={
            "owner_http_status": owner_resp.status_code,
            "owner_replay_status": owner_data.get("replay_status"),
            "non_owner_http_status": non_owner_status,
            "non_owner_error_code": non_owner_error,
            "non_owner_payload_leaked": bool(non_owner_leaked),
            "storage_empty_read": bool(storage_empty),
        },
    )


def scenario_trace_write_failure_isolation() -> dict[str, object]:
    """Trace write failure injected at the real ReconciliationService side-effect
    boundary, after the core ledger/queue/task transaction commits.

    Proves the business result is committed and the API call succeeds while the
    Trace batch is dropped (0 rows) and the failure counter increments by one.
    """
    import bank_reconciliation_agent.services.reconciliation as recon_module
    from bank_reconciliation_agent.services.ledger import ledger_service
    from bank_reconciliation_agent.services.queue import queue_service
    from bank_reconciliation_agent.services.reconciliation import (
        ReconciliationMatchResult,
        ReconciliationService,
    )
    from bank_reconciliation_agent.services.task import task_service
    from bank_reconciliation_agent.services.trace import trace_service as global_trace_service
    from decimal import Decimal

    user_id, task_id, flow_id = "eval_wf", "TASK-WF-ISO", "F-WF-ISO"
    service = ReconciliationService()

    task_service.replace_task(
        user_id=user_id,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=1,
        pending_human_rows=0,
        status="RUNNING",
    )

    class _BrokenEngine:
        def begin(self):
            raise RuntimeError("simulated trace db failure")

    broken_ts = TraceService(get_engine())
    broken_ts._engine = _BrokenEngine()
    broken_ts._initialized = True

    def _det_run_item(state, *, emitter=None):
        return run_item(
            state,
            extraction_agent=_noop_extraction_agent(),
            trace_agent=_noop_trace_agent(),
            audit_agent=_SpyAuditAgent(),
            tool_executor=_SpyToolExecutor(),
            emitter=emitter,
        )

    orig_trace = recon_module.trace_service
    orig_run = recon_module.run_item
    orig_bank = recon_module.transaction_service.get_bank_row
    orig_clear = recon_module.transaction_service.get_clear_row
    before_fail = TraceService.metrics_snapshot()["trace_write_failure_count"]
    business_raised = False
    try:
        recon_module.trace_service = broken_ts
        recon_module.run_item = _det_run_item
        recon_module.transaction_service.get_bank_row = lambda **k: {
            "flow_id": k["flow_id"],
            "summary": "银行流水",
        }
        recon_module.transaction_service.get_clear_row = lambda **k: {
            "flow_id": k["flow_id"],
            "summary": "清算流水",
        }
        result = ReconciliationMatchResult(
            flow_id=flow_id,
            status="PENDING_HUMAN",
            error_type="AMOUNT_MISMATCH",
            exception_branch="BE-R002",
            bank_amount=Decimal("100.00"),
            clear_amount=Decimal("99.00"),
            amount_diff=Decimal("1.00"),
        )
        queue_rows = service._write_queue_entries(user_id, task_id, "BANK_ENTERPRISE", [result])
        try:
            service._write_ledger_entries(
                user_id, task_id, "BANK_ENTERPRISE", [result], queue_rows=queue_rows
            )
        except Exception:
            business_raised = True
    finally:
        recon_module.trace_service = orig_trace
        recon_module.run_item = orig_run
        recon_module.transaction_service.get_bank_row = orig_bank
        recon_module.transaction_service.get_clear_row = orig_clear

    after_fail = TraceService.metrics_snapshot()["trace_write_failure_count"]

    ledger_page = ledger_service.list(
        user_id=user_id, query=LedgerQuery(task_id=task_id, page=1, page_size=100)
    )
    ledger_row = next((r for r in ledger_page.items if r.flow_id == flow_id), None)
    queue_committed = (
        queue_service.get_row(user_id=user_id, task_id=task_id, flow_id=flow_id) is not None
    )
    task_row = task_service.get(user_id=user_id, task_id=task_id)
    task_stats_committed = bool(task_row and task_row.ai_processed_rows == 1)
    trace_rows = len(
        global_trace_service.get_spans(user_id=user_id, task_id=task_id, flow_id=flow_id)
    )
    failure_incremented = after_fail == before_fail + 1

    facts = {
        "business_call_succeeded": not business_raised,
        "ledger_committed": ledger_row is not None,
        "queue_committed": queue_committed,
        "task_stats_committed": task_stats_committed,
        "final_decision": ledger_row.handle_status if ledger_row else None,
        "trace_rows": trace_rows,
        "failure_counter_incremented": failure_incremented,
    }
    passed = (
        not business_raised
        and ledger_row is not None
        and queue_committed
        and task_stats_committed
        and ledger_row.handle_status == "PENDING_HUMAN"
        and trace_rows == 0
        and failure_incremented
    )
    return _base_scenario(
        "trace_write_failure_isolation",
        [],
        trace_persisted=False,
        scenario_passed=passed,
        expected_persistence=False,
        facts=facts,
        include_spans=False,
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _p50(values: list[int]) -> int:
    if not values:
        return 0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) // 2


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    return sorted(values)[int(len(values) * 0.95)]


def _compute_metrics(scenarios: list[dict[str, object]]) -> dict[str, object]:
    all_spans: list[dict[str, object]] = []
    eligible_count = 0
    persisted = 0
    for s in scenarios:
        all_spans.extend(s.get("all_spans", []))
        if s.get("eligible_execution"):
            eligible_count += 1
            if s.get("trace_persisted", False):
                persisted += 1

    rate = persisted / eligible_count if eligible_count > 0 else 0.0

    durations: dict[str, list[int]] = {}
    for span in all_spans:
        st = span["span_type"]
        durations.setdefault(st, []).append(span["duration_ms"])

    dur_stats = {}
    for st, vals in durations.items():
        dur_stats[st] = {"p50": _p50(vals), "p95": _p95(vals)}

    error_dist: dict[str, int] = Counter()
    fallback_dist: dict[str, int] = Counter()
    token_by_agent: dict[str, dict[str, int]] = {}
    for span in all_spans:
        if span.get("error_type"):
            key = f"{span['span_type']}.{span['error_type']}"
            error_dist[key] += 1
        if span.get("fallback_reason"):
            fb = str(span["fallback_reason"])
            fallback_dist[fb] += 1
        if span["span_type"] == "AGENT":
            name = str(span.get("name", "unknown"))
            if name not in token_by_agent:
                token_by_agent[name] = {"prompt": 0, "completion": 0}
            token_by_agent[name]["prompt"] += int(span.get("prompt_tokens", 0) or 0)
            token_by_agent[name]["completion"] += int(span.get("completion_tokens", 0) or 0)

    metrics = TraceService.metrics_snapshot()

    return {
        "trace_completeness_rate": rate,
        "numerator": persisted,
        "denominator": eligible_count,
        "duration_p50_p95_by_type": dur_stats,
        "error_distribution": dict(sorted(error_dist.items())),
        "fallback_distribution": dict(sorted(fallback_dist.items())),
        "token_by_agent": token_by_agent,
        "trace_write_success_count": metrics.get("trace_write_success_count", 0),
        "trace_write_failure_count": metrics.get("trace_write_failure_count", 0),
        "source": "runtime_memory",
    }


# ---------------------------------------------------------------------------
# Report builders
# ---------------------------------------------------------------------------


def _build_json(
    scenarios: list[dict[str, object]], metrics: dict[str, object]
) -> dict[str, object]:
    scenario_summaries = []
    pass_count = 0
    for s in scenarios:
        if s.get("scenario_passed"):
            pass_count += 1
        scenario_summaries.append(
            {
                "scenario": s["scenario"],
                "eligible_execution": s.get("eligible_execution", False),
                "expected_persistence": s.get("expected_persistence", False),
                "trace_persisted": s.get("trace_persisted", False),
                "scenario_passed": s.get("scenario_passed", False),
                "span_sequence": s.get("span_sequence", []),
                "terminal_type": s.get("terminal_type"),
                "span_count": s.get("span_count", 0),
                "facts": s.get("facts", {}),
            }
        )
    return {
        "environment": "offline",
        "provider": "fake",
        "embedding": "hash",
        "database": "sqlite_local",
        "claim": {
            "offline": True,
            "fake_provider": True,
            "hash_embedding": True,
            "local_sqlite": True,
            "local_latency_only": True,
            "not_production_sla": True,
        },
        "scenario_pass_count": pass_count,
        "scenario_total": len(scenario_summaries),
        "scenarios": scenario_summaries,
        "metrics": metrics,
    }


def _build_markdown(json_report: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append("# Trace Replay Evidence Report")
    lines.append("")
    lines.append(
        f"**Environment**: offline | **Provider**: {json_report['provider']} | "
        f"**Embedding**: {json_report['embedding']} | **Database**: {json_report['database']}"
    )
    lines.append("")
    lines.append(
        "> This report is generated from a single deterministic run using a fake "
        "LLM provider, hash embedding and local SQLite. Latency figures are "
        "local-only and must not be interpreted as production SLAs."
    )
    lines.append("")

    metrics = json_report["metrics"]
    lines.append("## Completeness")
    lines.append(f"- **Rate**: {metrics['trace_completeness_rate']:.2%}")
    lines.append(f"- **Numerator (eligible flows persisted)**: {metrics['numerator']}")
    lines.append(f"- **Denominator (eligible flows executed)**: {metrics['denominator']}")
    lines.append(
        f"- **Scenario pass count**: {json_report['scenario_pass_count']}"
        f"/{json_report['scenario_total']}"
    )
    lines.append("")

    lines.append("## Scenarios")
    for scenario in json_report["scenarios"]:
        lines.append(f"### {scenario['scenario']}")
        lines.append(f"- Passed: {scenario['scenario_passed']}")
        lines.append(f"- Eligible execution: {scenario['eligible_execution']}")
        lines.append(
            f"- Persistence expected/actual: "
            f"{scenario['expected_persistence']}/{scenario['trace_persisted']}"
        )
        lines.append(f"- Terminal: {scenario['terminal_type']}")
        lines.append(f"- Span count: {scenario['span_count']}")
        if scenario["span_sequence"]:
            seq_str = " → ".join(scenario["span_sequence"])
            lines.append(f"- Sequence: `{seq_str}`")
        for key, value in scenario["facts"].items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    lines.append("## Duration (P50 / P95)")
    for st, vals in metrics["duration_p50_p95_by_type"].items():
        lines.append(f"- **{st}**: P50={vals['p50']}ms  P95={vals['p95']}ms")

    lines.append("")
    lines.append("## Error Distribution")
    if metrics["error_distribution"]:
        for k, v in metrics["error_distribution"].items():
            lines.append(f"- `{k}`: {v}")
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append("## Fallback Distribution")
    if metrics["fallback_distribution"]:
        for k, v in metrics["fallback_distribution"].items():
            lines.append(f"- `{k}`: {v}")
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append("## Token by Agent")
    if metrics["token_by_agent"]:
        for name, tokens in metrics["token_by_agent"].items():
            total = tokens["prompt"] + tokens["completion"]
            lines.append(
                f"- **{name}**: prompt={tokens['prompt']}, completion={tokens['completion']}, "
                f"total={total}"
            )
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append("## Write Counters")
    lines.append(f"- Success: {metrics['trace_write_success_count']}")
    lines.append(f"- Failure: {metrics['trace_write_failure_count']}")
    lines.append(f"- Source: `{metrics.get('source', 'runtime_memory')}`")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_report(json_report: dict[str, object]) -> list[str]:
    """Return a list of validation errors; empty means the report is trustworthy."""
    errors: list[str] = []
    scenarios = json_report["scenarios"]
    metrics = json_report["metrics"]

    expected_names = [
        "complete_success",
        "tool_failed_fallback",
        "agent_repair_failure_fallback",
        "guard_blocked_fallback",
        "cross_tenant_replay_rejection",
        "trace_write_failure_isolation",
    ]
    if [s["scenario"] for s in scenarios] != expected_names:
        errors.append("scenario set/order mismatch")

    for s in scenarios:
        if not s["scenario_passed"]:
            errors.append(f"scenario failed expectation: {s['scenario']}")

    passed = sum(1 for s in scenarios if s["scenario_passed"])
    if json_report["scenario_pass_count"] != passed:
        errors.append("scenario_pass_count inconsistent with scenarios")
    if json_report["scenario_pass_count"] != 6:
        errors.append(f"expected 6/6 scenario passes, got {json_report['scenario_pass_count']}")

    if metrics["denominator"] != 6:
        errors.append(f"expected completeness denominator 6, got {metrics['denominator']}")
    if metrics["numerator"] != 5:
        errors.append(f"expected completeness numerator 5, got {metrics['numerator']}")
    if abs(metrics["trace_completeness_rate"] - 5 / 6) > 1e-9:
        errors.append("completeness rate is not 5/6")

    return errors


def _validate_markdown(markdown_text: str, json_report: dict[str, object]) -> list[str]:
    """Return errors if the rendered Markdown drifts from the same JSON report.

    Guards against ``_build_markdown`` silently diverging from the machine facts:
    scenario set/order, 6/6 pass count, 5/6 completeness and the claim boundary
    must all appear verbatim in the Markdown that will be written alongside JSON.
    """
    errors: list[str] = []
    if not markdown_text.strip():
        errors.append("markdown is empty")
        return errors

    names = [s["scenario"] for s in json_report["scenarios"]]
    last_index = -1
    for name in names:
        heading = f"### {name}"
        idx = markdown_text.find(heading)
        if idx == -1:
            errors.append(f"markdown missing scenario heading: {name}")
        elif idx < last_index:
            errors.append(f"markdown scenario out of order: {name}")
        else:
            last_index = idx

    metrics = json_report["metrics"]
    required_fragments = [
        f"Scenario pass count**: {json_report['scenario_pass_count']}/{json_report['scenario_total']}",
        f"Numerator (eligible flows persisted)**: {metrics['numerator']}",
        f"Denominator (eligible flows executed)**: {metrics['denominator']}",
        f"**Provider**: {json_report['provider']}",
        f"**Embedding**: {json_report['embedding']}",
        f"**Database**: {json_report['database']}",
    ]
    for fragment in required_fragments:
        if fragment not in markdown_text:
            errors.append(f"markdown missing fragment: {fragment!r}")

    return errors


def _write_reports_atomically(json_text: str, markdown_text: str) -> tuple[Path, Path]:
    """Write both reports to temp files, then atomically replace the targets.

    Neither final report is touched until both temp files are written, so a
    failure mid-write can never leave a half-updated pair on disk.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / "trace_replay_evidence.json"
    md_path = REPORTS_DIR / "trace_replay_evidence.md"
    json_tmp = REPORTS_DIR / "trace_replay_evidence.json.tmp"
    md_tmp = REPORTS_DIR / "trace_replay_evidence.md.tmp"
    json_tmp.write_text(json_text, encoding="utf-8")
    md_tmp.write_text(markdown_text, encoding="utf-8")
    os.replace(json_tmp, json_path)
    os.replace(md_tmp, md_path)
    return json_path, md_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print("=== Trace Replay Evidence Runner ===")
    print("Provider: fake | Embedding: hash | Database: sqlite (file-backed/local)")
    print()

    runners = [
        ("complete_success", scenario_success),
        ("tool_failed_fallback", scenario_tool_failed),
        ("agent_repair_failure_fallback", scenario_agent_repair_failure),
        ("guard_blocked_fallback", scenario_guard_blocked),
        ("cross_tenant_replay_rejection", scenario_cross_tenant_replay_rejection),
        ("trace_write_failure_isolation", scenario_trace_write_failure_isolation),
    ]

    scenarios_run: list[dict[str, object]] = []
    for idx, (name, runner) in enumerate(runners, start=1):
        print(f"[{idx}/{len(runners)}] {name} ... ", end="")
        result = runner()
        status = "OK" if result["scenario_passed"] else "FAIL"
        print(status)
        scenarios_run.append(result)

    metrics = _compute_metrics(scenarios_run)
    json_report = _build_json(scenarios_run, metrics)

    # 1. Report schema / cross-field validation before rendering anything.
    errors = _validate_report(json_report)
    if errors:
        print("\nValidation failed; existing reports left untouched:")
        for err in errors:
            print(f"  - {err}")
        return 1

    # 2. Render both artefacts fully in memory from the same JSON report.
    try:
        json_text = json.dumps(json_report, ensure_ascii=False, indent=2)
        markdown_text = _build_markdown(json_report)
    except Exception as exc:
        print(f"\nReport rendering failed ({type(exc).__name__}); reports left untouched.")
        return 1

    # 3. Verify the Markdown was generated from the same JSON facts.
    md_errors = _validate_markdown(markdown_text, json_report)
    if md_errors:
        print("\nMarkdown/JSON consistency check failed; reports left untouched:")
        for err in md_errors:
            print(f"  - {err}")
        return 1

    # 4. Only now touch disk, writing both artefacts atomically.
    json_path, md_path = _write_reports_atomically(json_text, markdown_text)
    print(f"\nJSON report  → {json_path}")
    print(f"Markdown report → {md_path}")

    print(
        f"\nCompleteness: {metrics['trace_completeness_rate']:.2%} "
        f"({metrics['numerator']}/{metrics['denominator']}) | "
        f"scenario pass {json_report['scenario_pass_count']}/{json_report['scenario_total']}"
    )
    print("All scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

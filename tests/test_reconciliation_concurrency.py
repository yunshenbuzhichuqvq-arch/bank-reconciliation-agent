import json
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, BoundedSemaphore, Event, Lock, get_ident

import pytest
from pydantic import ValidationError

from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgentError
from bank_reconciliation_agent.core.config import Settings, settings
from bank_reconciliation_agent.core.llm import reliability as reliability_module
from bank_reconciliation_agent.core.llm.provider import LLMResult
from bank_reconciliation_agent.schemas.ledger import LedgerRow
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from bank_reconciliation_agent.schemas.tools import (
    SearchRulesArgs,
    SearchRulesOutput,
    ToolAttemptRecord,
    ToolCallResult,
    ToolContext,
)
from bank_reconciliation_agent.schemas.trace import SpanType
from bank_reconciliation_agent.services.circuit_breaker import CircuitBreaker
from bank_reconciliation_agent.services import reconciliation as reconciliation_module
from bank_reconciliation_agent.services.reconciliation import (
    ReconciliationFlowBundle,
    ReconciliationMatchResult,
    ReconciliationService,
    ReconciliationWriteBundle,
    get_reconciliation_executor,
)
from bank_reconciliation_agent.services.stream_emitter import QueueEmitter
from bank_reconciliation_agent.services.tool_adapters import make_search_rules_adapter
from bank_reconciliation_agent.services.tool_executor import get_shared_executor
from bank_reconciliation_agent.services.trace import validate_trace_snapshot
from bank_reconciliation_agent.services import workflow as workflow_module


def test_reconciliation_concurrency_config_defaults_and_bounds() -> None:
    assert Settings(_env_file=None).reconciliation_max_concurrency == 6
    assert (
        Settings(_env_file=None, reconciliation_max_concurrency=1).reconciliation_max_concurrency
        == 1
    )
    assert (
        Settings(_env_file=None, reconciliation_max_concurrency=8).reconciliation_max_concurrency
        == 8
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None, reconciliation_max_concurrency=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, reconciliation_max_concurrency=9)


def test_parallel_flows_respect_process_cap_and_preserve_input_order(monkeypatch) -> None:
    service = ReconciliationService()
    active = 0
    peak = 0
    completion_order: list[str] = []
    lock = Lock()

    def build_flow(result: ReconciliationMatchResult, **kwargs) -> ReconciliationFlowBundle:
        nonlocal active, peak
        index = _flow_index(result)
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep((8 - index) * 0.005)
            completion_order.append(result.flow_id)
            return _flow_bundle(result, stream_seq=kwargs["stream_seq_start"])
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(service, "_build_flow_bundle", build_flow)
    results = [_match_result(index) for index in range(8)]

    bundle = service._build_write_bundle(
        user_id="u",
        task_id="TASK-CONCURRENT",
        scenario_type="BANK_ENTERPRISE",
        results=results,
    )

    expected_order = [result.flow_id for result in results]
    assert 1 < peak <= settings.reconciliation_max_concurrency
    assert completion_order != expected_order
    assert [row.flow_id for row in bundle.ledger_rows] == expected_order
    assert [str(row["flow_id"]) for row in bundle.rag_log_rows] == expected_order
    assert [str(row["flow_id"]) for row in bundle.agent_log_rows] == expected_order
    assert [snapshot[0] for snapshot in bundle.trace_snapshots] == expected_order
    assert bundle.ai_processed_rows == len(results)
    assert bundle.total_prompt_tokens == sum(range(1, 9))
    assert bundle.total_completion_tokens == sum(range(101, 109))


def test_two_batches_share_one_process_wide_flow_cap(monkeypatch) -> None:
    services = [ReconciliationService(), ReconciliationService()]
    active = 0
    peak = 0
    lock = Lock()

    def build_flow(result: ReconciliationMatchResult, **kwargs) -> ReconciliationFlowBundle:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.02)
            return _flow_bundle(result, stream_seq=kwargs["stream_seq_start"])
        finally:
            with lock:
                active -= 1

    for service in services:
        monkeypatch.setattr(service, "_build_flow_bundle", build_flow)

    def run_batch(service: ReconciliationService, task_suffix: str) -> None:
        service._build_write_bundle(
            user_id="u",
            task_id=f"TASK-{task_suffix}",
            scenario_type="BANK_ENTERPRISE",
            results=[_match_result(index) for index in range(8)],
        )

    with ThreadPoolExecutor(max_workers=2) as callers:
        futures = [
            callers.submit(run_batch, services[0], "A"),
            callers.submit(run_batch, services[1], "B"),
        ]
        for future in futures:
            future.result(timeout=3)

    assert 1 < peak <= settings.reconciliation_max_concurrency


def test_single_flow_batches_share_process_wide_admission_cap(monkeypatch) -> None:
    service = ReconciliationService()
    cap = settings.reconciliation_max_concurrency
    release = Event()
    reached_cap = Event()
    active = 0
    peak = 0
    lock = Lock()

    def build_flow(result: ReconciliationMatchResult, **kwargs) -> ReconciliationFlowBundle:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active >= cap:
                reached_cap.set()
        try:
            assert release.wait(timeout=2)
            return _flow_bundle(result, stream_seq=kwargs["stream_seq_start"])
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(service, "_build_flow_bundle", build_flow)

    def run_batch(index: int) -> ReconciliationWriteBundle:
        return service._build_write_bundle(
            user_id="u",
            task_id=f"TASK-SINGLE-{index}",
            scenario_type="BANK_ENTERPRISE",
            results=[_match_result(index)],
        )

    batch_count = cap * 2
    with ThreadPoolExecutor(max_workers=batch_count) as callers:
        futures = [callers.submit(run_batch, index) for index in range(batch_count)]
        assert reached_cap.wait(timeout=1)
        time.sleep(0.02)
        with lock:
            assert active == cap
            assert peak == cap
        release.set()
        assert all(len(future.result(timeout=2).ledger_rows) == 1 for future in futures)


def test_emitter_batches_share_cap_and_keep_each_batch_serial(monkeypatch) -> None:
    service = ReconciliationService()
    cap = settings.reconciliation_max_concurrency
    release = Event()
    reached_cap = Event()
    active = 0
    peak = 0
    emitter_active: dict[int, int] = {}
    emitter_peak: dict[int, int] = {}
    emitter_starts: dict[int, list[int]] = {}
    lock = Lock()

    def build_flow(result: ReconciliationMatchResult, **kwargs) -> ReconciliationFlowBundle:
        nonlocal active, peak
        emitter = kwargs["emitter"]
        emitter_id = id(emitter)
        with lock:
            active += 1
            peak = max(peak, active)
            emitter_active[emitter_id] = emitter_active.get(emitter_id, 0) + 1
            emitter_peak[emitter_id] = max(
                emitter_peak.get(emitter_id, 0), emitter_active[emitter_id]
            )
            emitter_starts.setdefault(emitter_id, []).append(kwargs["stream_seq_start"])
            if active >= cap:
                reached_cap.set()
        try:
            if kwargs["stream_seq_start"] == 0:
                assert release.wait(timeout=2)
            return _flow_bundle(result, stream_seq=kwargs["stream_seq_start"] + 1)
        finally:
            with lock:
                emitter_active[emitter_id] -= 1
                active -= 1

    monkeypatch.setattr(service, "_build_flow_bundle", build_flow)

    emitters = [QueueEmitter() for _ in range(cap * 2)]

    def run_batch(index: int) -> ReconciliationWriteBundle:
        return service._build_write_bundle(
            user_id="u",
            task_id=f"TASK-EMITTER-{index}",
            scenario_type="BANK_ENTERPRISE",
            results=[_match_result(index * 2), _match_result(index * 2 + 1)],
            emitter=emitters[index],
        )

    with ThreadPoolExecutor(max_workers=len(emitters)) as callers:
        futures = [callers.submit(run_batch, index) for index in range(len(emitters))]
        assert reached_cap.wait(timeout=1)
        time.sleep(0.02)
        with lock:
            assert active == cap
            assert peak == cap
        release.set()
        for future in futures:
            assert len(future.result(timeout=2).ledger_rows) == 2

    assert set(emitter_peak.values()) == {1}
    assert all(starts == [0, 1] for starts in emitter_starts.values())


def test_config_one_caps_parallel_direct_batches_process_wide(monkeypatch) -> None:
    service = ReconciliationService()
    release = Event()
    entered = Event()
    active = 0
    peak = 0
    lock = Lock()

    monkeypatch.setattr(settings, "reconciliation_max_concurrency", 1)
    monkeypatch.setattr(
        reconciliation_module,
        "_reconciliation_admission_gate",
        BoundedSemaphore(1),
    )

    def build_flow(result: ReconciliationMatchResult, **kwargs) -> ReconciliationFlowBundle:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            entered.set()
        try:
            assert release.wait(timeout=2)
            return _flow_bundle(result, stream_seq=kwargs["stream_seq_start"])
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(service, "_build_flow_bundle", build_flow)

    def run_batch(index: int) -> ReconciliationWriteBundle:
        return service._build_write_bundle(
            user_id="u",
            task_id=f"TASK-CAP-ONE-{index}",
            scenario_type="BANK_ENTERPRISE",
            results=[_match_result(index)],
        )

    with ThreadPoolExecutor(max_workers=4) as callers:
        futures = [callers.submit(run_batch, index) for index in range(4)]
        assert entered.wait(timeout=1)
        time.sleep(0.02)
        with lock:
            assert active == 1
            assert peak == 1
        release.set()
        assert all(len(future.result(timeout=2).ledger_rows) == 1 for future in futures)


def test_emitter_path_stays_serial_with_monotonic_flow_seq(monkeypatch) -> None:
    service = ReconciliationService()
    emitter = QueueEmitter()
    active = 0
    peak = 0
    starts: list[int] = []

    def build_flow(result: ReconciliationMatchResult, **kwargs) -> ReconciliationFlowBundle:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        starts.append(kwargs["stream_seq_start"])
        try:
            assert kwargs["emitter"] is emitter
            return _flow_bundle(result, stream_seq=kwargs["stream_seq_start"] + 1)
        finally:
            active -= 1

    monkeypatch.setattr(service, "_build_flow_bundle", build_flow)
    results = [_match_result(index) for index in range(5)]

    bundle = service._build_write_bundle(
        user_id="u",
        task_id="TASK-SSE-SERIAL",
        scenario_type="BANK_ENTERPRISE",
        results=results,
        emitter=emitter,
    )

    assert peak == 1
    assert starts == [0, 1, 2, 3, 4]
    assert [row.flow_id for row in bundle.ledger_rows] == [result.flow_id for result in results]


def test_unexpected_flow_error_waits_for_active_work_and_skips_persistence(monkeypatch) -> None:
    service = ReconciliationService()
    gate = Barrier(settings.reconciliation_max_concurrency)
    active = 0
    peak = 0
    begin_calls = 0
    lock = Lock()

    class NoWriteEngine:
        def begin(self):
            nonlocal begin_calls
            begin_calls += 1
            raise AssertionError("persistence must not start after a flow failure")

    def build_flow(result: ReconciliationMatchResult, **kwargs) -> ReconciliationFlowBundle:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            gate.wait(timeout=1)
            if result.flow_id == "FLOW-0":
                raise RuntimeError("unexpected infrastructure failure")
            time.sleep(0.05)
            return _flow_bundle(result, stream_seq=kwargs["stream_seq_start"])
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(service, "_build_flow_bundle", build_flow)
    monkeypatch.setattr(service, "_ensure_core_transaction_tables", lambda: None)
    monkeypatch.setattr(service, "_engine", NoWriteEngine())
    results = [_match_result(index) for index in range(8)]
    queue_rows = service._write_queue_entries("u", "TASK-FAIL", "BANK_ENTERPRISE", results)

    with pytest.raises(RuntimeError, match="unexpected infrastructure failure"):
        service._write_ledger_entries(
            "u",
            "TASK-FAIL",
            "BANK_ENTERPRISE",
            results,
            queue_rows=queue_rows,
        )

    assert peak == settings.reconciliation_max_concurrency
    assert active == 0
    assert begin_calls == 0


def test_known_agent_error_fails_closed_only_its_flow_in_parallel_batch(monkeypatch) -> None:
    service = ReconciliationService()
    gate = Barrier(2)

    def run_workflow(*, user_id, task_id, scenario_type, result, rag_query, recorder=None):
        del rag_query, recorder
        gate.wait(timeout=1)
        if result.flow_id == "FLOW-0":
            raise ExtractionAgentError("invalid extraction output")
        state = service._agent_error_workflow_state(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            result=result,
            error=RuntimeError("placeholder"),
        )
        state["audit_decision"]["reason"] = "healthy flow completed"
        state["fallback_path"] = "L1"
        return state

    monkeypatch.setattr(service, "_run_workflow_for_result", run_workflow)
    bundle = service._build_write_bundle(
        user_id="u",
        task_id="TASK-AGENT-FAIL-CLOSED",
        scenario_type="BANK_ENTERPRISE",
        results=[_match_result(0), _match_result(1)],
    )
    rows = {row.flow_id: row for row in bundle.ledger_rows}

    assert set(rows) == {"FLOW-0", "FLOW-1"}
    assert "ExtractionAgentError" in (rows["FLOW-0"].ai_audit_opinion or "")
    assert rows["FLOW-0"].handle_status == "PENDING_HUMAN"
    assert rows["FLOW-1"].ai_audit_opinion == "healthy flow completed"


def test_flow_and_tool_executors_are_separate_and_nested_work_completes(monkeypatch) -> None:
    service = ReconciliationService()
    assert get_reconciliation_executor() is not get_shared_executor()

    def build_flow(result: ReconciliationMatchResult, **kwargs) -> ReconciliationFlowBundle:
        nested = get_shared_executor().submit(lambda: result.flow_id)
        assert nested.result(timeout=1) == result.flow_id
        return _flow_bundle(result, stream_seq=kwargs["stream_seq_start"])

    monkeypatch.setattr(service, "_build_flow_bundle", build_flow)
    results = [_match_result(index) for index in range(8)]
    bundle = service._build_write_bundle(
        user_id="u",
        task_id="TASK-NESTED",
        scenario_type="BANK_ENTERPRISE",
        results=results,
    )

    assert len(bundle.ledger_rows) == 8


def test_thread_agent_suite_reuses_private_provider_and_usage_per_worker(monkeypatch) -> None:
    gate = Barrier(2)

    class FlowProvider:
        model = "flow-provider"

        def complete(self, messages, **kwargs) -> LLMResult:
            del kwargs
            content = "\n".join(message["content"] for message in messages)
            flow_id = "FLOW-A" if "FLOW-A" in content else "FLOW-B"
            prompt_tokens = 101 if flow_id == "FLOW-A" else 202
            gate.wait(timeout=1)
            return LLMResult(
                text=json.dumps(
                    {
                        "decision": "PENDING_HUMAN",
                        "risk_level": "MEDIUM",
                        "reason": flow_id,
                        "ai_suggestion": "PENDING_HUMAN",
                        "evidence": ["rule-1"],
                        "confidence": 0.88,
                    }
                ),
                prompt_tokens=prompt_tokens,
                completion_tokens=10,
                model=f"model-{flow_id}",
            )

    monkeypatch.setattr(workflow_module, "get_llm_provider", FlowProvider)

    def run(flow_id: str) -> tuple[int, int, int, int, int, str]:
        suite = workflow_module._thread_agent_suite()
        repeated = workflow_module._thread_agent_suite()
        decision = suite.audit_agent.decide_with_llm(
            flow_id=flow_id,
            error_type="AMOUNT_MISMATCH",
            exception_branch="BE-R002",
            bank_amount="100.00",
            clear_amount="99.00",
            amount_diff="1.00",
            evidence=[_evidence()],
        )
        assert repeated is suite
        assert suite.audit_agent.provider is suite.trace_agent.provider
        assert suite.audit_agent.provider is suite.extraction_agent.provider
        return (
            id(suite),
            id(suite.audit_agent),
            id(suite.audit_agent.provider),
            suite.audit_agent.last_llm_result.prompt_tokens,
            suite.audit_agent.last_llm_summary.prompt_tokens,
            decision.reason,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        result_a = executor.submit(run, "FLOW-A")
        result_b = executor.submit(run, "FLOW-B")
        observed_a = result_a.result(timeout=2)
        observed_b = result_b.result(timeout=2)

    assert observed_a[:3] != observed_b[:3]
    assert observed_a[3:] == (101, 101, "FLOW-A")
    assert observed_b[3:] == (202, 202, "FLOW-B")


def test_parallel_real_workflow_matches_serial_and_isolates_trace_usage(monkeypatch) -> None:
    service = ReconciliationService()
    lock = Lock()
    provider_calls: list[tuple[str, str, int, int]] = []
    provider_barriers: dict[str, Barrier] = {}

    class FlowProvider:
        model = "flow-provider"

        def complete(self, messages, **kwargs) -> LLMResult:
            del kwargs
            payload = json.loads(messages[-1]["content"])
            flow_id = str(payload["flow_id"])
            task = str(payload["task"])
            barrier = provider_barriers.get(task)
            if barrier is not None:
                barrier.wait(timeout=2)
            with lock:
                provider_calls.append((flow_id, task, id(self), get_ident()))

            flow_index = 1 if flow_id == "FLOW-A" else 2
            task_code = {"extraction": 1, "trace": 2, "audit": 3}[task]
            if task == "extraction":
                output = {
                    "standard_type": "REVERSAL",
                    "original_flow_id": f"ORIGINAL-{flow_id}",
                    "cleaned_remark": f"cleaned-{flow_id}",
                    "confidence": 0.95,
                }
            elif task == "trace":
                output = {
                    "trace_found": True,
                    "related_flow_ids": [f"RELATED-{flow_id}"],
                    "trace_summary": f"trace-{flow_id}",
                    "confidence": 0.95,
                }
            else:
                output = {
                    "decision": "PENDING_HUMAN",
                    "risk_level": "MEDIUM",
                    "reason": f"decision-{flow_id}",
                    "ai_suggestion": "PENDING_HUMAN",
                    "evidence": [f"rule-{flow_id}"],
                    "confidence": 0.95,
                }
            return LLMResult(
                text=json.dumps(output),
                prompt_tokens=flow_index * 100 + task_code * 10,
                completion_tokens=flow_index * 10 + task_code,
                model=f"model-{flow_id}-{task}",
            )

    def provider_factory() -> FlowProvider:
        return FlowProvider()

    monkeypatch.setattr(workflow_module, "get_llm_provider", provider_factory)

    class ThreadSafeTransactions:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def _row(self, side: str, flow_id: str) -> dict[str, str]:
            with lock:
                self.calls.append((side, flow_id))
            summary = "客户退款冲正" if flow_id == "FLOW-A" else "普通摘要"
            return {
                "flow_id": flow_id,
                "summary": summary,
                "accounting_date": "2026-07-16",
            }

        def get_bank_row(self, *, user_id: str, task_id: str, flow_id: str):
            del user_id, task_id
            return self._row("bank", flow_id)

        def get_clear_row(self, *, user_id: str, task_id: str, flow_id: str):
            del user_id, task_id
            return self._row("clear", flow_id)

    transactions = ThreadSafeTransactions()
    monkeypatch.setattr(reconciliation_module, "transaction_service", transactions)

    class ThreadSafeToolExecutor:
        def __init__(self, barrier: Barrier | None = None) -> None:
            self.barrier = barrier
            self.active = 0
            self.peak = 0
            self.calls: list[str] = []
            self.completion_order: list[str] = []

        def execute(self, name, args, context) -> ToolCallResult:
            del args
            assert name == "search_rules"
            flow_id = context.flow_id
            with lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
                self.calls.append(flow_id)
            try:
                if self.barrier is not None:
                    self.barrier.wait(timeout=2)
                    if flow_id == "FLOW-A":
                        time.sleep(0.03)
                result = SearchRulesOutput(
                    items=[_integration_evidence(flow_id)],
                    rewritten_query=f"rewritten-{flow_id}",
                )
                with lock:
                    self.completion_order.append(flow_id)
                return ToolCallResult(
                    tool_name="search_rules",
                    status="SUCCEEDED",
                    result=result,
                    attempt=1,
                    duration_ms=1.0,
                    attempts=[
                        ToolAttemptRecord(
                            attempt=1,
                            status="SUCCEEDED",
                            duration_ms=1.0,
                        )
                    ],
                )
            finally:
                with lock:
                    self.active -= 1

    results = [
        ReconciliationMatchResult(
            flow_id="FLOW-A",
            status="PENDING_HUMAN",
            error_type="NARRATIVE_NAME_MISMATCH",
            exception_branch="BE-R004",
            bank_amount=Decimal("100.00"),
            clear_amount=Decimal("100.00"),
            amount_diff=Decimal("0.00"),
        ),
        ReconciliationMatchResult(
            flow_id="FLOW-B",
            status="PENDING_HUMAN",
            error_type="BANK_UNARRIVED",
            exception_branch="BE-R005",
            bank_amount=Decimal("200.00"),
            clear_amount=None,
            amount_diff=Decimal("200.00"),
        ),
    ]

    serial_tool = ThreadSafeToolExecutor()
    monkeypatch.setattr(workflow_module.default_tool_executor, "execute", serial_tool.execute)
    serial = service._merge_flow_bundles(
        [
            service._build_flow_bundle(
                result,
                user_id="u",
                task_id="TASK-REAL-WORKFLOW",
                scenario_type="BANK_ENTERPRISE",
                emitter=None,
                stream_seq_start=0,
            )
            for result in results
        ]
    )

    with lock:
        provider_calls.clear()
        transactions.calls.clear()
    provider_barriers["audit"] = Barrier(2)
    parallel_tool = ThreadSafeToolExecutor(Barrier(2))
    monkeypatch.setattr(workflow_module.default_tool_executor, "execute", parallel_tool.execute)
    parallel = service._build_write_bundle(
        user_id="u",
        task_id="TASK-REAL-WORKFLOW",
        scenario_type="BANK_ENTERPRISE",
        results=results,
    )

    assert _canonical_bundle(parallel) == _canonical_bundle(serial)
    assert [row.flow_id for row in parallel.ledger_rows] == ["FLOW-A", "FLOW-B"]
    assert [snapshot[0] for snapshot in parallel.trace_snapshots] == ["FLOW-A", "FLOW-B"]
    assert parallel_tool.peak == 2
    assert parallel_tool.completion_order == ["FLOW-B", "FLOW-A"]

    assert provider_calls == []

    for flow_id in ("FLOW-A", "FLOW-B"):
        assert [side for side, flow in transactions.calls if flow == flow_id] == ["bank", "clear"]

    trace_ids: set[str] = set()
    for flow_id, trace_id, spans in parallel.trace_snapshots:
        trace_ids.add(trace_id)
        validate_trace_snapshot(spans)
        assert [span.sequence_no for span in spans] == list(range(1, len(spans) + 1))
        assert spans[0].span_type == SpanType.WORKFLOW
        assert spans[0].parent_span_id is None
        assert spans[0].outcome == "PENDING_HUMAN"
        assert spans[-1].span_type == SpanType.FINAL
        assert spans[-1].outcome == "PENDING_HUMAN"
        tool_span = next(span for span in spans if span.span_type == SpanType.TOOL)
        assert tool_span.evidence_ids == [f"rule-{flow_id}"]
        assert not any(span.span_type == SpanType.AGENT for span in spans)
        assert any(span.name == "RuleAudit" for span in spans)

    assert len(trace_ids) == 2
    assert parallel.ai_processed_rows == 2
    assert parallel.fallback_l2_rows == 0
    assert parallel.fallback_l3_rows == 0
    assert parallel.total_prompt_tokens == 0
    assert parallel.total_completion_tokens == 0
    assert parallel.saved_prompt_tokens == 0
    assert parallel.saved_completion_tokens == 0
    assert [row["llm_tokens"] for row in parallel.agent_log_rows] == [0, 0]


def test_search_rules_adapter_serializes_shared_retriever_state() -> None:
    active = 0
    peak = 0
    lock = Lock()

    class SlowRetriever:
        store = None

        def search(self, request) -> RagSearchResponse:
            nonlocal active, peak
            del request
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                time.sleep(0.01)
                return RagSearchResponse(items=[_evidence()], rewritten_query=None)
            finally:
                with lock:
                    active -= 1

    adapter = make_search_rules_adapter(
        retriever=SlowRetriever(),
        rag_breaker=CircuitBreaker(fail_threshold=2, open_seconds=30),
    )
    context = ToolContext(
        user_id="u",
        task_id="t",
        flow_id="f",
        scenario_type="BANK_ENTERPRISE",
        exception_branch="BE-R002",
    )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(adapter, SearchRulesArgs(query="q"), context) for _ in range(8)]
        for future in futures:
            assert len(future.result(timeout=2).items) == 1

    assert peak == 1


def test_llm_breaker_singleton_is_safe_during_parallel_worker_startup(monkeypatch) -> None:
    monkeypatch.setattr(reliability_module, "_llm_breaker", None)
    gate = Barrier(8)

    def load_breaker() -> int:
        gate.wait(timeout=1)
        return id(reliability_module.get_llm_breaker())

    with ThreadPoolExecutor(max_workers=8) as executor:
        breaker_ids = [
            future.result(timeout=2) for future in [executor.submit(load_breaker) for _ in range(8)]
        ]

    assert len(set(breaker_ids)) == 1


def test_circuit_breaker_allows_only_one_half_open_probe() -> None:
    now = [0.0]
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=1, time_fn=lambda: now[0])
    assert breaker.record_failure() == "OPEN"
    now[0] = 2.0

    with ThreadPoolExecutor(max_workers=8) as executor:
        allowed = list(executor.map(lambda _: breaker.allow_request(), range(8)))

    assert allowed.count(True) == 1


def _match_result(index: int) -> ReconciliationMatchResult:
    return ReconciliationMatchResult(
        flow_id=f"FLOW-{index}",
        status="PENDING_HUMAN",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount=Decimal("100.00"),
        clear_amount=Decimal("99.00"),
        amount_diff=Decimal("1.00"),
    )


def _flow_index(result: ReconciliationMatchResult) -> int:
    return int(result.flow_id.rsplit("-", 1)[1])


def _flow_bundle(
    result: ReconciliationMatchResult,
    *,
    stream_seq: int,
) -> ReconciliationFlowBundle:
    index = _flow_index(result)
    return ReconciliationFlowBundle(
        ledger_row=LedgerRow(
            id=0,
            task_id="TASK",
            flow_id=result.flow_id,
            error_type=result.error_type or "",
            exception_branch=result.exception_branch,
            bank_amount=result.bank_amount,
            clear_amount=result.clear_amount,
            discrepancy_amount=Decimal("1.00"),
            ai_audit_opinion="test",
            ai_confidence=Decimal("0.88"),
            rag_source="rule-1",
            fallback_path="L1",
            handle_status="PENDING_HUMAN",
        ),
        rag_log_row={"flow_id": result.flow_id},
        agent_log_row={"flow_id": result.flow_id},
        trace_snapshot=(result.flow_id, f"TRACE-{index}", []),
        prompt_tokens=index + 1,
        completion_tokens=index + 101,
        saved_prompt_tokens=0,
        saved_completion_tokens=0,
        fallback_l2_rows=0,
        fallback_l3_rows=0,
        stream_seq=stream_seq,
    )


def _integration_evidence(flow_id: str) -> RagSearchItem:
    return RagSearchItem(
        chunk_id=f"rule-{flow_id}",
        source=f"rules.md#{flow_id}",
        source_name="Rule",
        source_url=f"https://example.com/{flow_id}",
        source_file="rules.md",
        section_title=flow_id,
        element_type="paragraph",
        business_tags=["integration"],
        score=0.9,
        content=f"rule for {flow_id}",
    )


def _canonical_bundle(bundle: ReconciliationWriteBundle) -> dict[str, object]:
    traces: list[tuple[str, list[dict[str, object]]]] = []
    for flow_id, _trace_id, spans in bundle.trace_snapshots:
        sequence_by_span_id = {span.span_id: span.sequence_no for span in spans}
        canonical_spans: list[dict[str, object]] = []
        for span in spans:
            row = span.model_dump(
                mode="json",
                exclude={
                    "trace_id",
                    "span_id",
                    "parent_span_id",
                    "started_at",
                    "ended_at",
                    "duration_ms",
                },
            )
            row["parent_sequence_no"] = sequence_by_span_id.get(span.parent_span_id)
            canonical_spans.append(row)
        traces.append((flow_id, canonical_spans))
    return {
        "ledger_rows": [row.model_dump(mode="json") for row in bundle.ledger_rows],
        "rag_log_rows": bundle.rag_log_rows,
        "agent_log_rows": bundle.agent_log_rows,
        "traces": traces,
        "ai_processed_rows": bundle.ai_processed_rows,
        "fallback_l2_rows": bundle.fallback_l2_rows,
        "fallback_l3_rows": bundle.fallback_l3_rows,
        "total_prompt_tokens": bundle.total_prompt_tokens,
        "total_completion_tokens": bundle.total_completion_tokens,
        "saved_prompt_tokens": bundle.saved_prompt_tokens,
        "saved_completion_tokens": bundle.saved_completion_tokens,
    }


def _evidence() -> RagSearchItem:
    return RagSearchItem(
        chunk_id="rule-1",
        source="rules.md#amount",
        source_name="Rule",
        source_url="https://example.com/rule",
        source_file="rules.md",
        section_title="Amount",
        element_type="paragraph",
        business_tags=["amount_mismatch"],
        score=0.9,
        content="amount mismatch rule",
    )

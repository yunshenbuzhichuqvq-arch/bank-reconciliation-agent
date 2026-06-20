from bank_reconciliation_agent.agents.audit_agent import AuditAgent, AuditDecision
from bank_reconciliation_agent.core.llm.provider import LLMResult
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from bank_reconciliation_agent.services.circuit_breaker import CircuitBreaker
from bank_reconciliation_agent.services.workflow import ReconciliationState, _llm_usage, run_item


def test_llm_usage_carries_cached_flag() -> None:
    class CachedAgent:
        last_llm_result = LLMResult(
            text="{}",
            prompt_tokens=100,
            completion_tokens=20,
            model="fake",
            cached=True,
        )

    assert _llm_usage(CachedAgent()) == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "llm_tokens": 120,
        "cached": True,
    }


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


def _low_score_evidence() -> RagSearchItem:
    return RagSearchItem(
        chunk_id="rule-low",
        source="rules.md#rule-low",
        source_name="低分规则",
        source_url="https://example.com/rule-low",
        source_file="rules.md",
        section_title="rule-low",
        element_type="paragraph",
        business_tags=["bank_enterprise"],
        score=0.2,
        content="低分规则证据",
    )


def _state(exception_branch: str, *, summary: str = "普通摘要") -> ReconciliationState:
    return {
        "task_id": "TASK-WF-001",
        "user_id": "demo_user",
        "thread_id": "THREAD-WF-001",
        "scenario_type": "BANK_ENTERPRISE",
        "current_queue_id": None,
        "source_a_item": {"flow_id": f"FLOW-{exception_branch}", "summary": summary},
        "source_b_item": {"flow_id": f"FLOW-{exception_branch}", "summary": summary},
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
    }


def test_run_item_returns_audit_decision_for_five_bank_enterprise_branches() -> None:
    for branch in ["BE-R002", "BE-R004", "BE-R005", "BE-R006", "BE-R008"]:
        result = run_item(
            _state(branch, summary="冲正退款" if branch == "BE-R004" else "普通摘要"),
            extraction_agent=SpyExtractionAgent(),
            trace_agent=SpyTraceAgent(),
            audit_agent=SpyAuditAgent(),
            retriever=StaticRetriever(),
        )

        assert result["audit_decision"]["flow_id"] == f"FLOW-{branch}"
        assert result["audit_decision"]["decision"] == "PENDING_HUMAN"
        assert result["rag_context"][0]["chunk_id"] == "rule-001"
        assert result["next_action"] == "PENDING_HUMAN"


def test_run_item_routes_extraction_for_reversal_narrative_only() -> None:
    extraction_agent = SpyExtractionAgent()

    run_item(
        _state("BE-R004", summary="客户退款冲正"),
        extraction_agent=extraction_agent,
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        retriever=StaticRetriever(),
    )
    run_item(
        _state("BE-R002", summary="客户退款冲正"),
        extraction_agent=extraction_agent,
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        retriever=StaticRetriever(),
    )

    assert extraction_agent.calls == ["FLOW-BE-R004"]


def test_run_item_routes_trace_for_single_side_branches() -> None:
    trace_agent = SpyTraceAgent()

    for branch in ["BE-R005", "BE-R006", "BE-R008"]:
        run_item(
            _state(branch),
            extraction_agent=SpyExtractionAgent(),
            trace_agent=trace_agent,
            audit_agent=SpyAuditAgent(),
            retriever=StaticRetriever(),
        )

    assert trace_agent.calls == ["FLOW-BE-R005", "FLOW-BE-R006"]


def test_run_item_binds_trace_context(monkeypatch) -> None:
    bound_contexts: list[dict[str, str]] = []

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.bind_trace_context",
        lambda **kwargs: bound_contexts.append(kwargs),
    )

    run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        retriever=StaticRetriever(),
    )

    assert bound_contexts == [
        {"trace_id": "TASK-WF-001", "user_id": "demo_user", "thread_id": "THREAD-WF-001"}
    ]


def test_run_item_retries_schema_drift_then_falls_back_to_human() -> None:
    audit_agent = InvalidSchemaAuditAgent()

    result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=audit_agent,
        retriever=StaticRetriever(),
    )

    assert audit_agent.calls == 3
    assert result["retry_count"] == 3
    assert result["audit_decision"]["decision"] == "PENDING_HUMAN"
    assert "SchemaHook 校验失败" in result["audit_decision"]["reason"]
    schema_logs = [row for row in result["agent_logs"] if row["agent_name"] == "SchemaHook"]
    assert [row["retry_count"] for row in schema_logs] == [1, 2, 3]


def test_run_item_memory_hook_keeps_state_intact() -> None:
    result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        retriever=StaticRetriever(),
    )

    assert result["source_a_item"]["flow_id"] == "FLOW-BE-R002"


def test_run_item_passes_memory_context_to_audit_agent(monkeypatch) -> None:
    audit_agent = SpyAuditAgent()

    def fake_memory_hook(state: ReconciliationState) -> ReconciliationState:
        state["memory_context"] = "memory context from hook"
        return state

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.memory_hook",
        fake_memory_hook,
    )

    run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=audit_agent,
        retriever=StaticRetriever(),
    )

    assert audit_agent.memory_contexts == ["memory context from hook"]


def test_run_item_rag_failure_opens_breaker_and_short_circuits_to_human(monkeypatch) -> None:
    now = 0.0

    def fake_time() -> float:
        return now

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.workflow.rag_circuit_breaker",
        CircuitBreaker(fail_threshold=1, open_seconds=30, time_fn=fake_time),
    )

    result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        retriever=FailingRetriever(),
    )

    assert result["rag_context"] == []
    assert result["fallback_path"] == "HUMAN"
    assert result["audit_decision"]["decision"] == "PENDING_HUMAN"
    assert any(
        row["agent_name"] == "RAGCircuitBreaker" and row["breaker_state"] == "OPEN"
        for row in result["agent_logs"]
    )

    skipped_result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        retriever=StaticRetriever(),
    )

    assert skipped_result["rag_context"] == []
    assert any(
        row["agent_name"] == "RAGCircuitBreaker" and row["reason"] == "breaker open, skip rag retrieval"
        for row in skipped_result["agent_logs"]
    )


def test_run_item_rag_half_open_success_closes_breaker(monkeypatch) -> None:
    now = 0.0

    def fake_time() -> float:
        return now

    breaker = CircuitBreaker(fail_threshold=1, open_seconds=10, time_fn=fake_time)
    monkeypatch.setattr("bank_reconciliation_agent.services.workflow.rag_circuit_breaker", breaker)

    run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        retriever=FailingRetriever(),
    )

    now = 11.0
    result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        retriever=StaticRetriever(),
    )

    assert breaker.state == "CLOSED"
    assert result["rag_context"][0]["chunk_id"] == "rule-001"
    assert any(
        row["agent_name"] == "RAGCircuitBreaker" and row["reason"] == "half-open probe succeeded"
        for row in result["agent_logs"]
    )


def test_run_item_constraint_c3_turns_low_risk_large_diff_to_human() -> None:
    state = _state("BE-R002")
    state["math_result"]["amount_diff"] = "10001.00"

    result = run_item(
        state,
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=LowRiskAutoFixedAuditAgent(confidence=0.90),
        retriever=StaticRetriever(),
    )

    assert result["audit_decision"]["decision"] == "PENDING_HUMAN"
    assert "C3" in result["audit_decision"]["reason"]
    assert result["next_action"] == "PENDING_HUMAN"


def test_run_item_constraint_c4_rejects_placeholder_reason() -> None:
    result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=PlaceholderReasonAuditAgent(),
        retriever=StaticRetriever(),
    )

    assert result["audit_decision"]["decision"] == "PENDING_HUMAN"
    assert "C4" in result["audit_decision"]["reason"]


def test_run_item_constraint_c5_rejects_low_confidence_auto_fix() -> None:
    result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=LowRiskAutoFixedAuditAgent(confidence=0.84),
        retriever=StaticRetriever(),
    )

    assert result["audit_decision"]["decision"] == "PENDING_HUMAN"
    assert "C5" in result["audit_decision"]["reason"]


def test_run_item_constraint_c6_rejects_auto_fix_on_low_rag_score() -> None:
    result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=LowRiskAutoFixedAuditAgent(confidence=0.90),
        retriever=LowScoreRetriever(),
    )

    assert result["audit_decision"]["decision"] == "PENDING_HUMAN"
    assert "C6" in result["audit_decision"]["reason"]


def test_run_item_decision_hook_keeps_compliant_auto_fix_without_extra_calls() -> None:
    audit_agent = CountingAutoFixedAuditAgent(confidence=0.90)

    result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=audit_agent,
        retriever=StaticRetriever(),
    )

    assert audit_agent.calls == 1
    assert result["audit_decision"]["decision"] == "AUTO_FIXED"
    assert result["next_action"] == "AUTO_FIXED"


def test_run_item_invalid_llm_decision_literal_uses_agent_fallback_instead_of_outer_error() -> None:
    result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=AuditAgent(provider=InvalidDecisionLiteralProvider()),
        retriever=StaticRetriever(),
    )

    assert result["audit_decision"]["decision"] == "PENDING_HUMAN"
    assert result["audit_decision"]["fallback_applied"] is True
    assert result["audit_decision"]["evidence"][0]["chunk_id"] == "rule-001"
    assert "金额不一致" in result["audit_decision"]["reason"]
    assert "AI 处理异常" not in result["audit_decision"]["reason"]
    assert result["error_message"] is None


class StaticRetriever:
    def search(self, request):
        del request
        return RagSearchResponse(items=[_evidence()])


class LowScoreRetriever:
    def search(self, request):
        del request
        return RagSearchResponse(items=[_low_score_evidence()])


class FailingRetriever:
    def search(self, request):
        del request
        raise RuntimeError("chroma unavailable")


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
    def __init__(self) -> None:
        self.calls: list[str] = []

    def trace(
        self,
        *,
        flow_id: str,
        summary: str,
        transaction_date: str | None,
        amount: str | None,
        remark: str | None,
    ):
        del summary, transaction_date, amount, remark
        self.calls.append(flow_id)
        return {
            "trace_found": True,
            "related_flow_ids": ["FLOW-T1-001"],
            "trace_summary": "发现 T+1 线索",
            "confidence": 0.9,
        }


class SpyAuditAgent:
    def __init__(self) -> None:
        self.memory_contexts: list[str | None] = []

    def decide_with_llm(
        self,
        flow_id: str,
        error_type: str,
        exception_branch: str | None,
        bank_amount: str | None,
        clear_amount: str | None,
        amount_diff: str | None,
        evidence: list[RagSearchItem],
        memory_context: str | None = None,
    ) -> AuditDecision:
        del error_type, exception_branch, bank_amount, clear_amount, amount_diff
        self.memory_contexts.append(memory_context)
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


class InvalidSchemaAuditAgent:
    def __init__(self) -> None:
        self.calls = 0

    def decide_with_llm(
        self,
        flow_id: str,
        error_type: str,
        exception_branch: str | None,
        bank_amount: str | None,
        clear_amount: str | None,
        amount_diff: str | None,
        evidence: list[RagSearchItem],
        few_shot_cases: list[dict[str, object]] | None = None,
        trace_context: dict[str, object] | None = None,
        memory_context: str | None = None,
    ) -> dict[str, object]:
        del (
            error_type,
            exception_branch,
            bank_amount,
            clear_amount,
            amount_diff,
            evidence,
            few_shot_cases,
            trace_context,
            memory_context,
        )
        self.calls += 1
        return {
            "flow_id": flow_id,
            "decision": "FIXED",
            "risk_level": "LOW",
            "reason": "invalid schema",
            "ai_suggestion": "APPROVED_MATCH",
            "evidence": [],
            "confidence": 0.9,
            "next_action": "AUTO_FIXED",
        }


class LowRiskAutoFixedAuditAgent:
    def __init__(self, *, confidence: float) -> None:
        self.confidence = confidence

    def decide_with_llm(self, flow_id: str, **kwargs) -> AuditDecision:
        return AuditDecision(
            flow_id=flow_id,
            decision="AUTO_FIXED",
            risk_level="LOW",
            reason="auto fixed",
            ai_suggestion="APPROVED_MATCH",
            evidence=kwargs["evidence"],
            confidence=self.confidence,
            fallback_applied=False,
            fallback_level=0,
            next_action="AUTO_FIXED",
        )


class CountingAutoFixedAuditAgent(LowRiskAutoFixedAuditAgent):
    def __init__(self, *, confidence: float) -> None:
        super().__init__(confidence=confidence)
        self.calls = 0

    def decide_with_llm(self, flow_id: str, **kwargs) -> AuditDecision:
        self.calls += 1
        return super().decide_with_llm(flow_id=flow_id, **kwargs)


class PlaceholderReasonAuditAgent:
    def decide_with_llm(self, flow_id: str, **kwargs) -> AuditDecision:
        return AuditDecision(
            flow_id=flow_id,
            decision="PENDING_HUMAN",
            risk_level="MEDIUM",
            reason="TBD",
            ai_suggestion="PENDING_HUMAN",
            evidence=kwargs["evidence"],
            confidence=0.90,
            fallback_applied=False,
            fallback_level=0,
            next_action="PENDING_HUMAN",
        )


class InvalidDecisionLiteralProvider:
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
    ) -> LLMResult:
        del messages, temperature, response_format
        return LLMResult(
            text=(
                '{"decision":"APPROVED_MATCH","risk_level":"LOW","reason":"模型建议自动平账",'
                '"ai_suggestion":"APPROVED_MATCH","evidence":["rule"],"confidence":0.91}'
            ),
            prompt_tokens=10,
            completion_tokens=8,
            model="invalid-literal",
        )

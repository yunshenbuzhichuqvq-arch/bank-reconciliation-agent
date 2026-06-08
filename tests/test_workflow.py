from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item


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

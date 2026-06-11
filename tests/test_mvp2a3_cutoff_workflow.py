from decimal import Decimal

from bank_reconciliation_agent.agents.audit_agent import AuditAgent
from bank_reconciliation_agent.agents.trace_agent import TraceResult
from bank_reconciliation_agent.core.llm.provider import FakeLLMProvider
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from bank_reconciliation_agent.services.exception_router import BranchResult
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item


def _evidence() -> RagSearchItem:
    return RagSearchItem(
        chunk_id="rule-bc-r003",
        source="rules.md#bc-r003",
        source_name="规则",
        source_url="https://example.com/bc-r003",
        source_file="rules.md",
        section_title="bc-r003",
        element_type="paragraph",
        business_tags=["bank_clearing"],
        score=0.9,
        content="跨日切 T+1 补记规则",
    )


def _state(*, t1_candidate: dict[str, str] | None) -> ReconciliationState:
    return {
        "task_id": "TASK-BC-R003-001",
        "user_id": "demo_user",
        "thread_id": "THREAD-BC-R003-001",
        "scenario_type": "BANK_CLEARING",
        "current_queue_id": None,
        "source_a_item": {
            "flow_id": "FLOW-CORE-T1",
            "summary": "核心 T+1 入账",
            "accounting_date": "2026-06-10",
        },
        "source_b_item": {
            "flow_id": "FLOW-CLEAR-CUTOFF",
            "summary": "清算跨日切",
            "trade_date": "2026-06-09",
        },
        "error_type": "CUTOFF_CROSS_DAY",
        "exception_branch": "BC-R003",
        "math_result": {
            "bank_amount": "100.00",
            "clear_amount": None,
            "amount_diff": None,
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
        "t1_candidate": t1_candidate,
    }


def test_run_item_routes_bc_r003_to_trace_with_t1_candidate_context() -> None:
    trace_agent = CaptureTraceAgent()

    result = run_item(
        _state(
            t1_candidate={"flow_id": "FLOW-CORE-T1", "accounting_date": "2026-06-10"}
        ),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=trace_agent,
        audit_agent=StaticAuditAgent(),
        retriever=StaticRetriever(),
    )

    assert trace_agent.calls == [
        {
            "flow_id": "FLOW-CORE-T1",
            "cutoff_t1_context": {
                "flow_id": "FLOW-CORE-T1",
                "accounting_date": "2026-06-10",
            },
        }
    ]
    assert result["agent_logs"][0]["agent_name"] == "TraceAgent"


def test_reconciliation_service_propagates_t1_candidate_into_workflow_state(monkeypatch) -> None:
    service = ReconciliationService()
    captured_states: list[dict[str, object]] = []

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.transaction_service.get_bank_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "核心 T+1 入账"},
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.transaction_service.get_clear_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "清算跨日切"},
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.run_item",
        lambda state: captured_states.append(state) or state,
    )

    branch_result = BranchResult(
        flow_id="FLOW-CLEAR-CUTOFF",
        action="EXCEPTION",
        error_type="CUTOFF_CROSS_DAY",
        exception_branch="BC-R003",
        bank_amount=Decimal("100.00"),
        clear_amount=None,
        amount_diff=None,
        t1_candidate={"flow_id": "FLOW-CORE-T1", "accounting_date": "2026-06-10"},
    )
    match_result = service._to_match_result(branch_result)

    service._run_workflow_for_result(
        user_id="demo_user",
        task_id="TASK-BC-R003-001",
        scenario_type="BANK_CLEARING",
        result=match_result,
        rag_query="CUTOFF_CROSS_DAY BC-R003",
    )

    assert captured_states[0]["t1_candidate"] == {
        "flow_id": "FLOW-CORE-T1",
        "accounting_date": "2026-06-10",
    }


def test_bc_r003_trace_context_drives_t1_audit_semantics() -> None:
    result = run_item(
        _state(
            t1_candidate={"flow_id": "FLOW-CORE-T1", "accounting_date": "2026-06-10"}
        ),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=StaticTraceAgent(
            TraceResult(
                trace_found=True,
                related_flow_ids=["FLOW-CORE-T1"],
                trace_summary="T+1 已配对，核心次日补记成功",
                confidence=0.91,
            )
        ),
        audit_agent=AuditAgent(provider=FakeLLMProvider()),
        retriever=StaticRetriever(),
    )

    assert "T+1 已配对" in result["audit_decision"]["reason"]
    assert result["next_action"] == "PENDING_HUMAN"


def test_bc_r003_without_candidate_marks_wait_for_t1_follow_up() -> None:
    result = run_item(
        _state(t1_candidate=None),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=StaticTraceAgent(
            TraceResult(
                trace_found=False,
                related_flow_ids=[],
                trace_summary="疑似跨日切，待 T+1 补齐",
                confidence=0.2,
            )
        ),
        audit_agent=AuditAgent(provider=FakeLLMProvider()),
        retriever=StaticRetriever(),
    )

    assert "待 T+1 补齐" in result["audit_decision"]["reason"]
    assert result["next_action"] == "PENDING_HUMAN"


class StaticRetriever:
    def search(self, request):
        del request
        return RagSearchResponse(items=[_evidence()])


class NoopExtractionAgent:
    def extract(self, *, flow_id: str, summary: str, remark: str | None):
        del flow_id, summary, remark
        return {}


class CaptureTraceAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def trace(
        self,
        *,
        flow_id: str,
        summary: str,
        transaction_date: str | None,
        amount: str | None,
        remark: str | None,
        cutoff_t1_context: dict[str, str] | None = None,
    ) -> dict[str, object]:
        del summary, transaction_date, amount, remark
        self.calls.append(
            {"flow_id": flow_id, "cutoff_t1_context": cutoff_t1_context}
        )
        return {
            "trace_found": True,
            "related_flow_ids": ["FLOW-CORE-T1"],
            "trace_summary": "T+1 已配对，核心次日补记成功",
            "confidence": 0.91,
        }


class StaticTraceAgent:
    def __init__(self, result: TraceResult) -> None:
        self.result = result

    def trace(
        self,
        *,
        flow_id: str,
        summary: str,
        transaction_date: str | None,
        amount: str | None,
        remark: str | None,
        cutoff_t1_context: dict[str, str] | None = None,
    ) -> TraceResult:
        del flow_id, summary, transaction_date, amount, remark, cutoff_t1_context
        return self.result


class StaticAuditAgent:
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
    ):
        del few_shot_cases
        return AuditAgent(provider=FakeLLMProvider()).decide_with_llm(
            flow_id=flow_id,
            error_type=error_type,
            exception_branch=exception_branch,
            bank_amount=bank_amount,
            clear_amount=clear_amount,
            amount_diff=amount_diff,
            evidence=evidence,
            trace_context=trace_context,
            memory_context=memory_context,
        )

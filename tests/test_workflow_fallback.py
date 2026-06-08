from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
from bank_reconciliation_agent.services.agent_log import AgentLogService, agent_execution_log_table
from bank_reconciliation_agent.services.ledger import LedgerService, error_ledger_table
from bank_reconciliation_agent.services.task import TaskService, reconciliation_task_table
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item
from decimal import Decimal
from sqlalchemy import create_engine, select


def _evidence(*, score: float = 0.9) -> RagSearchItem:
    return RagSearchItem(
        chunk_id="rule-001",
        source="rules.md#rule",
        source_name="规则",
        source_url="https://example.com/rule",
        source_file="rules.md",
        section_title="rule",
        element_type="paragraph",
        business_tags=["bank_enterprise"],
        score=score,
        content="规则证据",
    )


def _state() -> ReconciliationState:
    return {
        "task_id": "TASK-FB-001",
        "user_id": "demo_user",
        "thread_id": "THREAD-FB-001",
        "scenario_type": "BANK_ENTERPRISE",
        "current_queue_id": None,
        "source_a_item": {"flow_id": "FLOW-FB-001", "summary": "普通摘要"},
        "source_b_item": {"flow_id": "FLOW-FB-001", "summary": "普通摘要"},
        "error_type": "AMOUNT_MISMATCH",
        "exception_branch": "BE-R002",
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


def test_low_confidence_decision_escalates_to_l2_then_l3_then_human() -> None:
    audit_agent = SequenceAuditAgent([0.4, 0.5, 0.5])
    trace_agent = SpyTraceAgent(confidence=0.6)
    fallback_cases = [
        {
            "flow_id": "FLOW-OLD-001",
            "exception_branch": "BE-R002",
            "ai_audit_opinion": "历史人工确认金额差异需复核",
            "handle_status": "HELD",
        }
    ]

    result = run_item(
        _state(),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=trace_agent,
        audit_agent=audit_agent,
        retriever=StaticRetriever([_evidence()]),
        fallback_case_provider=StaticFallbackCaseProvider(fallback_cases),
    )

    assert audit_agent.calls == [1, 2, 3]
    assert audit_agent.call_args[0]["few_shot_cases"] is None
    assert audit_agent.call_args[0]["trace_context"] is None
    assert audit_agent.call_args[1]["few_shot_cases"] == fallback_cases
    assert audit_agent.call_args[1]["trace_context"] is None
    assert audit_agent.call_args[2]["few_shot_cases"] == fallback_cases
    assert audit_agent.call_args[2]["trace_context"] == {
        "trace_found": False,
        "related_flow_ids": [],
        "trace_summary": "未发现追溯线索",
        "confidence": 0.6,
    }
    assert trace_agent.calls == ["FLOW-FB-001"]
    assert result["fallback_level"] == 3
    assert result["fallback_path"] == "L1->L2->L3->HUMAN"
    assert result["audit_decision"]["decision"] == "PENDING_HUMAN"
    assert result["audit_decision"]["fallback_applied"] is True
    assert result["audit_decision"]["fallback_level"] == 3
    assert result["next_action"] == "PENDING_HUMAN"


def test_rag_miss_short_circuits_to_human_without_fallback() -> None:
    audit_agent = SequenceAuditAgent([0.4])
    trace_agent = SpyTraceAgent(confidence=0.9)

    result = run_item(
        _state(),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=trace_agent,
        audit_agent=audit_agent,
        retriever=StaticRetriever([]),
        fallback_case_provider=EmptyFallbackCaseProvider(),
    )

    assert audit_agent.calls == [1]
    assert trace_agent.calls == []
    assert result["fallback_level"] == 0
    assert result["fallback_path"] == "HUMAN"
    assert result["audit_decision"]["decision"] == "PENDING_HUMAN"
    assert result["audit_decision"]["confidence"] == 0.0


def test_low_rag_score_triggers_l2_even_when_l1_confidence_is_high() -> None:
    audit_agent = SequenceAuditAgent([0.9, 0.9])
    fallback_cases = [
        {
            "flow_id": "FLOW-OLD-002",
            "exception_branch": "BE-R002",
            "ai_audit_opinion": "历史人工确认可参考",
            "handle_status": "FIXED",
        }
    ]

    result = run_item(
        _state(),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=SpyTraceAgent(confidence=0.9),
        audit_agent=audit_agent,
        retriever=StaticRetriever([_evidence(score=0.2)]),
        fallback_case_provider=StaticFallbackCaseProvider(fallback_cases),
    )

    assert audit_agent.calls == [1, 2]
    assert audit_agent.call_args[1]["few_shot_cases"] == fallback_cases
    assert result["fallback_level"] == 2
    assert result["fallback_path"] == "L1->L2"
    assert result["audit_decision"]["fallback_applied"] is True


def test_l2_handles_empty_fallback_cases_without_error() -> None:
    audit_agent = SequenceAuditAgent([0.4, 0.9])

    result = run_item(
        _state(),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=SpyTraceAgent(confidence=0.9),
        audit_agent=audit_agent,
        retriever=StaticRetriever([_evidence()]),
        fallback_case_provider=EmptyFallbackCaseProvider(),
    )

    assert audit_agent.calls == [1, 2]
    assert audit_agent.call_args[1]["few_shot_cases"] == []
    assert result["fallback_level"] == 2
    assert result["fallback_path"] == "L1->L2"


def test_persistence_services_store_fallback_fields_and_task_stats() -> None:
    engine = create_engine("sqlite:///:memory:")
    ledger_service = LedgerService(engine)
    agent_log_service = AgentLogService(engine)
    task_service = TaskService(engine)

    task_service.replace_task(
        user_id="demo_user",
        task_id="TASK-FB-DB",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )
    ledger_service.replace_task_rows(
        user_id="demo_user",
        task_id="TASK-FB-DB",
        rows=[
            LedgerRowFactory.build(
                task_id="TASK-FB-DB",
                fallback_path="L1->L2->L3->HUMAN",
            )
        ],
    )
    agent_log_service.replace_task_rows(
        user_id="demo_user",
        task_id="TASK-FB-DB",
        rows=[
            agent_log_service.build_row(
                user_id="demo_user",
                task_id="TASK-FB-DB",
                queue_id=None,
                agent_name="AuditAgent",
                event_type="AUDIT_DECISION",
                input_payload={"flow_id": "FLOW-FB-DB"},
                output_payload={"decision": "PENDING_HUMAN"},
                prompt_version="v1",
                fallback_level=3,
                llm_tokens=384,
            )
        ],
    )
    task_service.increment_ai_stats(
        user_id="demo_user",
        task_id="TASK-FB-DB",
        ai_processed_rows=1,
        fallback_l2_rows=1,
        fallback_l3_rows=1,
        total_llm_tokens=384,
        total_llm_cost=Decimal("0.0002"),
    )

    with engine.connect() as connection:
        ledger_row = connection.execute(select(error_ledger_table)).mappings().one()
        agent_log_row = connection.execute(select(agent_execution_log_table)).mappings().one()
        task_row = connection.execute(select(reconciliation_task_table)).mappings().one()

    assert ledger_row["fallback_path"] == "L1->L2->L3->HUMAN"
    assert agent_log_row["prompt_version"] == "v1"
    assert agent_log_row["fallback_level"] == 3
    assert agent_log_row["llm_tokens"] == 384
    assert task_row["ai_processed_rows"] == 1
    assert task_row["fallback_l2_rows"] == 1
    assert task_row["fallback_l3_rows"] == 1
    assert task_row["total_llm_tokens"] == 384
    assert Decimal(str(task_row["total_llm_cost"])) == Decimal("0.0002")


class StaticRetriever:
    def __init__(self, items: list[RagSearchItem]) -> None:
        self.items = items

    def search(self, request):
        del request
        return RagSearchResponse(items=self.items)


class EmptyFallbackCaseProvider:
    def confirmed_cases(
        self,
        *,
        user_id: str,
        exception_branch: str | None,
        limit: int = 3,
    ) -> list[dict[str, object]]:
        del user_id, exception_branch, limit
        return []


class StaticFallbackCaseProvider:
    def __init__(self, cases: list[dict[str, object]]) -> None:
        self.cases = cases

    def confirmed_cases(
        self,
        *,
        user_id: str,
        exception_branch: str | None,
        limit: int = 3,
    ) -> list[dict[str, object]]:
        del user_id, exception_branch, limit
        return self.cases


class NoopExtractionAgent:
    def extract(self, *, flow_id: str, summary: str, remark: str | None):
        del flow_id, summary, remark
        return {}


class SpyTraceAgent:
    def __init__(self, *, confidence: float) -> None:
        self.confidence = confidence
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
            "trace_found": False,
            "related_flow_ids": [],
            "trace_summary": "未发现追溯线索",
            "confidence": self.confidence,
        }


class SequenceAuditAgent:
    def __init__(self, confidences: list[float]) -> None:
        self.confidences = confidences
        self.calls: list[int] = []
        self.call_args: list[dict[str, object]] = []

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
    ) -> AuditDecision:
        del error_type, exception_branch, bank_amount, clear_amount, amount_diff
        self.calls.append(len(self.calls) + 1)
        self.call_args.append(
            {
                "flow_id": flow_id,
                "evidence": evidence,
                "few_shot_cases": few_shot_cases,
                "trace_context": trace_context,
            }
        )
        confidence = self.confidences[min(len(self.calls) - 1, len(self.confidences) - 1)]
        return AuditDecision(
            flow_id=flow_id,
            decision="PENDING_HUMAN",
            risk_level="MEDIUM",
            reason="spy audit",
            ai_suggestion="PENDING_HUMAN",
            evidence=evidence,
            confidence=confidence if evidence else 0.0,
            fallback_applied=False,
            fallback_level=0,
            next_action="PENDING_HUMAN",
        )


class LedgerRowFactory:
    @staticmethod
    def build(task_id: str, fallback_path: str):
        from bank_reconciliation_agent.schemas.ledger import LedgerRow

        return LedgerRow(
            id=0,
            task_id=task_id,
            flow_id="FLOW-FB-DB",
            error_type="AMOUNT_MISMATCH",
            exception_branch="BE-R002",
            bank_amount=Decimal("100.00"),
            clear_amount=Decimal("99.00"),
            discrepancy_amount=Decimal("1.00"),
            ai_audit_opinion="低置信转人工",
            ai_confidence=Decimal("0.4000"),
            rag_source="rule-001",
            fallback_path=fallback_path,
            handle_status="PENDING_HUMAN",
        )

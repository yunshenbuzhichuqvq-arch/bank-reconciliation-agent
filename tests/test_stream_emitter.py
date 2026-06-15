from decimal import Decimal

from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.services.exception_router import BranchResult
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from bank_reconciliation_agent.services.stream_emitter import QueueEmitter
from bank_reconciliation_agent.services.workflow import run_item

from tests.test_workflow import SpyAuditAgent, SpyExtractionAgent, SpyTraceAgent, StaticRetriever, _state


def test_run_item_emits_ordered_agent_stream_events() -> None:
    emitter = QueueEmitter()

    result = run_item(
        _state("BE-R002"),
        extraction_agent=SpyExtractionAgent(),
        trace_agent=SpyTraceAgent(),
        audit_agent=SpyAuditAgent(),
        retriever=StaticRetriever(),
        emitter=emitter,
    )

    events = emitter.drain()

    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    assert {event.event_type for event in events} >= {
        StreamEventType.RAG_RETRIEVED,
        StreamEventType.AGENT_DECISION,
    }
    assert all(AgentStreamEvent.model_validate(event.model_dump()) for event in events)
    assert events[-1].payload["decision"] == result["audit_decision"]["decision"]


def test_run_item_default_emitter_does_not_reuse_null_emitter_instance() -> None:
    assert run_item.__kwdefaults__["emitter"] is None


def test_reconciliation_service_passes_emitter_to_workflow(monkeypatch) -> None:
    service = ReconciliationService()
    emitter = QueueEmitter()
    captured_emitters: list[QueueEmitter] = []

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.transaction_service.get_bank_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "银行流水"},
    )
    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.transaction_service.get_clear_row",
        lambda **kwargs: {"flow_id": kwargs["flow_id"], "summary": "清算流水"},
    )

    def fake_run_item(state, *, emitter):
        captured_emitters.append(emitter)
        return state

    monkeypatch.setattr("bank_reconciliation_agent.services.reconciliation.run_item", fake_run_item)

    branch_result = BranchResult(
        flow_id="FLOW-STREAM",
        action="EXCEPTION",
        error_type="AMOUNT_MISMATCH",
        exception_branch="BE-R002",
        bank_amount=Decimal("100.00"),
        clear_amount=Decimal("99.00"),
        amount_diff=Decimal("1.00"),
    )

    service._run_workflow_for_result(
        user_id="demo_user",
        task_id="TASK-STREAM",
        scenario_type="BANK_ENTERPRISE",
        result=service._to_match_result(branch_result),
        rag_query="AMOUNT_MISMATCH BE-R002",
        emitter=emitter,
    )

    assert captured_emitters == [emitter]

import asyncio
from decimal import Decimal

import pytest
from fastapi import HTTPException

from bank_reconciliation_agent.schemas.ledger import LedgerRow
from bank_reconciliation_agent.schemas.stream import StreamEventType
from bank_reconciliation_agent.services.live_registry import get_emitter, unregister
from bank_reconciliation_agent.services.ledger import ledger_service
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from bank_reconciliation_agent.services.task import task_service


@pytest.mark.anyio
async def test_start_live_marks_running_emits_task_progress_and_retains_finished_emitter() -> None:
    task_id = "TASK_V1_3_2_LIVE_SUCCESS"
    user_id = "demo_user"
    task_service.replace_task(
        user_id=user_id,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=4,
        total_clear_rows=4,
        auto_fixed_rows=1,
        pending_ai_rows=0,
        pending_human_rows=3,
    )
    ledger_service.replace_task_rows(
        user_id=user_id,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        rows=[
            _ledger_row(task_id, "FLOW-001", "AMOUNT_MISMATCH"),
            _ledger_row(task_id, "FLOW-002", "AMOUNT_MISMATCH"),
            _ledger_row(task_id, "FLOW-003", "BANK_UNARRIVED"),
        ],
    )

    result = await ReconciliationService().start_live(user_id=user_id, task_id=task_id)
    emitter = get_emitter(task_id)
    assert result.status == "AI_RUNNING"
    assert emitter is not None

    progress_event = await asyncio.to_thread(emitter.get, 1)

    assert progress_event.event_type == StreamEventType.TASK_PROGRESS
    assert progress_event.task_id == task_id
    assert progress_event.payload == {
        "processed": 4,
        "total": 4,
        "auto_fixed": 1,
        "pending_ai": 0,
        "pending_human": 3,
        "unresolved": 3,
        "exception_dist": {"AMOUNT_MISMATCH": 2, "BANK_UNARRIVED": 1},
    }

    terminal_event = await asyncio.to_thread(emitter.get, 1)
    assert terminal_event.event_type == StreamEventType.TASK_DONE
    assert terminal_event.payload["status"] == "COMPLETED"

    await asyncio.sleep(0)
    assert emitter.finished
    assert get_emitter(task_id) is emitter
    assert ReconciliationService().get_status(user_id=user_id, task_id=task_id).status == "COMPLETED"
    unregister(task_id)


@pytest.mark.anyio
async def test_start_live_rejects_running_task_without_replacing_emitter() -> None:
    task_id = "TASK_V1_3_2_LIVE_RUNNING"
    user_id = "demo_user"
    task_service.replace_task(
        user_id=user_id,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )
    task_service.update_status(user_id=user_id, task_id=task_id, status="AI_RUNNING")

    with pytest.raises(HTTPException) as exc_info:
        await ReconciliationService().start_live(user_id=user_id, task_id=task_id)

    assert exc_info.value.status_code == 409
    assert get_emitter(task_id) is None


@pytest.mark.anyio
async def test_start_live_retains_finished_emitter_on_background_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = "TASK_V1_3_2_LIVE_ERROR"
    user_id = "demo_user"
    task_service.replace_task(
        user_id=user_id,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )
    service = ReconciliationService()

    def raise_error(*args: object, **kwargs: object) -> None:
        raise RuntimeError("live failure")

    monkeypatch.setattr(service, "_emit_live_progress", raise_error)

    await service.start_live(user_id=user_id, task_id=task_id)
    emitter = get_emitter(task_id)
    assert emitter is not None

    terminal_event = await asyncio.to_thread(emitter.get, 1)
    assert terminal_event.event_type == StreamEventType.TASK_DONE
    assert terminal_event.payload["status"] == "FAILED"
    assert "live failure" in terminal_event.payload["error_message"]

    await asyncio.sleep(0)
    assert emitter.finished
    assert get_emitter(task_id) is emitter
    assert ReconciliationService().get_status(user_id=user_id, task_id=task_id).status == "FAILED"
    unregister(task_id)


def test_sync_start_still_marks_task_ai_running() -> None:
    task_id = "TASK_V1_3_2_SYNC_START"
    user_id = "demo_user"
    task_service.replace_task(
        user_id=user_id,
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )

    result = ReconciliationService().start(user_id=user_id, task_id=task_id)

    assert result.status == "AI_RUNNING"
    assert ReconciliationService().get_status(user_id=user_id, task_id=task_id).status == "AI_RUNNING"
    assert get_emitter(task_id) is None


def _ledger_row(task_id: str, flow_id: str, error_type: str) -> LedgerRow:
    return LedgerRow(
        id=0,
        task_id=task_id,
        flow_id=flow_id,
        error_type=error_type,
        exception_branch=None,
        bank_amount=Decimal("10.00"),
        clear_amount=Decimal("9.00"),
        discrepancy_amount=Decimal("1.00"),
        ai_audit_opinion=None,
        ai_confidence=None,
        rag_source=None,
        fallback_path=None,
        handle_status="PENDING_HUMAN",
    )

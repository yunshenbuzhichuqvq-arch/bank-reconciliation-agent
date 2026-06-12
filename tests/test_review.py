import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from langgraph.types import Command

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.services.ledger import error_ledger_table
from bank_reconciliation_agent.services.memory.long_term import LongTermMemoryService
from bank_reconciliation_agent.services.memory.short_term import ShortTermMemoryService
from bank_reconciliation_agent.services.queue import reconciliation_queue_table
from bank_reconciliation_agent.services import review as review_module
from bank_reconciliation_agent.services.review import human_review_table, review_service
from bank_reconciliation_agent.services.review_graph import get_review_graph
from bank_reconciliation_agent.services.task import reconciliation_task_table
from bank_reconciliation_agent.core.config import settings
from scripts.generate_mock_excel import generate_mvp1_mock_excel


client = TestClient(app)
DEMO_HEADERS = {"X-User-ID": "demo_user"}


def _upload_task(tmp_path: Path) -> str:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
            files={
                "bank_file": (
                    "bank_transactions.xlsx",
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    "clear_transactions.xlsx",
                    clear_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
    assert response.status_code == 200
    return response.json()["data"]["task_id"]


def _pending_item_by_branch(task_id: str, exception_branch: str) -> dict[str, object]:
    items = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=20",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"]
    return next(item for item in items if item["exception_branch"] == exception_branch)


def test_pending_review_list_fields_order_and_pagination(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)

    response = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=2",
        headers=DEMO_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["scenario_type"] == "BANK_ENTERPRISE"
    assert body["total"] == 6
    assert len(body["items"]) == 2
    assert [item["exception_branch"] for item in body["items"]] == ["BE-R002", "BE-R004"]

    first = body["items"][0]
    assert first["error_type"] == "AMOUNT_MISMATCH"
    assert first["risk_level"] == "MEDIUM"
    assert first["ai_suggestion"] == "PENDING_HUMAN"
    assert first["ai_confidence"] is not None
    assert "金额不一致" in first["ai_reason"]
    assert first["rag_sources"]
    assert first["rag_sources"][0]["source"]
    assert first["similar_historical_cases"] == 0
    assert first["historical_approve_rate"] == "0%"

    page_two = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=2&page_size=2",
        headers=DEMO_HEADERS,
    )
    assert page_two.status_code == 200
    assert len(page_two.json()["data"]["items"]) == 2


def test_approve_match_writes_review_and_updates_ledger_queue_task(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)
    pending = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=1",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"][0]

    response = client.post(
        f"/api/v1/review/{pending['queue_id']}/approve",
        headers=DEMO_HEADERS,
        json={
            "action": "APPROVED_MATCH",
            "handler_username": "reviewer_a",
            "remark": "确认平账",
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["queue_id"] == pending["queue_id"]
    assert body["current_status"] == "FIXED"
    assert body["memory_updated"] == {"short_term": False, "long_term": True}

    engine = get_engine()
    with engine.connect() as connection:
        review = connection.execute(
            select(human_review_table).where(human_review_table.c.queue_id == pending["queue_id"])
        ).mappings().one()
        ledger = connection.execute(
            select(error_ledger_table).where(
                error_ledger_table.c.user_id == "demo_user",
                error_ledger_table.c.task_id == task_id,
                error_ledger_table.c.flow_id == "F2003",
            )
        ).mappings().one()
        queue = connection.execute(
            select(reconciliation_queue_table).where(
                reconciliation_queue_table.c.id == pending["queue_id"]
            )
        ).mappings().one()
        task = connection.execute(
            select(reconciliation_task_table).where(
                reconciliation_task_table.c.user_id == "demo_user",
                reconciliation_task_table.c.task_id == task_id,
            )
        ).mappings().one()

    assert review["user_id"] == "demo_user"
    assert review["scenario_type"] == "BANK_ENTERPRISE"
    assert review["action"] == "APPROVED_MATCH"
    assert review["handler_username"] == "reviewer_a"
    assert review["remark"] == "确认平账"
    assert ledger["handle_status"] == "FIXED"
    assert ledger["handler_username"] == "reviewer_a"
    assert ledger["handle_remark"] == "确认平账"
    assert ledger["handled_at"] is not None
    assert queue["status"] == "FIXED"
    assert task["pending_human_rows"] == 5
    assert task["unresolved_rows"] == 5

    long_rows = LongTermMemoryService().recall(
        user_id="demo_user",
        error_type="AMOUNT_MISMATCH",
        keywords=["amount", "confirmed"],
    )
    assert any(
        row["flow_id"] == "F2003" and row["human_decision"] == "APPROVED_MATCH"
        for row in long_rows
    )


def test_approve_force_hold_sets_held(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)
    pending = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=1",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"][0]

    response = client.post(
        f"/api/v1/review/{pending['queue_id']}/approve",
        headers=DEMO_HEADERS,
        json={"action": "FORCE_HOLD", "handler_username": "reviewer_b"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["current_status"] == "HELD"

    with get_engine().connect() as connection:
        ledger_status = connection.execute(
            select(error_ledger_table.c.handle_status).where(
                error_ledger_table.c.user_id == "demo_user",
                error_ledger_table.c.task_id == task_id,
                error_ledger_table.c.flow_id == "F2003",
            )
        ).scalar_one()
        queue_status = connection.execute(
            select(reconciliation_queue_table.c.status).where(
                reconciliation_queue_table.c.id == pending["queue_id"]
            )
        ).scalar_one()

    assert ledger_status == "HELD"
    assert queue_status == "HELD"


def test_approve_ignores_memory_side_effect_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = _upload_task(tmp_path)
    pending = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=1",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"][0]

    def failing_memory_update(**kwargs):
        del kwargs
        raise RuntimeError("memory unavailable")

    monkeypatch.setattr(review_module.memory_manager, "update_after_decision", failing_memory_update)

    response = client.post(
        f"/api/v1/review/{pending['queue_id']}/approve",
        headers=DEMO_HEADERS,
        json={
            "action": "APPROVED_MATCH",
            "handler_username": "reviewer_a",
            "remark": "确认平账",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["memory_updated"] == {"short_term": False, "long_term": False}


def test_approve_override_deletes_short_term_without_writing_long_term(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)
    pending = _pending_item_by_branch(task_id, "BE-R004")
    short_term_service = ShortTermMemoryService()
    short_term_service.append(
        thread_id=task_id,
        queue_id=int(pending["queue_id"]),
        flow_id="F2005",
        error_type="NAME_MISMATCH",
        risk_level="LOW",
        decision="APPROVED_MATCH",
        confidence=review_module.Decimal("0.9500"),
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )

    response = client.post(
        f"/api/v1/review/{pending['queue_id']}/approve",
        headers=DEMO_HEADERS,
        json={
            "action": "FORCE_HOLD",
            "handler_username": "reviewer_override",
            "remark": "人工改为挂账",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["memory_updated"] == {"short_term": True, "long_term": False}
    recent_rows = short_term_service.recent(thread_id=task_id, limit=20)
    assert all(row["queue_id"] != pending["queue_id"] for row in recent_rows)

    long_rows = LongTermMemoryService().recall(
        user_id="demo_user",
        error_type="NAME_MISMATCH",
        keywords=["name", "override"],
        limit=20,
    )
    assert all(row["flow_id"] != "F2005" for row in long_rows)


def test_approve_non_override_keeps_short_term_and_writes_long_term(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)
    pending = _pending_item_by_branch(task_id, "BE-R002")
    short_term_service = ShortTermMemoryService()
    short_term_service.append(
        thread_id=task_id,
        queue_id=int(pending["queue_id"]),
        flow_id="F2003",
        error_type="AMOUNT_MISMATCH",
        risk_level="MEDIUM",
        decision="PENDING_HUMAN",
        confidence=review_module.Decimal("0.8800"),
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )

    response = client.post(
        f"/api/v1/review/{pending['queue_id']}/approve",
        headers=DEMO_HEADERS,
        json={
            "action": "APPROVED_MATCH",
            "handler_username": "reviewer_confirm",
            "remark": "人工确认平账",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["memory_updated"] == {"short_term": False, "long_term": True}
    recent_rows = short_term_service.recent(thread_id=task_id, limit=20)
    assert any(row["queue_id"] == pending["queue_id"] for row in recent_rows)

    long_rows = LongTermMemoryService().recall(
        user_id="demo_user",
        error_type="AMOUNT_MISMATCH",
        keywords=["amount", "confirm"],
        limit=20,
    )
    assert any(
        row["flow_id"] == "F2003" and row["human_decision"] == "APPROVED_MATCH"
        for row in long_rows
    )


def test_approve_via_checkpoint_override_matches_plain_memory_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = _upload_task(tmp_path)
    pending = _pending_item_by_branch(task_id, "BE-R004")
    short_term_service = ShortTermMemoryService()
    short_term_service.append(
        thread_id=task_id,
        queue_id=int(pending["queue_id"]),
        flow_id="F2005",
        error_type="NAME_MISMATCH",
        risk_level="LOW",
        decision="APPROVED_MATCH",
        confidence=review_module.Decimal("0.9500"),
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )

    checkpoint_path = tmp_path / "override-checkpoint.sqlite"
    monkeypatch.setattr(settings, "checkpoint_enabled", True)
    monkeypatch.setattr(settings, "checkpoint_sqlite_path", str(checkpoint_path))
    get_review_graph.cache_clear()

    response = client.post(
        f"/api/v1/review/{pending['queue_id']}/approve",
        headers=DEMO_HEADERS,
        json={
            "action": "FORCE_HOLD",
            "handler_username": "reviewer_checkpoint_override",
            "remark": "checkpoint override",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["memory_updated"] == {"short_term": True, "long_term": False}
    recent_rows = short_term_service.recent(thread_id=task_id, limit=20)
    assert all(row["queue_id"] != pending["queue_id"] for row in recent_rows)
    get_review_graph.cache_clear()


def test_approve_rejects_other_user_queue(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)
    pending = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=1",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"][0]

    with pytest.raises(HTTPException) as exc_info:
        review_service.approve(
            user_id="other_user",
            queue_id=pending["queue_id"],
            action="APPROVED_MATCH",
            handler_username="reviewer_c",
            remark=None,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "forbidden task access"


def test_approve_rejects_invalid_action(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)
    pending = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=1",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"][0]

    response = client.post(
        f"/api/v1/review/{pending['queue_id']}/approve",
        headers=DEMO_HEADERS,
        json={"action": "PENDING_HUMAN", "handler_username": "reviewer_d"},
    )

    assert response.status_code == 422


def test_approve_routes_to_plain_when_checkpoint_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = review_module.ReviewResultResponse(
        queue_id=7,
        current_status="FIXED",
        memory_updated={"short_term": False, "long_term": True},
    )

    def fake_plain(**kwargs):
        assert kwargs["queue_id"] == 7
        return expected

    def fail_checkpoint(**kwargs):
        del kwargs
        raise AssertionError("checkpoint route should not be used")

    monkeypatch.setattr(settings, "checkpoint_enabled", False)
    monkeypatch.setattr(review_service, "_approve_plain", fake_plain)
    monkeypatch.setattr(review_service, "_approve_via_checkpoint", fail_checkpoint)

    result = review_service.approve(
        user_id="demo_user",
        queue_id=7,
        action="APPROVED_MATCH",
        handler_username="reviewer_x",
        remark="ok",
    )

    assert result == expected


def test_approve_routes_to_checkpoint_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = review_module.ReviewResultResponse(
        queue_id=8,
        current_status="HELD",
        memory_updated={"short_term": False, "long_term": False},
    )

    def fail_plain(**kwargs):
        del kwargs
        raise AssertionError("plain route should not be used")

    def fake_checkpoint(**kwargs):
        assert kwargs["queue_id"] == 8
        return expected

    monkeypatch.setattr(settings, "checkpoint_enabled", True)
    monkeypatch.setattr(review_service, "_approve_plain", fail_plain)
    monkeypatch.setattr(review_service, "_approve_via_checkpoint", fake_checkpoint)

    result = review_service.approve(
        user_id="demo_user",
        queue_id=8,
        action="FORCE_HOLD",
        handler_username="reviewer_y",
        remark=None,
    )

    assert result == expected


def test_review_graph_interrupt_resume_persists_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = _upload_task(tmp_path)
    pending = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=1",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"][0]

    checkpoint_path = tmp_path / "review-checkpoint.sqlite"
    monkeypatch.setattr(settings, "checkpoint_sqlite_path", str(checkpoint_path))
    get_review_graph.cache_clear()

    graph = get_review_graph()
    config = {"configurable": {"thread_id": f"{task_id}:{pending['queue_id']}"}}
    initial_state = {
        "task_id": task_id,
        "user_id": "demo_user",
        "queue_id": pending["queue_id"],
        "handler_username": "reviewer_graph",
        "remark": "checkpoint path",
    }

    first = graph.invoke(initial_state, config)

    assert "__interrupt__" in first
    state = graph.get_state(config)
    assert state.values["task_id"] == task_id
    assert state.values["queue_id"] == pending["queue_id"]
    assert state.next == ("human_review",)
    assert state.interrupts

    with sqlite3.connect(checkpoint_path) as connection:
        assert connection.execute("select count(*) from checkpoints").fetchone()[0] >= 1

    second = graph.invoke(Command(resume="APPROVED_MATCH"), config)

    assert second["result"]["current_status"] == "FIXED"
    assert second["result"]["memory_updated"] == {"short_term": False, "long_term": True}

    with get_engine().connect() as connection:
        queue = connection.execute(
            select(reconciliation_queue_table.c.status).where(
                reconciliation_queue_table.c.id == pending["queue_id"]
            )
        ).scalar_one()

    assert queue == "FIXED"
    get_review_graph.cache_clear()


def test_approve_via_checkpoint_matches_plain_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = _upload_task(tmp_path)
    pending = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=1",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"][0]

    checkpoint_path = tmp_path / "approve-checkpoint.sqlite"
    monkeypatch.setattr(settings, "checkpoint_enabled", True)
    monkeypatch.setattr(settings, "checkpoint_sqlite_path", str(checkpoint_path))
    get_review_graph.cache_clear()

    response = client.post(
        f"/api/v1/review/{pending['queue_id']}/approve",
        headers=DEMO_HEADERS,
        json={
            "action": "APPROVED_MATCH",
            "handler_username": "reviewer_checkpoint",
            "remark": "checkpoint approve",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "queue_id": pending["queue_id"],
        "current_status": "FIXED",
        "memory_updated": {"short_term": False, "long_term": True},
    }
    get_review_graph.cache_clear()


def test_approve_via_checkpoint_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = _upload_task(tmp_path)
    pending = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=1",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"][0]

    checkpoint_path = tmp_path / "idempotent-checkpoint.sqlite"
    monkeypatch.setattr(settings, "checkpoint_enabled", True)
    monkeypatch.setattr(settings, "checkpoint_sqlite_path", str(checkpoint_path))
    get_review_graph.cache_clear()

    with get_engine().connect() as connection:
        review_count_before = connection.execute(
            select(func.count()).select_from(human_review_table)
        ).scalar_one()

    first = review_service.approve(
        user_id="demo_user",
        queue_id=pending["queue_id"],
        action="APPROVED_MATCH",
        handler_username="reviewer_once",
        remark="first pass",
    )
    second = review_service.approve(
        user_id="demo_user",
        queue_id=pending["queue_id"],
        action="APPROVED_MATCH",
        handler_username="reviewer_twice",
        remark="second pass",
    )

    assert first.current_status == "FIXED"
    assert first.memory_updated == {"short_term": False, "long_term": True}
    assert second.current_status == "FIXED"
    assert second.memory_updated == {"short_term": False, "long_term": False}

    with get_engine().connect() as connection:
        review_count = connection.execute(
            select(func.count()).select_from(human_review_table)
        ).scalar_one()
        task = connection.execute(
            select(reconciliation_task_table).where(
                reconciliation_task_table.c.user_id == "demo_user",
                reconciliation_task_table.c.task_id == task_id,
            )
        ).mappings().one()

    assert review_count == review_count_before + 1
    assert task["pending_human_rows"] == 5
    assert task["unresolved_rows"] == 5
    get_review_graph.cache_clear()


def test_pending_review_requires_user_header() -> None:
    response = client.get("/api/v1/review/pending")

    assert response.status_code == 401

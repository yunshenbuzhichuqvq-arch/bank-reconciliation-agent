import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from langgraph.types import Command

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.services.ledger import error_ledger_table
from bank_reconciliation_agent.services.queue import reconciliation_queue_table
from bank_reconciliation_agent.services import review as review_module
from bank_reconciliation_agent.services.review import human_review_table, review_service
from bank_reconciliation_agent.services.review_graph import get_review_graph
from bank_reconciliation_agent.services.task import reconciliation_task_table
from bank_reconciliation_agent.services.transactions import (
    bank_transaction_table,
    clear_transaction_table,
)
from bank_reconciliation_agent.core.config import settings
from scripts.generate_mock_excel import generate_mvp1_mock_excel
from tests.auth_helpers import demo_bearer_headers


client = TestClient(app)
DEMO_HEADERS = demo_bearer_headers()


def _upload_task(tmp_path: Path) -> str:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
            files={
                "bank_file": (
                    "mvp1_bank.xlsx",
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    "mvp1_clear.xlsx",
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

    engine = get_engine()
    with engine.connect() as connection:
        review = (
            connection.execute(
                select(human_review_table).where(
                    human_review_table.c.queue_id == pending["queue_id"]
                )
            )
            .mappings()
            .one()
        )
        ledger = (
            connection.execute(
                select(error_ledger_table).where(
                    error_ledger_table.c.user_id == "demo_user",
                    error_ledger_table.c.task_id == task_id,
                    error_ledger_table.c.flow_id == "F2003",
                )
            )
            .mappings()
            .one()
        )
        queue = (
            connection.execute(
                select(reconciliation_queue_table).where(
                    reconciliation_queue_table.c.id == pending["queue_id"]
                )
            )
            .mappings()
            .one()
        )
        task = (
            connection.execute(
                select(reconciliation_task_table).where(
                    reconciliation_task_table.c.user_id == "demo_user",
                    reconciliation_task_table.c.task_id == task_id,
                )
            )
            .mappings()
            .one()
        )

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

    with get_engine().connect() as connection:
        queue = connection.execute(
            select(reconciliation_queue_table.c.status).where(
                reconciliation_queue_table.c.id == pending["queue_id"]
            )
        ).scalar_one()

    assert queue == "FIXED"
    get_review_graph.cache_clear()


def test_approve_via_checkpoint_matches_plain_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    }
    get_review_graph.cache_clear()


def test_approve_via_checkpoint_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    assert second.current_status == "FIXED"

    with get_engine().connect() as connection:
        review_count = connection.execute(
            select(func.count()).select_from(human_review_table)
        ).scalar_one()
        task = (
            connection.execute(
                select(reconciliation_task_table).where(
                    reconciliation_task_table.c.user_id == "demo_user",
                    reconciliation_task_table.c.task_id == task_id,
                )
            )
            .mappings()
            .one()
        )

    assert review_count == review_count_before + 1
    assert task["pending_human_rows"] == 5
    assert task["unresolved_rows"] == 5
    get_review_graph.cache_clear()


def test_pending_review_requires_user_header() -> None:
    response = client.get("/api/v1/review/pending")

    assert response.status_code == 401


def test_pending_review_item_includes_new_context_fields(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)

    response = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=20",
        headers=DEMO_HEADERS,
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]

    be_r002 = next(item for item in items if item["exception_branch"] == "BE-R002")
    assert isinstance(be_r002["task_id"], str)
    assert len(be_r002["task_id"]) > 0
    assert isinstance(be_r002["flow_id"], str)
    assert len(be_r002["flow_id"]) > 0
    assert isinstance(be_r002["bank_serial_no"], str)
    assert len(be_r002["bank_serial_no"]) > 0
    assert isinstance(be_r002["clearing_serial_no"], str)
    assert len(be_r002["clearing_serial_no"]) > 0
    assert isinstance(be_r002["discrepancy_amount"], str)
    assert Decimal(be_r002["discrepancy_amount"]) != 0


def test_pending_review_amounts_are_serialized_as_strings(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)

    items = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=20",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"]

    be_r002 = next(item for item in items if item["exception_branch"] == "BE-R002")
    for field in ("bank_amount", "clear_amount", "discrepancy_amount"):
        value = be_r002[field]
        assert isinstance(value, str), f"{field} should be str, got {type(value)}"
        Decimal(value)


def test_pending_review_single_sided_null_fields(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)

    items = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=2&page_size=2",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"]

    bank_unarrived = next(item for item in items if item["exception_branch"] == "BE-R005")
    assert bank_unarrived["bank_serial_no"] is None
    assert bank_unarrived["bank_amount"] is None
    assert bank_unarrived["clearing_serial_no"] is not None
    assert bank_unarrived["clear_amount"] is not None
    assert bank_unarrived["discrepancy_amount"] is not None
    assert bank_unarrived["clear_amount"] != "0"
    assert bank_unarrived["discrepancy_amount"] != "0"

    book_unrecorded = next(item for item in items if item["exception_branch"] == "BE-R006")
    assert book_unrecorded["clearing_serial_no"] is None
    assert book_unrecorded["clear_amount"] is None
    assert book_unrecorded["bank_serial_no"] is not None
    assert book_unrecorded["bank_amount"] is not None
    assert book_unrecorded["discrepancy_amount"] is not None


def test_pending_review_pagination_and_total_unchanged(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)

    response = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=2",
        headers=DEMO_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["total"] == 6
    assert len(body["items"]) == 2
    assert [item["exception_branch"] for item in body["items"]] == ["BE-R002", "BE-R004"]

    page_two = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=2&page_size=2",
        headers=DEMO_HEADERS,
    )
    assert page_two.status_code == 200
    assert len(page_two.json()["data"]["items"]) == 2

    page_three = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=3&page_size=2",
        headers=DEMO_HEADERS,
    )
    assert page_three.status_code == 200
    assert len(page_three.json()["data"]["items"]) == 2


def test_pending_review_tenant_isolation_no_cross_user_leakage(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)

    be_r002_item = _pending_item_by_branch(task_id, "BE-R002")
    flow_id = be_r002_item["flow_id"]

    engine = get_engine()
    now_val = func.now()
    with engine.begin() as connection:
        connection.execute(
            bank_transaction_table.insert().values(
                task_id=task_id,
                user_id="other_user",
                flow_id=flow_id,
                bank_serial_no="OTHER_USER_SERIAL_NO",
                amount=Decimal("999.00"),
                trade_time=now_val,
            )
        )
        connection.execute(
            clear_transaction_table.insert().values(
                task_id=task_id,
                user_id="other_user",
                flow_id=flow_id,
                clearing_serial_no="OTHER_USER_CLEAR_SERIAL",
                amount=Decimal("888.00"),
                transaction_amount=Decimal("888.00"),
                net_amount=Decimal("888.00"),
                trade_time=now_val,
            )
        )

    items = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=20",
        headers=DEMO_HEADERS,
    ).json()["data"]["items"]

    current_item = next(item for item in items if item["exception_branch"] == "BE-R002")
    assert current_item["bank_serial_no"] != "OTHER_USER_SERIAL_NO"
    assert current_item["clearing_serial_no"] != "OTHER_USER_CLEAR_SERIAL"


def test_pending_review_bilateral_amounts_match_persisted_values(tmp_path: Path) -> None:
    task_id = _upload_task(tmp_path)

    engine = get_engine()
    with engine.connect() as connection:
        ledger = (
            connection.execute(
                select(
                    error_ledger_table.c.bank_amount,
                    error_ledger_table.c.clear_amount,
                    error_ledger_table.c.discrepancy_amount,
                ).where(
                    error_ledger_table.c.user_id == "demo_user",
                    error_ledger_table.c.task_id == task_id,
                    error_ledger_table.c.flow_id == "F2003",
                )
            )
            .mappings()
            .one()
        )

    be_r002_item = _pending_item_by_branch(task_id, "BE-R002")
    assert Decimal(be_r002_item["bank_amount"]) == ledger["bank_amount"]
    assert Decimal(be_r002_item["clear_amount"]) == ledger["clear_amount"]
    assert Decimal(be_r002_item["discrepancy_amount"]) == ledger["discrepancy_amount"]

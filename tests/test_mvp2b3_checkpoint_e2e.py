import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.services.memory.long_term import LongTermMemoryService
from bank_reconciliation_agent.services.memory.short_term import ShortTermMemoryService
from bank_reconciliation_agent.services.queue import reconciliation_queue_table
from bank_reconciliation_agent.services.review import human_review_table
from bank_reconciliation_agent.services.review_graph import get_review_graph
from bank_reconciliation_agent.services.task import reconciliation_task_table
from scripts.generate_mock_excel import (
    generate_mvp1_mock_excel,
    generate_mvp2a3_mock_excel,
)
from tests.auth_helpers import demo_bearer_headers


client = TestClient(app)
DEMO_HEADERS = demo_bearer_headers()


def _upload_task(tmp_path: Path, *, scenario_type: str) -> tuple[str, dict[str, object]]:
    if scenario_type == "BANK_CLEARING":
        bank_path, clear_path = generate_mvp2a3_mock_excel(tmp_path)
        data = {"scenario_type": "BANK_CLEARING"}
    else:
        bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
        data = None

    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
            data=data,
            files={
                "bank_file": (
                    bank_path.name,
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    clear_path.name,
                    clear_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
    assert response.status_code == 200
    body = response.json()["data"]
    return body["task_id"], body


def _pending_item_by_branch(task_id: str, exception_branch: str) -> dict[str, object]:
    response = client.get(
        f"/api/v1/review/pending?task_id={task_id}&page=1&page_size=20",
        headers=DEMO_HEADERS,
    )
    assert response.status_code == 200
    return next(item for item in response.json()["data"]["items"] if item["exception_branch"] == exception_branch)


def _task_counters(task_id: str) -> dict[str, int]:
    with get_engine().connect() as connection:
        task = connection.execute(
            select(reconciliation_task_table).where(
                reconciliation_task_table.c.user_id == "demo_user",
                reconciliation_task_table.c.task_id == task_id,
            )
        ).mappings().one()
    return {
        "pending_human_rows": task["pending_human_rows"],
        "unresolved_rows": task["unresolved_rows"],
    }


def _approve(
    queue_id: int,
    *,
    action: str,
    handler_username: str,
    remark: str,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/review/{queue_id}/approve",
        headers=DEMO_HEADERS,
        json={
            "action": action,
            "handler_username": handler_username,
            "remark": remark,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.parametrize(
    ("scenario_type", "exception_branch", "expected_upload_counts"),
    [
        (
            "BANK_ENTERPRISE",
            "BE-R002",
            {"auto_fixed_rows": 2, "pending_human_rows": 6},
        ),
        (
            "BANK_CLEARING",
            "BC-R001",
            {"auto_fixed_rows": 1, "pending_human_rows": 4},
        ),
    ],
)
def test_checkpoint_toggle_e2e_matches_plain_and_preserves_scenario_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario_type: str,
    exception_branch: str,
    expected_upload_counts: dict[str, int],
) -> None:
    monkeypatch.setattr(settings, "checkpoint_enabled", False)
    plain_task_id, plain_upload = _upload_task(tmp_path / "plain", scenario_type=scenario_type)
    assert plain_upload["auto_fixed_rows"] == expected_upload_counts["auto_fixed_rows"]
    assert plain_upload["pending_human_rows"] == expected_upload_counts["pending_human_rows"]
    plain_pending = _pending_item_by_branch(plain_task_id, exception_branch)
    plain_result = _approve(
        int(plain_pending["queue_id"]),
        action="APPROVED_MATCH",
        handler_username="plain_reviewer",
        remark=f"{scenario_type} plain approve",
    )
    plain_counters = _task_counters(plain_task_id)

    checkpoint_path = tmp_path / f"{scenario_type.lower()}-checkpoint.sqlite"
    monkeypatch.setattr(settings, "checkpoint_enabled", True)
    monkeypatch.setattr(settings, "checkpoint_sqlite_path", str(checkpoint_path))
    get_review_graph.cache_clear()
    checkpoint_task_id, checkpoint_upload = _upload_task(tmp_path / "checkpoint", scenario_type=scenario_type)
    assert checkpoint_upload["auto_fixed_rows"] == expected_upload_counts["auto_fixed_rows"]
    assert checkpoint_upload["pending_human_rows"] == expected_upload_counts["pending_human_rows"]
    checkpoint_pending = _pending_item_by_branch(checkpoint_task_id, exception_branch)
    checkpoint_result = _approve(
        int(checkpoint_pending["queue_id"]),
        action="APPROVED_MATCH",
        handler_username="checkpoint_reviewer",
        remark=f"{scenario_type} checkpoint approve",
    )
    checkpoint_counters = _task_counters(checkpoint_task_id)

    assert plain_result["current_status"] == "FIXED"
    assert checkpoint_result == plain_result | {"queue_id": checkpoint_pending["queue_id"]}
    assert plain_counters == checkpoint_counters == {"pending_human_rows": expected_upload_counts["pending_human_rows"] - 1, "unresolved_rows": expected_upload_counts["pending_human_rows"] - 1}

    with sqlite3.connect(checkpoint_path) as connection:
        assert connection.execute("select count(*) from checkpoints").fetchone()[0] >= 1
    get_review_graph.cache_clear()


@pytest.mark.parametrize("checkpoint_enabled", [False, True])
def test_memory_rollback_and_non_override_e2e_are_consistent_across_toggle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checkpoint_enabled: bool,
) -> None:
    checkpoint_path = tmp_path / "memory-checkpoint.sqlite"
    monkeypatch.setattr(settings, "checkpoint_enabled", checkpoint_enabled)
    monkeypatch.setattr(settings, "checkpoint_sqlite_path", str(checkpoint_path))
    get_review_graph.cache_clear()

    override_task_id, _ = _upload_task(tmp_path / "override", scenario_type="BANK_ENTERPRISE")
    override_pending = _pending_item_by_branch(override_task_id, "BE-R004")
    short_term_service = ShortTermMemoryService()
    short_term_service.append(
        thread_id=override_task_id,
        queue_id=int(override_pending["queue_id"]),
        flow_id="F2005",
        error_type="NAME_MISMATCH",
        risk_level="LOW",
        decision="APPROVED_MATCH",
        confidence="0.9500",
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )

    override_result = _approve(
        int(override_pending["queue_id"]),
        action="FORCE_HOLD",
        handler_username="reviewer_override",
        remark="override",
    )
    assert override_result["current_status"] == "HELD"
    assert override_result["memory_updated"] == {"short_term": True, "long_term": False}
    assert all(
        row["queue_id"] != override_pending["queue_id"]
        for row in short_term_service.recent(thread_id=override_task_id, limit=20)
    )
    assert all(
        row["flow_id"] != "F2005"
        for row in LongTermMemoryService().recall(
            user_id="demo_user",
            error_type="NAME_MISMATCH",
            keywords=["override"],
            limit=20,
        )
    )

    non_override_task_id, _ = _upload_task(tmp_path / "non-override", scenario_type="BANK_ENTERPRISE")
    non_override_pending = _pending_item_by_branch(non_override_task_id, "BE-R002")
    short_term_service.append(
        thread_id=non_override_task_id,
        queue_id=int(non_override_pending["queue_id"]),
        flow_id="F2003",
        error_type="AMOUNT_MISMATCH",
        risk_level="MEDIUM",
        decision="PENDING_HUMAN",
        confidence="0.8800",
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )

    non_override_result = _approve(
        int(non_override_pending["queue_id"]),
        action="APPROVED_MATCH",
        handler_username="reviewer_confirm",
        remark="confirm",
    )
    assert non_override_result["current_status"] == "FIXED"
    assert non_override_result["memory_updated"] == {"short_term": False, "long_term": True}
    assert any(
        row["queue_id"] == non_override_pending["queue_id"]
        for row in short_term_service.recent(thread_id=non_override_task_id, limit=20)
    )
    assert any(
        row["flow_id"] == "F2003" and row["human_decision"] == "APPROVED_MATCH"
        for row in LongTermMemoryService().recall(
            user_id="demo_user",
            error_type="AMOUNT_MISMATCH",
            keywords=["confirm"],
            limit=20,
        )
    )
    get_review_graph.cache_clear()


def test_checkpoint_approve_is_idempotent_and_does_not_duplicate_review_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint_path = tmp_path / "idempotent-checkpoint.sqlite"
    monkeypatch.setattr(settings, "checkpoint_enabled", True)
    monkeypatch.setattr(settings, "checkpoint_sqlite_path", str(checkpoint_path))
    get_review_graph.cache_clear()

    task_id, _ = _upload_task(tmp_path / "idempotent", scenario_type="BANK_ENTERPRISE")
    pending = _pending_item_by_branch(task_id, "BE-R002")

    with get_engine().connect() as connection:
        review_count_before = connection.execute(select(func.count()).select_from(human_review_table)).scalar_one()

    first = _approve(
        int(pending["queue_id"]),
        action="APPROVED_MATCH",
        handler_username="reviewer_once",
        remark="first",
    )
    second = _approve(
        int(pending["queue_id"]),
        action="APPROVED_MATCH",
        handler_username="reviewer_twice",
        remark="second",
    )

    with get_engine().connect() as connection:
        review_count_after = connection.execute(select(func.count()).select_from(human_review_table)).scalar_one()
        queue_status = connection.execute(
            select(reconciliation_queue_table.c.status).where(
                reconciliation_queue_table.c.id == int(pending["queue_id"])
            )
        ).scalar_one()

    assert first["current_status"] == "FIXED"
    assert first["memory_updated"] == {"short_term": False, "long_term": True}
    assert second["current_status"] == "FIXED"
    assert second["memory_updated"] == {"short_term": False, "long_term": False}
    assert review_count_after == review_count_before + 1
    assert queue_status == "FIXED"
    get_review_graph.cache_clear()

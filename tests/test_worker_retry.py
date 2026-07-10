from pathlib import Path

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from bank_reconciliation_agent.services.reconciliation import reconciliation_service
from bank_reconciliation_agent.services.task import TaskService, task_service


@pytest.mark.parametrize(
    "error",
    [
        RedisConnectionError("redis unavailable"),
        OperationalError("SELECT 1", {}, Exception("database unavailable")),
    ],
)
def test_transient_infrastructure_error_is_reraised_for_arq_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: Exception,
) -> None:
    task_id = f"transient-{type(error).__name__}"
    task_service.replace_task(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0,
        total_clear_rows=0,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=0,
        status="QUEUED",
    )
    bank_path = tmp_path / "bank.xlsx"
    clear_path = tmp_path / "clear.xlsx"
    bank_path.write_bytes(b"bank")
    clear_path.write_bytes(b"clear")
    monkeypatch.setattr(
        reconciliation_service,
        "_read_dataframe",
        lambda *_: (_ for _ in ()).throw(error),
    )

    with pytest.raises(type(error)):
        reconciliation_service.run_reconciliation_job(
            user_id="demo_user",
            task_id=task_id,
            scenario_type="BANK_ENTERPRISE",
            bank_path=str(bank_path),
            clear_path=str(clear_path),
        )

    task = task_service.get(user_id="demo_user", task_id=task_id)
    assert task is not None
    assert task.status == "RUNNING"


def test_business_error_marks_task_failed_without_reraising(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    task_id = "business-failure"
    task_service.replace_task(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0,
        total_clear_rows=0,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=0,
        status="QUEUED",
    )
    bank_path = tmp_path / "bank.xlsx"
    clear_path = tmp_path / "clear.xlsx"
    bank_path.write_bytes(b"bank")
    clear_path.write_bytes(b"clear")
    monkeypatch.setattr(
        reconciliation_service,
        "_read_dataframe",
        lambda *_: (_ for _ in ()).throw(ValueError("invalid business input")),
    )

    reconciliation_service.run_reconciliation_job(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        bank_path=str(bank_path),
        clear_path=str(clear_path),
    )

    task = task_service.get(user_id="demo_user", task_id=task_id)
    assert task is not None
    assert task.status == "FAILED"


# ---------------------------------------------------------------------------
# TASK-25.1 CAS methods
# ---------------------------------------------------------------------------


class TestMarkAttemptStarted:
    def test_rejects_invalid_attempt(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        with pytest.raises(ValueError):
            ts.mark_attempt_started(user_id="u1", task_id="t1", attempt=0)
        with pytest.raises(ValueError):
            ts.mark_attempt_started(user_id="u1", task_id="t1", attempt=-1)

    def test_updates_queued_to_running(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        ts.replace_task(
            user_id="u_attempt", task_id="t_queued",
            scenario_type="BANK_ENTERPRISE",
            total_bank_rows=0, total_clear_rows=0,
            auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
            status="QUEUED",
        )
        result = ts.mark_attempt_started(user_id="u_attempt", task_id="t_queued", attempt=1)
        assert result is True
        task = ts.get(user_id="u_attempt", task_id="t_queued")
        assert task is not None
        assert task.status == "RUNNING"
        assert task.job_attempt == 1

    def test_updates_running_attempt(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        ts.replace_task(
            user_id="u_attempt", task_id="t_running",
            scenario_type="BANK_ENTERPRISE",
            total_bank_rows=0, total_clear_rows=0,
            auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
            status="RUNNING",
        )
        result = ts.mark_attempt_started(user_id="u_attempt", task_id="t_running", attempt=2)
        assert result is True
        task = ts.get(user_id="u_attempt", task_id="t_running")
        assert task is not None
        assert task.job_attempt == 2

    def test_does_not_update_non_active_states(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        for status in ("UPLOADED", "COMPLETED", "FAILED"):
            tid = f"t_{status}"
            ts.replace_task(
                user_id="u_attempt", task_id=tid,
                scenario_type="BANK_ENTERPRISE",
                total_bank_rows=0, total_clear_rows=0,
                auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
                status=status,
            )
            if status == "FAILED":
                ts.mark_failed_if_active(
                    user_id="u_attempt", task_id=tid,
                    attempt=3, failure_type="OperationalError",
                    failure_summary="database operation unavailable",
                )
            result = ts.mark_attempt_started(user_id="u_attempt", task_id=tid, attempt=1)
            assert result is False

    def test_user_scoped(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        for uid in ("u1", "u2"):
            ts.replace_task(
                user_id=uid, task_id="t_shared",
                scenario_type="BANK_ENTERPRISE",
                total_bank_rows=0, total_clear_rows=0,
                auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
                status="QUEUED",
            )
        result = ts.mark_attempt_started(user_id="u1", task_id="t_shared", attempt=1)
        assert result is True
        t1 = ts.get(user_id="u1", task_id="t_shared")
        assert t1 is not None
        assert t1.job_attempt == 1
        t2 = ts.get(user_id="u2", task_id="t_shared")
        assert t2 is not None
        assert t2.job_attempt == 0


class TestMarkFailedIfActive:
    def test_first_call_sets_terminal_fields(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        ts.replace_task(
            user_id="u_fail", task_id="t_first",
            scenario_type="BANK_ENTERPRISE",
            total_bank_rows=0, total_clear_rows=0,
            auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
            status="QUEUED",
        )
        result = ts.mark_failed_if_active(
            user_id="u_fail", task_id="t_first",
            attempt=3, failure_type="RedisConnectionError",
            failure_summary="redis connection unavailable",
        )
        assert result is True
        task = ts.get(user_id="u_fail", task_id="t_first")
        assert task is not None
        assert task.status == "FAILED"
        assert task.job_attempt == 3
        assert task.retry_exhausted is True
        assert task.retry_recovered is False
        assert task.failure_type == "RedisConnectionError"
        assert task.failure_summary == "redis connection unavailable"
        assert task.failed_at is not None

    def test_repeat_call_returns_false(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        ts.replace_task(
            user_id="u_fail", task_id="t_repeat",
            scenario_type="BANK_ENTERPRISE",
            total_bank_rows=0, total_clear_rows=0,
            auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
            status="QUEUED",
        )
        first = ts.mark_failed_if_active(
            user_id="u_fail", task_id="t_repeat",
            attempt=3, failure_type="OperationalError",
            failure_summary="database operation unavailable",
        )
        assert first is True
        task_after_first = ts.get(user_id="u_fail", task_id="t_repeat")
        assert task_after_first is not None
        first_failed_at = task_after_first.failed_at

        second = ts.mark_failed_if_active(
            user_id="u_fail", task_id="t_repeat",
            attempt=3, failure_type="OperationalError",
            failure_summary="database operation unavailable",
        )
        assert second is False
        task_after_second = ts.get(user_id="u_fail", task_id="t_repeat")
        assert task_after_second is not None
        assert task_after_second.failed_at == first_failed_at
        assert task_after_second.failure_type == "OperationalError"

    def test_does_not_overwrite_non_active_states(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        for status in ("UPLOADED", "COMPLETED"):
            tid = f"t_noop_{status}"
            ts.replace_task(
                user_id="u_fail", task_id=tid,
                scenario_type="BANK_ENTERPRISE",
                total_bank_rows=0, total_clear_rows=0,
                auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
                status=status,
            )
            ts.update_status(user_id="u_fail", task_id=tid, status="AI_RUNNING")
            result = ts.mark_failed_if_active(
                user_id="u_fail", task_id=tid,
                attempt=3, failure_type="OperationalError",
                failure_summary="database operation unavailable",
            )
            assert result is False
            task = ts.get(user_id="u_fail", task_id=tid)
            assert task is not None
            assert task.status == "AI_RUNNING"

    def test_user_scoped(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        for uid in ("u1", "u2"):
            ts.replace_task(
                user_id=uid, task_id="t_shared",
                scenario_type="BANK_ENTERPRISE",
                total_bank_rows=0, total_clear_rows=0,
                auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
                status="QUEUED",
            )
        result = ts.mark_failed_if_active(
            user_id="u1", task_id="t_shared",
            attempt=3, failure_type="OperationalError",
            failure_summary="database operation unavailable",
        )
        assert result is True
        t1 = ts.get(user_id="u1", task_id="t_shared")
        assert t1 is not None
        assert t1.status == "FAILED"
        t2 = ts.get(user_id="u2", task_id="t_shared")
        assert t2 is not None
        assert t2.status == "QUEUED"

    def test_rejects_oversized_strings(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        ts.replace_task(
            user_id="u_fail", task_id="t_oversize",
            scenario_type="BANK_ENTERPRISE",
            total_bank_rows=0, total_clear_rows=0,
            auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
            status="QUEUED",
        )
        with pytest.raises(ValueError):
            ts.mark_failed_if_active(
                user_id="u_fail", task_id="t_oversize",
                attempt=3, failure_type="X" * 65,
                failure_summary="ok",
            )
        with pytest.raises(ValueError):
            ts.mark_failed_if_active(
                user_id="u_fail", task_id="t_oversize",
                attempt=3, failure_type="ok",
                failure_summary="Y" * 256,
            )


class TestMarkAttemptSucceeded:
    def test_updates_attempt_and_sets_recovered_when_attempt_gt_1(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        ts.replace_task(
            user_id="u_success", task_id="t_attempt2",
            scenario_type="BANK_ENTERPRISE",
            total_bank_rows=10, total_clear_rows=10,
            auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
            status="UPLOADED",
        )
        ts.update_status(user_id="u_success", task_id="t_attempt2", status="COMPLETED")
        result = ts.mark_attempt_succeeded(user_id="u_success", task_id="t_attempt2", attempt=2)
        assert result is True
        task = ts.get(user_id="u_success", task_id="t_attempt2")
        assert task is not None
        assert task.job_attempt == 2
        assert task.retry_recovered is True
        assert task.retry_exhausted is False

    def test_attempt_1_does_not_set_recovered(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        ts.replace_task(
            user_id="u_success", task_id="t_attempt1",
            scenario_type="BANK_ENTERPRISE",
            total_bank_rows=10, total_clear_rows=10,
            auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
            status="UPLOADED",
        )
        ts.update_status(user_id="u_success", task_id="t_attempt1", status="COMPLETED")
        result = ts.mark_attempt_succeeded(user_id="u_success", task_id="t_attempt1", attempt=1)
        assert result is True
        task = ts.get(user_id="u_success", task_id="t_attempt1")
        assert task is not None
        assert task.job_attempt == 1
        assert task.retry_recovered is False

    def test_failed_task_returns_false(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        ts.replace_task(
            user_id="u_success", task_id="t_failed",
            scenario_type="BANK_ENTERPRISE",
            total_bank_rows=0, total_clear_rows=0,
            auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
            status="QUEUED",
        )
        ts.mark_failed_if_active(
            user_id="u_success", task_id="t_failed",
            attempt=3, failure_type="OperationalError",
            failure_summary="database operation unavailable",
        )
        result = ts.mark_attempt_succeeded(user_id="u_success", task_id="t_failed", attempt=1)
        assert result is False
        task = ts.get(user_id="u_success", task_id="t_failed")
        assert task is not None
        assert task.status == "FAILED"

    def test_clears_failure_fields_on_success(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        ts.replace_task(
            user_id="u_success", task_id="t_recover",
            scenario_type="BANK_ENTERPRISE",
            total_bank_rows=10, total_clear_rows=10,
            auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
            status="UPLOADED",
        )
        result = ts.mark_attempt_succeeded(user_id="u_success", task_id="t_recover", attempt=2)
        assert result is True
        task = ts.get(user_id="u_success", task_id="t_recover")
        assert task is not None
        assert task.retry_exhausted is False
        assert task.failure_type is None
        assert task.failure_summary is None
        assert task.failed_at is None

    def test_user_scoped(self) -> None:
        ts = TaskService()
        ts._ensure_initialized()
        for uid in ("u1", "u2"):
            ts.replace_task(
                user_id=uid, task_id="t_shared",
                scenario_type="BANK_ENTERPRISE",
                total_bank_rows=10, total_clear_rows=10,
                auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
                status="UPLOADED",
            )
            ts.update_status(user_id=uid, task_id="t_shared", status="COMPLETED")
        result = ts.mark_attempt_succeeded(user_id="u1", task_id="t_shared", attempt=2)
        assert result is True
        t1 = ts.get(user_id="u1", task_id="t_shared")
        assert t1 is not None
        assert t1.retry_recovered is True
        t2 = ts.get(user_id="u2", task_id="t_shared")
        assert t2 is not None
        assert t2.retry_recovered is False

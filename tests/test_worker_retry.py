import asyncio
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


# ---------------------------------------------------------------------------
# TASK-25.2 Direct function boundary tests
# ---------------------------------------------------------------------------


def test_worker_function_throws_retry_on_attempt_1(monkeypatch) -> None:
    from arq import Retry
    from bank_reconciliation_agent.worker import run_reconciliation_job as wfn

    task_service.replace_task(
        user_id="u_retry", task_id="t_retry_1",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0, total_clear_rows=0,
        auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
        status="QUEUED",
    )

    def mock_service(**kwargs: object) -> None:
        raise RedisConnectionError("redis gone")

    monkeypatch.setattr(
        reconciliation_service, "run_reconciliation_job", mock_service
    )

    with pytest.raises(Retry):
        asyncio.run(wfn({"job_try": 1}, user_id="u_retry", task_id="t_retry_1",
                        scenario_type="BANK_ENTERPRISE", bank_path="b", clear_path="c"))


def test_worker_function_throws_retry_on_attempt_2(monkeypatch) -> None:
    from arq import Retry
    from bank_reconciliation_agent.worker import run_reconciliation_job as wfn

    task_service.replace_task(
        user_id="u_retry", task_id="t_retry_2",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0, total_clear_rows=0,
        auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
        status="QUEUED",
    )

    def mock_service(**kwargs: object) -> None:
        raise RedisConnectionError("redis gone")

    monkeypatch.setattr(
        reconciliation_service, "run_reconciliation_job", mock_service
    )
    # On attempt 1, max_tries=3: 1 < 3 → Retry
    with pytest.raises(Retry):
        asyncio.run(wfn({"job_try": 2}, user_id="u_retry", task_id="t_retry_2",
                        scenario_type="BANK_ENTERPRISE", bank_path="b", clear_path="c"))


def test_worker_function_reraises_on_attempt_3(monkeypatch) -> None:
    from bank_reconciliation_agent.worker import run_reconciliation_job as wfn

    task_service.replace_task(
        user_id="u_retry", task_id="t_retry_3",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0, total_clear_rows=0,
        auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
        status="QUEUED",
    )

    def mock_service(**kwargs: object) -> None:
        raise OperationalError("db gone", {}, Exception("inner"))

    monkeypatch.setattr(
        reconciliation_service, "run_reconciliation_job", mock_service
    )
    with pytest.raises(OperationalError):
        asyncio.run(wfn({"job_try": 3}, user_id="u_retry", task_id="t_retry_3",
                        scenario_type="BANK_ENTERPRISE", bank_path="b", clear_path="c"))

    task = task_service.get(user_id="u_retry", task_id="t_retry_3")
    assert task is not None
    assert task.status == "FAILED"
    assert task.job_attempt == 3
    assert task.retry_exhausted is True
    assert task.failure_type == "OperationalError"


def test_worker_function_terminal_cas_noop_still_reraises(monkeypatch) -> None:
    from bank_reconciliation_agent.worker import run_reconciliation_job as wfn

    task_service.replace_task(
        user_id="u_retry", task_id="t_noop",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0, total_clear_rows=0,
        auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
        status="QUEUED",
    )
    task_service.mark_failed_if_active(
        user_id="u_retry", task_id="t_noop",
        attempt=3, failure_type="OperationalError",
        failure_summary="database operation unavailable",
    )

    service_called = False

    def mock_service(**kwargs: object) -> None:
        nonlocal service_called
        service_called = True

    monkeypatch.setattr(
        reconciliation_service, "run_reconciliation_job", mock_service
    )
    asyncio.run(wfn({"job_try": 3}, user_id="u_retry", task_id="t_noop",
                    scenario_type="BANK_ENTERPRISE", bank_path="b", clear_path="c"))

    assert service_called is False
    task = task_service.get(user_id="u_retry", task_id="t_noop")
    assert task is not None
    assert task.status == "FAILED"
    assert task.failure_type == "OperationalError"


def test_worker_function_business_error_not_converted_to_retry(monkeypatch) -> None:
    from bank_reconciliation_agent.worker import run_reconciliation_job as wfn

    task_service.replace_task(
        user_id="u_biz", task_id="t_biz",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0, total_clear_rows=0,
        auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
        status="QUEUED",
    )

    def mock_service(**kwargs: object) -> None:
        raise ValueError("business logic error")

    monkeypatch.setattr(
        reconciliation_service, "run_reconciliation_job", mock_service
    )
    with pytest.raises(ValueError):
        asyncio.run(wfn({"job_try": 1}, user_id="u_biz", task_id="t_biz",
                        scenario_type="BANK_ENTERPRISE", bank_path="b", clear_path="c"))


# ---------------------------------------------------------------------------
# TASK-25.2 Real Worker + fakeredis tests
# ---------------------------------------------------------------------------


def _make_fakeredis_pool():
    from arq.connections import ArqRedis
    from fakeredis.aioredis import FakeRedis

    fake = FakeRedis(decode_responses=False, version=(7,))
    return ArqRedis(connection_pool=fake.connection_pool)


def _run_worker_and_get_task(
    fake_pool,
    user_id: str,
    task_id: str,
    *,
    fail_on: set[int],
    error_cls: type[Exception],
    max_tries: int = 3,
) -> tuple[int, object, bool]:
    """Returns (call_count, final_task, job_failed).

    job_failed is True when the ARQ job itself failed (exhaustion).
    """
    from unittest.mock import patch

    from arq.worker import FailedJobs, Worker
    from bank_reconciliation_agent.worker import run_reconciliation_job as real_worker_fn
    from bank_reconciliation_agent.services.reconciliation import reconciliation_service

    call_count = [0]
    original = reconciliation_service.run_reconciliation_job

    def mock_service(**kwargs: object) -> None:
        call_count[0] += 1
        if call_count[0] in fail_on:
            if error_cls is OperationalError:
                raise OperationalError("stmt", {}, Exception("mock db error"))
            raise error_cls(f"mock {error_cls.__name__} on attempt {call_count[0]}")
        task_service.update_status(
            user_id=kwargs["user_id"], task_id=kwargs["task_id"], status="UPLOADED"
        )

    reconciliation_service.run_reconciliation_job = mock_service

    job = None
    job_failed = False

    async def _run() -> None:
        nonlocal job, job_failed
        job = await fake_pool.enqueue_job(
            "run_reconciliation_job",
            user_id=user_id,
            task_id=task_id,
            scenario_type="BANK_ENTERPRISE",
            bank_path="/fake/bank.xlsx",
            clear_path="/fake/clear.xlsx",
        )
        with patch("arq.worker.log_redis_info"):
            worker = Worker(
                functions=[real_worker_fn],
                redis_pool=fake_pool,
                poll_delay=0.01,
                max_tries=max_tries,
                job_timeout=10,
                burst=True,
            )
            try:
                await worker.run_check(max_burst_jobs=5)
            except FailedJobs:
                job_failed = True
            except Exception:
                raise
            await worker.close()

    asyncio.run(_run())

    try:
        reconciliation_service.run_reconciliation_job = original
    except Exception:
        pass

    final_task = task_service.get(user_id=user_id, task_id=task_id)
    return call_count[0], final_task, job_failed


def test_real_worker_redis_error_recovers_on_attempt_2(monkeypatch) -> None:
    task_service.replace_task(
        user_id="u_rw", task_id="t_redis_rec",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0, total_clear_rows=0,
        auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
        status="QUEUED",
    )
    fake_pool = _make_fakeredis_pool()
    count, task, job_failed = _run_worker_and_get_task(
        fake_pool, "u_rw", "t_redis_rec",
        fail_on={1}, error_cls=RedisConnectionError,
    )
    assert job_failed is False
    assert count == 2
    assert task is not None
    assert task.status == "UPLOADED"
    assert task.job_attempt == 2
    assert task.retry_recovered is True
    assert task.retry_exhausted is False


def test_real_worker_op_error_recovers_on_attempt_3(monkeypatch) -> None:
    task_service.replace_task(
        user_id="u_rw", task_id="t_db_rec",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0, total_clear_rows=0,
        auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
        status="QUEUED",
    )
    fake_pool = _make_fakeredis_pool()
    count, task, job_failed = _run_worker_and_get_task(
        fake_pool, "u_rw", "t_db_rec",
        fail_on={1, 2}, error_cls=OperationalError,
    )
    assert job_failed is False
    assert count == 3
    assert task is not None
    assert task.status == "UPLOADED"
    assert task.job_attempt == 3
    assert task.retry_recovered is True
    assert task.retry_exhausted is False


def test_real_worker_exhaustion_on_3rd_attempt(monkeypatch) -> None:
    task_service.replace_task(
        user_id="u_rw", task_id="t_exhaust",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0, total_clear_rows=0,
        auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
        status="QUEUED",
    )
    fake_pool = _make_fakeredis_pool()
    count, task, job_failed = _run_worker_and_get_task(
        fake_pool, "u_rw", "t_exhaust",
        fail_on={1, 2, 3}, error_cls=RedisConnectionError,
    )
    assert job_failed is True
    assert count == 3
    assert task is not None
    assert task.status == "FAILED"
    assert task.job_attempt == 3
    assert task.retry_exhausted is True
    assert task.retry_recovered is False
    assert task.failure_type == "RedisConnectionError"
    assert task.failure_summary == "redis connection unavailable"


def test_real_worker_business_error_not_retried(monkeypatch) -> None:
    from arq.worker import Worker
    from bank_reconciliation_agent.worker import run_reconciliation_job as real_worker_fn
    from bank_reconciliation_agent.services.reconciliation import reconciliation_service

    task_service.replace_task(
        user_id="u_rw", task_id="t_biz",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0, total_clear_rows=0,
        auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
        status="QUEUED",
    )
    fake_pool = _make_fakeredis_pool()
    call_count = [0]
    original = reconciliation_service.run_reconciliation_job

    def mock_service(**kwargs: object) -> None:
        call_count[0] += 1
        task_service.update_status(
            user_id=kwargs["user_id"], task_id=kwargs["task_id"], status="FAILED"
        )

    reconciliation_service.run_reconciliation_job = mock_service

    async def _run() -> None:
        await fake_pool.enqueue_job(
            "run_reconciliation_job",
            user_id="u_rw", task_id="t_biz",
            scenario_type="BANK_ENTERPRISE",
            bank_path="/fake/bank.xlsx", clear_path="/fake/clear.xlsx",
        )
        from unittest.mock import patch

        with patch("arq.worker.log_redis_info"):
            worker = Worker(
                functions=[real_worker_fn], redis_pool=fake_pool,
                poll_delay=0.01, max_tries=3, job_timeout=10,
                burst=True,
            )
            await worker.run_check(max_burst_jobs=5)
            await worker.close()

    try:
        asyncio.run(_run())
    finally:
        reconciliation_service.run_reconciliation_job = original

    assert call_count[0] == 1
    task = task_service.get(user_id="u_rw", task_id="t_biz")
    assert task is not None
    assert task.status == "FAILED"


def test_worker_function_attempt_1_retryable_attempt_2_business_failure_no_recovered(
    monkeypatch
) -> None:
    task_service.replace_task(
        user_id="u_rw", task_id="t_retry_biz",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=0, total_clear_rows=0,
        auto_fixed_rows=0, pending_ai_rows=0, pending_human_rows=0,
        status="QUEUED",
    )
    fake_pool = _make_fakeredis_pool()

    from unittest.mock import patch
    from arq.worker import Worker
    from bank_reconciliation_agent.worker import run_reconciliation_job as real_worker_fn
    from bank_reconciliation_agent.services.reconciliation import reconciliation_service

    call_count = [0]
    original = reconciliation_service.run_reconciliation_job

    def mock_service(**kwargs: object) -> None:
        call_count[0] += 1
        if call_count[0] == 1:
            raise RedisConnectionError("redis gone")
        # attempt 2: business failure, service marks FAILED and returns
        task_service.update_status(
            user_id=kwargs["user_id"], task_id=kwargs["task_id"], status="FAILED"
        )

    reconciliation_service.run_reconciliation_job = mock_service

    async def _run() -> None:
        await fake_pool.enqueue_job(
            "run_reconciliation_job",
            user_id="u_rw", task_id="t_retry_biz",
            scenario_type="BANK_ENTERPRISE",
            bank_path="/fake/bank.xlsx", clear_path="/fake/clear.xlsx",
        )
        with patch("arq.worker.log_redis_info"):
            worker = Worker(
                functions=[real_worker_fn], redis_pool=fake_pool,
                poll_delay=0.01, max_tries=3, job_timeout=10,
                burst=True,
            )
            await worker.run_check(max_burst_jobs=5)
            await worker.close()

    asyncio.run(_run())

    try:
        reconciliation_service.run_reconciliation_job = original
    except Exception:
        pass

    assert call_count[0] == 2
    task = task_service.get(user_id="u_rw", task_id="t_retry_biz")
    assert task is not None
    assert task.status == "FAILED"
    assert task.retry_recovered is False


# ---------------------------------------------------------------------------
# TASK-26.3 LLM failure ARQ boundary
# ---------------------------------------------------------------------------


def test_llm_item_failure_stays_in_job_without_arq_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from scripts.generate_mock_excel import generate_mvp1_mock_excel

    from bank_reconciliation_agent.core.llm.provider import LLMCallError, LLMResult
    from bank_reconciliation_agent.services.workflow import runner as workflow_module
    from bank_reconciliation_agent.worker import run_reconciliation_job as wfn

    class FailingProvider:
        model = "failing"

        def complete(
            self,
            messages,
            *,
            temperature: float = 0.0,
            response_format: str = "json_object",
            response_validator=None,
        ) -> LLMResult:
            del messages, temperature, response_format, response_validator
            raise LLMCallError(
                failure_type="provider_5xx",
                retryable=False,
                sanitized_reason="upstream down",
            )

    monkeypatch.setattr(workflow_module, "get_llm_provider", FailingProvider)

    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    task_id = "TASK-LLM-BOUNDARY"
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

    asyncio.run(
        wfn(
            {"job_try": 1},
            user_id="demo_user",
            task_id=task_id,
            scenario_type="BANK_ENTERPRISE",
            bank_path=str(bank_path),
            clear_path=str(clear_path),
        )
    )

    from bank_reconciliation_agent.schemas.ledger import LedgerQuery
    from bank_reconciliation_agent.services.ledger import LedgerService

    task = task_service.get(user_id="demo_user", task_id=task_id)
    assert task is not None
    # LLM failures are absorbed as business results; the job is not an ARQ retry.
    assert task.status != "FAILED"
    assert task.job_attempt == 1
    assert task.retry_exhausted is False
    assert task.retry_recovered is False

    page = LedgerService().list(
        user_id="demo_user",
        query=LedgerQuery(task_id=task_id, page=1, page_size=10_000),
    )
    assert page.items
    assert all(row.handle_status == "PENDING_HUMAN" for row in page.items)

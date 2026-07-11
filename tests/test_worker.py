import asyncio

import pytest

from bank_reconciliation_agent import worker
from bank_reconciliation_agent.core.config import settings


def test_worker_settings_register_reconciliation_job() -> None:
    assert worker.WorkerSettings.functions == [worker.run_reconciliation_job]
    assert worker.WorkerSettings.max_tries == settings.arq_job_max_attempts
    assert worker.WorkerSettings.job_timeout == settings.arq_job_timeout_seconds
    assert worker.WorkerSettings.redis_settings.host == "127.0.0.1"
    assert worker.WorkerSettings.redis_settings.port == 6379
    assert worker.WorkerSettings.redis_settings.database == 0
    assert worker.WorkerSettings.on_startup is worker.on_startup
    assert worker.WorkerSettings.on_shutdown is worker.on_shutdown


def test_run_reconciliation_job_delegates_to_service(monkeypatch) -> None:
    received: dict[str, str] = {}

    def run_job(**kwargs: str) -> None:
        received.update(kwargs)

    monkeypatch.setattr(
        worker.reconciliation_service,
        "run_reconciliation_job",
        run_job,
        raising=False,
    )

    asyncio.run(
        worker.run_reconciliation_job(
            {},
            user_id="user-1",
            task_id="task-1",
            scenario_type="BANK_ENTERPRISE",
            bank_path="/tmp/bank.xlsx",
            clear_path="/tmp/clear.xlsx",
        )
    )

    assert received == {
        "user_id": "user-1",
        "task_id": "task-1",
        "scenario_type": "BANK_ENTERPRISE",
        "bank_path": "/tmp/bank.xlsx",
        "clear_path": "/tmp/clear.xlsx",
    }


@pytest.mark.parametrize("bad_job_try", [True, False, "1", 0, -1])
def test_run_reconciliation_job_rejects_invalid_job_try(
    monkeypatch, bad_job_try: object
) -> None:
    called = False

    def run_job(**kwargs: str) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        worker.reconciliation_service,
        "run_reconciliation_job",
        run_job,
        raising=False,
    )

    with pytest.raises(ValueError):
        asyncio.run(
            worker.run_reconciliation_job(
                {"job_try": bad_job_try},
                user_id="user-1",
                task_id="task-1",
                scenario_type="BANK_ENTERPRISE",
                bank_path="/tmp/bank.xlsx",
                clear_path="/tmp/clear.xlsx",
            )
        )

    assert called is False


def test_run_reconciliation_job_rejects_job_try_over_max(monkeypatch) -> None:
    called = False

    def run_job(**kwargs: str) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        worker.reconciliation_service,
        "run_reconciliation_job",
        run_job,
        raising=False,
    )
    monkeypatch.setattr(worker.task_service, "mark_attempt_started", lambda **_: True)

    with pytest.raises(RuntimeError):
        asyncio.run(
            worker.run_reconciliation_job(
                {"job_try": settings.arq_job_max_attempts + 1},
                user_id="user-1",
                task_id="task-1",
                scenario_type="BANK_ENTERPRISE",
                bank_path="/tmp/bank.xlsx",
                clear_path="/tmp/clear.xlsx",
            )
        )

    assert called is False

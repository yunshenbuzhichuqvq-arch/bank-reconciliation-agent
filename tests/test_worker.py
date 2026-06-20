import asyncio

from bank_reconciliation_agent import worker


def test_worker_settings_register_reconciliation_job() -> None:
    assert worker.WorkerSettings.functions == [worker.run_reconciliation_job]
    assert worker.WorkerSettings.max_tries == 3
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

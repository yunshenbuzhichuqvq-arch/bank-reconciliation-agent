from pathlib import Path

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from bank_reconciliation_agent.services.reconciliation import reconciliation_service
from bank_reconciliation_agent.services.task import task_service


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

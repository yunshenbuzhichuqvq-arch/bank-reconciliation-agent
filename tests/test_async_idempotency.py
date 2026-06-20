import asyncio
from pathlib import Path

from arq.connections import ArqRedis
from fastapi import HTTPException
import pandas as pd
from starlette.datastructures import UploadFile

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.services.reconciliation import reconciliation_service
from bank_reconciliation_agent.services.task import task_service
from bank_reconciliation_agent.worker import run_reconciliation_job
from scripts.generate_mock_excel import generate_mvp1_mock_excel


async def _upload(bank_path: Path, clear_path: Path, *, force: bool = False):
    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        return await reconciliation_service.upload_async(
            user_id="demo_user",
            scenario_type="BANK_ENTERPRISE",
            bank_file=UploadFile(filename="bank.xlsx", file=bank_file),
            clear_file=UploadFile(filename="clear.xlsx", file=clear_file),
            force=force,
        )


def _generate_unique_excel(tmp_path: Path) -> tuple[Path, Path]:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    bank_df = pd.read_excel(bank_path)
    bank_df.loc[0, "remark"] = tmp_path.name
    bank_df.to_excel(bank_path, index=False)
    return bank_path, clear_path


def test_duplicate_queued_upload_is_not_enqueued_twice(
    tmp_path: Path,
    monkeypatch,
    fake_arq_redis: ArqRedis,
) -> None:
    async def run() -> None:
        bank_path, clear_path = _generate_unique_excel(tmp_path)
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

        first = await _upload(bank_path, clear_path)
        second = await _upload(bank_path, clear_path)

        assert second.task_id == first.task_id
        assert second.status == "QUEUED"
        assert await fake_arq_redis.zcard("arq:queue") == 1

    asyncio.run(run())


def test_terminal_task_requires_force_to_enqueue_again(
    tmp_path: Path,
    monkeypatch,
    fake_arq_redis: ArqRedis,
) -> None:
    async def run() -> None:
        bank_path, clear_path = _generate_unique_excel(tmp_path)
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
        queued = await _upload(bank_path, clear_path)
        upload_dir = Path(settings.upload_dir)
        job_kwargs = {
            "user_id": "demo_user",
            "task_id": queued.task_id,
            "scenario_type": "BANK_ENTERPRISE",
            "bank_path": str(upload_dir / f"{queued.task_id}_bank.xlsx"),
            "clear_path": str(upload_dir / f"{queued.task_id}_clear.xlsx"),
        }
        await run_reconciliation_job({}, **job_kwargs)

        existing = await _upload(bank_path, clear_path)
        assert existing.status == "UPLOADED"
        assert await fake_arq_redis.zcard("arq:queue") == 1

        forced = await _upload(bank_path, clear_path, force=True)
        assert forced.status == "QUEUED"
        assert await fake_arq_redis.zcard("arq:queue") == 2

    asyncio.run(run())


def test_running_task_rejects_force_upload(
    tmp_path: Path,
    monkeypatch,
    fake_arq_redis: ArqRedis,
) -> None:
    async def run() -> None:
        bank_path, clear_path = _generate_unique_excel(tmp_path)
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
        queued = await _upload(bank_path, clear_path)
        task_service.update_status(user_id="demo_user", task_id=queued.task_id, status="RUNNING")

        try:
            await _upload(bank_path, clear_path, force=True)
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("RUNNING task force upload must return 409")

    asyncio.run(run())


def test_worker_skips_task_that_is_already_terminal(tmp_path: Path, monkeypatch) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    task_id = "TASK_TERMINAL_SKIP"
    task_service.replace_task(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=1,
        pending_ai_rows=0,
        pending_human_rows=0,
    )
    called = False

    def fail_if_called(**kwargs) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(reconciliation_service, "_execute_reconciliation", fail_if_called)

    reconciliation_service.run_reconciliation_job(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        bank_path=str(bank_path),
        clear_path=str(clear_path),
    )

    assert called is False
    task = task_service.get(user_id="demo_user", task_id=task_id)
    assert task is not None
    assert task.status == "UPLOADED"

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from arq.connections import ArqRedis
from starlette.datastructures import UploadFile

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.schemas.ledger import LedgerQuery
from bank_reconciliation_agent.services.ledger import ledger_service
from bank_reconciliation_agent.services.queue import queue_service
from bank_reconciliation_agent.services.reconciliation import reconciliation_service
from bank_reconciliation_agent.services.task import task_service, reconciliation_task_table
from bank_reconciliation_agent.services.transactions import transaction_service
from bank_reconciliation_agent.worker import run_reconciliation_job
from scripts.generate_mock_excel import generate_mvp1_mock_excel


def _make_unique_excel(tmp_path: Path, marker: str) -> tuple[Path, Path]:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    bank_df = pd.read_excel(bank_path)
    bank_df.loc[0, "remark"] = marker
    bank_df.to_excel(bank_path, index=False)
    return bank_path, clear_path


def test_worker_completes_queued_reconciliation_with_sync_equivalent_results(
    tmp_path: Path,
    monkeypatch,
    fake_arq_redis: ArqRedis,
) -> None:
    async def run() -> None:
        bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

        with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
            sync_result = await reconciliation_service.upload(
                user_id="demo_user",
                bank_file=UploadFile(filename="bank.xlsx", file=bank_file),
                clear_file=UploadFile(filename="clear.xlsx", file=clear_file),
            )

        with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
            queued_result = await reconciliation_service.upload_async(
                user_id="demo_user",
                scenario_type="BANK_ENTERPRISE",
                bank_file=UploadFile(filename="bank.xlsx", file=bank_file),
                clear_file=UploadFile(filename="clear.xlsx", file=clear_file),
                force=True,
            )

        assert queued_result.task_id == sync_result.task_id
        assert queued_result.status == "QUEUED"

        upload_dir = Path(settings.upload_dir)
        await run_reconciliation_job(
            {},
            user_id="demo_user",
            task_id=queued_result.task_id,
            scenario_type="BANK_ENTERPRISE",
            bank_path=str(upload_dir / f"{queued_result.task_id}_bank.xlsx"),
            clear_path=str(upload_dir / f"{queued_result.task_id}_clear.xlsx"),
        )

        task = task_service.get(user_id="demo_user", task_id=queued_result.task_id)
        assert task is not None
        assert task.status == "UPLOADED"
        assert task.job_attempt == 1
        assert task.retry_recovered is False
        assert task.total_bank_rows == sync_result.total_bank_rows
        assert task.total_clear_rows == sync_result.total_clear_rows
        assert task.auto_fixed_rows == sync_result.auto_fixed_rows
        assert task.pending_ai_rows == sync_result.pending_ai_rows
        assert task.pending_human_rows == sync_result.pending_human_rows
        assert transaction_service.count_bank_rows(
            user_id="demo_user", task_id=queued_result.task_id
        ) == sync_result.total_bank_rows
        assert queue_service.count_rows(
            user_id="demo_user", task_id=queued_result.task_id
        ) == sync_result.pending_human_rows
        assert ledger_service.list(
            user_id="demo_user", query=LedgerQuery(task_id=queued_result.task_id)
        ).total == sync_result.pending_human_rows

    asyncio.run(run())


def test_force_reattempt_failed_task_preserves_force_count_and_clears_recovery(
    tmp_path: Path,
    monkeypatch,
    fake_arq_redis: ArqRedis,
) -> None:
    async def run() -> None:
        bank_path, clear_path = _make_unique_excel(tmp_path, "force_test_1")
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

        with bank_path.open("rb") as bf, clear_path.open("rb") as cf:
            first = await reconciliation_service.upload_async(
                user_id="demo_user",
                scenario_type="BANK_ENTERPRISE",
                bank_file=UploadFile(filename="bank.xlsx", file=bf),
                clear_file=UploadFile(filename="clear.xlsx", file=cf),
            )
        task_id = first.task_id

        task_service.update_status(user_id="demo_user", task_id=task_id, status="FAILED")
        # Simulate exhausted facts
        from bank_reconciliation_agent.db.session import get_engine
        from sqlalchemy import update

        with get_engine().begin() as conn:
            conn.execute(
                update(reconciliation_task_table)
                .where(
                    reconciliation_task_table.c.user_id == "demo_user",
                    reconciliation_task_table.c.task_id == task_id,
                )
                .values(
                    job_attempt=3,
                    retry_exhausted=True,
                    retry_recovered=False,
                    failure_type="OperationalError",
                    failure_summary="database operation unavailable",
                    failed_at=datetime.now(timezone.utc),
                    force_requeue_count=1,
                )
            )

        with bank_path.open("rb") as bf, clear_path.open("rb") as cf:
            forced = await reconciliation_service.upload_async(
                user_id="demo_user",
                scenario_type="BANK_ENTERPRISE",
                bank_file=UploadFile(filename="bank.xlsx", file=bf),
                clear_file=UploadFile(filename="clear.xlsx", file=cf),
                force=True,
            )
        assert forced.task_id == task_id
        assert forced.status == "QUEUED"

        task = task_service.get(user_id="demo_user", task_id=task_id)
        assert task is not None
        assert task.status == "QUEUED"
        assert task.job_attempt == 0
        assert task.retry_recovered is False
        assert task.retry_exhausted is False
        assert task.failure_type is None
        assert task.failure_summary is None
        assert task.failed_at is None
        assert task.force_requeue_count == 2

    asyncio.run(run())


def test_force_reattempt_twice_accumulates_force_count(
    tmp_path: Path,
    monkeypatch,
    fake_arq_redis: ArqRedis,
) -> None:
    async def run() -> None:
        bank_path, clear_path = _make_unique_excel(tmp_path, "force_test_2")
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

        with bank_path.open("rb") as bf, clear_path.open("rb") as cf:
            first = await reconciliation_service.upload_async(
                user_id="demo_user",
                scenario_type="BANK_ENTERPRISE",
                bank_file=UploadFile(filename="bank.xlsx", file=bf),
                clear_file=UploadFile(filename="clear.xlsx", file=cf),
            )
        task_id = first.task_id

        for expected_count in (1, 2, 3):
            task_service.update_status(
                user_id="demo_user", task_id=task_id, status="FAILED"
            )
            with bank_path.open("rb") as bf, clear_path.open("rb") as cf:
                await reconciliation_service.upload_async(
                    user_id="demo_user",
                    scenario_type="BANK_ENTERPRISE",
                    bank_file=UploadFile(filename="bank.xlsx", file=bf),
                    clear_file=UploadFile(filename="clear.xlsx", file=cf),
                    force=True,
                )
            task = task_service.get(user_id="demo_user", task_id=task_id)
            assert task is not None
            assert task.force_requeue_count == expected_count

    asyncio.run(run())


def test_running_force_returns_409_and_noop(
    tmp_path: Path,
    monkeypatch,
    fake_arq_redis: ArqRedis,
) -> None:
    async def run() -> None:
        bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

        with bank_path.open("rb") as bf, clear_path.open("rb") as cf:
            first = await reconciliation_service.upload_async(
                user_id="demo_user",
                scenario_type="BANK_ENTERPRISE",
                bank_file=UploadFile(filename="bank.xlsx", file=bf),
                clear_file=UploadFile(filename="clear.xlsx", file=cf),
            )
        task_id = first.task_id
        task_service.update_status(
            user_id="demo_user", task_id=task_id, status="RUNNING"
        )

        from bank_reconciliation_agent.db.session import get_engine
        from sqlalchemy import update

        with get_engine().begin() as conn:
            conn.execute(
                update(reconciliation_task_table)
                .where(
                    reconciliation_task_table.c.user_id == "demo_user",
                    reconciliation_task_table.c.task_id == task_id,
                )
                .values(job_attempt=2, force_requeue_count=0)
            )

        with bank_path.open("rb") as bf, clear_path.open("rb") as cf:
            try:
                await reconciliation_service.upload_async(
                    user_id="demo_user",
                    scenario_type="BANK_ENTERPRISE",
                    bank_file=UploadFile(filename="bank.xlsx", file=bf),
                    clear_file=UploadFile(filename="clear.xlsx", file=cf),
                    force=True,
                )
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 409

        task = task_service.get(user_id="demo_user", task_id=task_id)
        assert task is not None
        assert task.status == "RUNNING"
        assert task.job_attempt == 2
        assert task.force_requeue_count == 0

    asyncio.run(run())

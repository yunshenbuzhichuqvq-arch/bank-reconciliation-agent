import asyncio
from pathlib import Path

from arq.connections import ArqRedis
from starlette.datastructures import UploadFile

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.schemas.ledger import LedgerQuery
from bank_reconciliation_agent.services.ledger import ledger_service
from bank_reconciliation_agent.services.queue import queue_service
from bank_reconciliation_agent.services.reconciliation import reconciliation_service
from bank_reconciliation_agent.services.task import task_service
from bank_reconciliation_agent.services.transactions import transaction_service
from bank_reconciliation_agent.worker import run_reconciliation_job
from scripts.generate_mock_excel import generate_mvp1_mock_excel


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

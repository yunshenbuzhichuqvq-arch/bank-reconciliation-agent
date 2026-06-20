from pathlib import Path

import pandas as pd
from arq.connections import ArqRedis
from fastapi.testclient import TestClient

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.services.task import task_service
from scripts.generate_mock_excel import generate_mvp1_mock_excel


client = TestClient(app)
DEMO_HEADERS = {"X-User-ID": "demo_user"}


def _post_upload_async(bank_path: Path, clear_path: Path, *, headers: dict[str, str]):
    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        return client.post(
            "/api/v1/reconcile/upload-async",
            headers=headers,
            files={
                "bank_file": ("bank.xlsx", bank_file),
                "clear_file": ("clear.xlsx", clear_file),
            },
        )


def test_upload_async_returns_503_when_queue_is_disabled(tmp_path: Path, monkeypatch) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    monkeypatch.setattr(settings, "async_queue_enabled", False)

    response = _post_upload_async(bank_path, clear_path, headers=DEMO_HEADERS)

    assert response.status_code == 503


def test_upload_async_queues_task_and_persists_files(
    tmp_path: Path,
    monkeypatch,
    fake_arq_redis: ArqRedis,
) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    bank_df = pd.read_excel(bank_path)
    bank_df.loc[0, "remark"] = tmp_path.name
    bank_df.to_excel(bank_path, index=False)
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "async_queue_enabled", True)
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))

    response = _post_upload_async(bank_path, clear_path, headers=DEMO_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "QUEUED"
    assert (upload_dir / f"{data['task_id']}_bank.xlsx").is_file()
    assert (upload_dir / f"{data['task_id']}_clear.xlsx").is_file()
    task = task_service.get(user_id="demo_user", task_id=data["task_id"])
    assert task is not None
    assert task.status == "QUEUED"


def test_upload_async_enforces_authentication(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)

    missing = _post_upload_async(bank_path, clear_path, headers={})
    invalid = _post_upload_async(bank_path, clear_path, headers={"X-User-ID": "other_user"})

    assert missing.status_code == 401
    assert invalid.status_code == 403

from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from bank_reconciliation_agent.main import app
from scripts.generate_mock_excel import generate_mock_excel


client = TestClient(app)


def test_upload_reconciliation_files_returns_excel_row_counts(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mock_excel(tmp_path)

    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            files={
                "bank_file": (
                    "bank_transactions.xlsx",
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    "clear_transactions.xlsx",
                    clear_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "upload success"
    assert body["data"]["total_bank_rows"] == 10
    assert body["data"]["total_clear_rows"] == 10
    assert body["data"]["auto_fixed_rows"] == 0
    assert body["data"]["pending_ai_rows"] == 0
    assert body["data"]["pending_human_rows"] == 0


def test_upload_reconciliation_files_rejects_missing_required_bank_columns(
    tmp_path: Path,
) -> None:
    bank_path, clear_path = generate_mock_excel(tmp_path)
    bank_df = pd.read_excel(bank_path).drop(columns=["bank_serial_no"])
    invalid_bank = BytesIO()
    bank_df.to_excel(invalid_bank, index=False)
    invalid_bank.seek(0)

    with clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            files={
                "bank_file": (
                    "bank_transactions.xlsx",
                    invalid_bank,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    "clear_transactions.xlsx",
                    clear_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )

    assert response.status_code == 400
    assert "bank_file missing required columns" in response.json()["detail"]
    assert "bank_serial_no" in response.json()["detail"]

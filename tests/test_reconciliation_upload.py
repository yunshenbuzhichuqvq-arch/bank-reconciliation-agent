from io import BytesIO
from decimal import Decimal
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
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
    assert body["data"]["auto_fixed_rows"] == 8
    assert body["data"]["pending_ai_rows"] == 1
    assert body["data"]["pending_human_rows"] == 2


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


def test_reconciliation_service_builds_structured_match_results(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mock_excel(tmp_path)
    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)

    results = ReconciliationService()._build_match_results(bank_df, clear_df)
    results_by_flow_id = {result.flow_id: result for result in results}

    assert len(results) == 11
    assert results_by_flow_id["F1001"].status == "AUTO_FIXED"
    assert results_by_flow_id["F1001"].error_type is None
    assert results_by_flow_id["F1004"].status == "PENDING_AI"
    assert results_by_flow_id["F1004"].error_type == "AMOUNT_MISMATCH"
    assert results_by_flow_id["F1004"].bank_amount == Decimal("300.00")
    assert results_by_flow_id["F1004"].clear_amount == Decimal("295.00")
    assert results_by_flow_id["F1004"].amount_diff == Decimal("5.00")
    assert results_by_flow_id["F1005"].status == "PENDING_HUMAN"
    assert results_by_flow_id["F1005"].error_type == "SINGLE_SIDE_MISSING"
    assert results_by_flow_id["F1005"].bank_amount == Decimal("120.00")
    assert results_by_flow_id["F1005"].clear_amount is None
    assert results_by_flow_id["F1006"].status == "PENDING_HUMAN"
    assert results_by_flow_id["F1006"].error_type == "SINGLE_SIDE_MISSING"
    assert results_by_flow_id["F1006"].bank_amount is None
    assert results_by_flow_id["F1006"].clear_amount == Decimal("45.00")

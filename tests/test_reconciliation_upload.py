from io import BytesIO
from decimal import Decimal
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.schemas.ledger import LedgerQuery
from bank_reconciliation_agent.services.ledger import LedgerService
from bank_reconciliation_agent.services.queue import QueueService
from bank_reconciliation_agent.services.rag_log import RagLogService
from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from bank_reconciliation_agent.services.transactions import TransactionService
from scripts.generate_mock_excel import BANK_COLUMNS, CLEAR_COLUMNS, generate_mock_excel


client = TestClient(app)
DEMO_HEADERS = {"X-User-ID": "demo_user"}


def test_upload_reconciliation_files_returns_excel_row_counts(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mock_excel(tmp_path)

    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
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

    task_id = body["data"]["task_id"]
    status_response = client.get(f"/api/v1/reconcile/{task_id}/status", headers=DEMO_HEADERS)
    assert status_response.status_code == 200
    status_body = status_response.json()["data"]
    assert status_body["task_id"] == task_id
    assert status_body["status"] == "UPLOADED"
    assert status_body["auto_fixed_rows"] == 8
    assert status_body["pending_ai_rows"] == 1
    assert status_body["pending_human_rows"] == 2
    assert status_body["unresolved_rows"] == 3

    exceptions_response = client.get(
        f"/api/v1/reconcile/{task_id}/exceptions",
        headers=DEMO_HEADERS,
    )
    assert exceptions_response.status_code == 200
    exceptions_body = exceptions_response.json()["data"]
    assert exceptions_body["task_id"] == task_id
    assert exceptions_body["total"] == 3
    exceptions_by_flow_id = {
        item["flow_id"]: item for item in exceptions_body["items"]
    }
    assert exceptions_by_flow_id["F1004"]["status"] == "PENDING_AI"
    assert exceptions_by_flow_id["F1004"]["error_type"] == "AMOUNT_MISMATCH"
    assert exceptions_by_flow_id["F1004"]["bank_amount"] == "300.00"
    assert exceptions_by_flow_id["F1004"]["clear_amount"] == "295.00"
    assert exceptions_by_flow_id["F1004"]["amount_diff"] == "5.00"
    assert exceptions_by_flow_id["F1004"]["audit_decision"]["decision"] == "PENDING_HUMAN"
    assert exceptions_by_flow_id["F1004"]["audit_decision"]["risk_level"] == "MEDIUM"
    assert "金额不一致" in exceptions_by_flow_id["F1004"]["audit_decision"]["reason"]
    assert exceptions_by_flow_id["F1005"]["status"] == "PENDING_HUMAN"
    assert exceptions_by_flow_id["F1005"]["error_type"] == "SINGLE_SIDE_MISSING"
    assert exceptions_by_flow_id["F1005"]["bank_amount"] == "120.00"
    assert exceptions_by_flow_id["F1005"]["clear_amount"] is None
    assert exceptions_by_flow_id["F1006"]["status"] == "PENDING_HUMAN"
    assert exceptions_by_flow_id["F1006"]["error_type"] == "SINGLE_SIDE_MISSING"
    assert exceptions_by_flow_id["F1006"]["bank_amount"] is None
    assert exceptions_by_flow_id["F1006"]["clear_amount"] == "45.00"

    ledger_response = client.get(f"/api/v1/ledger?task_id={task_id}", headers=DEMO_HEADERS)
    assert ledger_response.status_code == 200
    ledger_body = ledger_response.json()["data"]
    assert ledger_body["total"] == 3
    ledger_by_flow_id = {item["flow_id"]: item for item in ledger_body["items"]}
    assert ledger_by_flow_id["F1004"]["error_type"] == "AMOUNT_MISMATCH"
    assert ledger_by_flow_id["F1004"]["discrepancy_amount"] == "5.00"
    assert ledger_by_flow_id["F1004"]["handle_status"] == "PENDING_HUMAN"
    assert "金额不一致" in ledger_by_flow_id["F1004"]["ai_audit_opinion"]
    assert ledger_by_flow_id["F1004"]["ai_confidence"] == "0.7000"
    assert "unionpay_reconciliation_faq_001" in ledger_by_flow_id["F1004"]["rag_source"]
    assert status_body["ai_processed_rows"] == exceptions_body["total"] == ledger_body["total"]

    start_response = client.post(f"/api/v1/reconcile/{task_id}/start", headers=DEMO_HEADERS)
    assert start_response.status_code == 200
    assert start_response.json()["data"]["status"] == "AI_RUNNING"

    running_status_response = client.get(
        f"/api/v1/reconcile/{task_id}/status",
        headers=DEMO_HEADERS,
    )
    assert running_status_response.status_code == 200
    assert running_status_response.json()["data"]["status"] == "AI_RUNNING"

    persisted_status = ReconciliationService().get_status(task_id)
    assert persisted_status.status == "AI_RUNNING"
    assert persisted_status.auto_fixed_rows == 8
    assert persisted_status.pending_ai_rows == 1
    assert persisted_status.pending_human_rows == 2
    assert persisted_status.unresolved_rows == 3

    persisted_ledger_page = LedgerService().list(LedgerQuery(task_id=task_id))
    assert persisted_ledger_page.total == 3
    assert {row.flow_id for row in persisted_ledger_page.items} == {"F1004", "F1005", "F1006"}

    persisted_transactions = TransactionService()
    assert persisted_transactions.count_bank_rows(task_id) == 10
    assert persisted_transactions.count_clear_rows(task_id) == 10
    bank_f1004 = persisted_transactions.get_bank_row(task_id, "F1004")
    clear_f1004 = persisted_transactions.get_clear_row(task_id, "F1004")
    assert bank_f1004 is not None
    assert clear_f1004 is not None
    assert all(column in bank_f1004 for column in BANK_COLUMNS)
    assert all(column in clear_f1004 for column in CLEAR_COLUMNS)
    assert bank_f1004["amount"] == Decimal("300.00")
    assert clear_f1004["amount"] == Decimal("295.00")
    assert bank_f1004["bank_serial_no"] == "B202605210004"
    assert bank_f1004["credit_amount"] == Decimal("300.00")
    assert bank_f1004["remark"] == "金额差错样例"
    assert clear_f1004["clearing_serial_no"] == "C202605210004"
    assert clear_f1004["transaction_amount"] == Decimal("295.00")
    assert clear_f1004["remark"] == "金额差错样例"
    assert bank_f1004["summary"] == "清算金额差异"
    assert clear_f1004["summary"] == "清算金额差异"

    persisted_queue = QueueService()
    assert persisted_queue.count_rows(task_id) == 3
    queue_f1004 = persisted_queue.get_row(task_id, "F1004")
    assert queue_f1004 is not None
    assert queue_f1004["error_type"] == "AMOUNT_MISMATCH"
    assert queue_f1004["status"] == "PENDING_AI"

    persisted_rag_logs = RagLogService()
    assert persisted_rag_logs.count_rows(task_id) == 3
    rag_log_f1004 = persisted_rag_logs.get_latest_row(task_id, "AMOUNT_MISMATCH")
    assert rag_log_f1004 is not None
    assert rag_log_f1004["top_k"] == 2
    assert "bank_amount=300.00" in rag_log_f1004["query_text"]
    assert "unionpay_reconciliation_faq_001" in rag_log_f1004["sources"]


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
            headers=DEMO_HEADERS,
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


def test_upload_reconciliation_files_rejects_duplicate_bank_flow_id(
    tmp_path: Path,
) -> None:
    bank_path, clear_path = generate_mock_excel(tmp_path)
    bank_df = pd.read_excel(bank_path)
    bank_df.loc[1, "flow_id"] = bank_df.loc[0, "flow_id"]
    invalid_bank = BytesIO()
    bank_df.to_excel(invalid_bank, index=False)
    invalid_bank.seek(0)

    with clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
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
    assert response.json()["detail"] == "bank_file contains duplicate flow_id: F1001"


def test_upload_reconciliation_files_rejects_duplicate_clear_flow_id(
    tmp_path: Path,
) -> None:
    bank_path, clear_path = generate_mock_excel(tmp_path)
    clear_df = pd.read_excel(clear_path)
    clear_df.loc[1, "flow_id"] = clear_df.loc[0, "flow_id"]
    invalid_clear = BytesIO()
    clear_df.to_excel(invalid_clear, index=False)
    invalid_clear.seek(0)

    with bank_path.open("rb") as bank_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
            files={
                "bank_file": (
                    "bank_transactions.xlsx",
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    "clear_transactions.xlsx",
                    invalid_clear,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "clear_file contains duplicate flow_id: F1001"


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

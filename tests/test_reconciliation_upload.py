from io import BytesIO
from decimal import Decimal
import inspect
from pathlib import Path
import pytest

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import select

from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.schemas.ledger import LedgerQuery
from bank_reconciliation_agent.services.ledger import LedgerService, error_ledger_table
from bank_reconciliation_agent.services.memory.short_term import ShortTermMemoryService
from bank_reconciliation_agent.services.queue import QueueService, queue_service
from bank_reconciliation_agent.services.rag_log import RagLogService
from bank_reconciliation_agent.services import reconciliation as reconciliation_module
from bank_reconciliation_agent.services.reconciliation import (
    ReconciliationMatchResult,
    ReconciliationService,
    ReconciliationWriteBundle,
)
from bank_reconciliation_agent.services.agent_log import agent_log_service
from bank_reconciliation_agent.services.ledger import ledger_service
from bank_reconciliation_agent.services.task import TaskService, reconciliation_task_table, task_service
from bank_reconciliation_agent.services.transactions import TransactionService
from scripts.generate_mock_excel import (
    BANK_COLUMNS,
    CLEAR_COLUMNS,
    EXPECTED_BRANCHES,
    generate_mock_excel,
    generate_mvp1_mock_excel,
)


client = TestClient(app)
DEMO_HEADERS = {"X-User-ID": "demo_user"}


def test_upload_reconciliation_files_returns_excel_row_counts(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)

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
    assert body["data"]["total_bank_rows"] == 7
    assert body["data"]["total_clear_rows"] == 6
    assert body["data"]["auto_fixed_rows"] == 2
    assert body["data"]["pending_ai_rows"] == 0
    assert body["data"]["pending_human_rows"] == 6

    task_id = body["data"]["task_id"]
    status_response = client.get(f"/api/v1/reconcile/{task_id}/status", headers=DEMO_HEADERS)
    assert status_response.status_code == 200
    status_body = status_response.json()["data"]
    assert status_body["task_id"] == task_id
    assert status_body["status"] == "UPLOADED"
    assert status_body["auto_fixed_rows"] == 2
    assert status_body["pending_ai_rows"] == 0
    assert status_body["pending_human_rows"] == 6
    assert status_body["unresolved_rows"] == 6

    exceptions_response = client.get(
        f"/api/v1/reconcile/{task_id}/exceptions",
        headers=DEMO_HEADERS,
    )
    assert exceptions_response.status_code == 200
    exceptions_body = exceptions_response.json()["data"]
    assert exceptions_body["task_id"] == task_id
    assert exceptions_body["total"] == 6
    exceptions_by_flow_id = {
        item["flow_id"]: item for item in exceptions_body["items"]
    }
    expected_exceptions = {
        flow_id: expected
        for flow_id, expected in EXPECTED_BRANCHES.items()
        if expected[2] == "PENDING_HUMAN"
    }
    assert set(exceptions_by_flow_id) == set(expected_exceptions)
    for flow_id, (error_type, exception_branch, disposition) in expected_exceptions.items():
        assert exceptions_by_flow_id[flow_id]["status"] == disposition
        assert exceptions_by_flow_id[flow_id]["error_type"] == error_type
        assert exceptions_by_flow_id[flow_id]["exception_branch"] == exception_branch
        assert exceptions_by_flow_id[flow_id]["rag_evidence"]
        assert exceptions_by_flow_id[flow_id]["rag_evidence"][0]["chunk_id"]
        assert exceptions_by_flow_id[flow_id]["rag_evidence"][0]["source_url"].startswith("https://")
        assert exceptions_by_flow_id[flow_id]["audit_decision"]["decision"] == "PENDING_HUMAN"
        assert exceptions_by_flow_id[flow_id]["audit_decision"]["risk_level"] == "MEDIUM"
        assert exceptions_by_flow_id[flow_id]["audit_decision"]["evidence"]
    assert exceptions_by_flow_id["F2003"]["bank_amount"] == "300.00"
    assert exceptions_by_flow_id["F2003"]["clear_amount"] == "295.00"
    assert exceptions_by_flow_id["F2003"]["amount_diff"] == "5.00"
    assert exceptions_by_flow_id["F2005"]["bank_amount"] is None
    assert exceptions_by_flow_id["F2005"]["clear_amount"] == "72.00"
    assert exceptions_by_flow_id["F2006"]["bank_amount"] == "45.00"
    assert exceptions_by_flow_id["F2006"]["clear_amount"] is None

    ledger_response = client.get(f"/api/v1/ledger?task_id={task_id}", headers=DEMO_HEADERS)
    assert ledger_response.status_code == 200
    ledger_body = ledger_response.json()["data"]
    assert ledger_body["total"] == 6
    ledger_by_flow_id = {item["flow_id"]: item for item in ledger_body["items"]}
    assert set(ledger_by_flow_id) == set(expected_exceptions)
    for flow_id, (error_type, exception_branch, _) in expected_exceptions.items():
        assert ledger_by_flow_id[flow_id]["error_type"] == error_type
        assert ledger_by_flow_id[flow_id]["exception_branch"] == exception_branch
        assert ledger_by_flow_id[flow_id]["handle_status"] == "PENDING_HUMAN"
        assert Decimal(ledger_by_flow_id[flow_id]["ai_confidence"]) > Decimal("0")
        assert ledger_by_flow_id[flow_id]["rag_source"]
    assert ledger_by_flow_id["F2003"]["discrepancy_amount"] == "5.00"
    assert "金额不一致" in ledger_by_flow_id["F2003"]["ai_audit_opinion"]
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

    persisted_status = ReconciliationService().get_status(user_id="demo_user", task_id=task_id)
    assert persisted_status.status == "AI_RUNNING"
    assert persisted_status.auto_fixed_rows == 2
    assert persisted_status.pending_ai_rows == 0
    assert persisted_status.pending_human_rows == 6
    assert persisted_status.unresolved_rows == 6

    persisted_task = TaskService().get(user_id="demo_user", task_id=task_id)
    assert persisted_task is not None

    persisted_ledger_page = LedgerService().list(
        user_id="demo_user",
        query=LedgerQuery(task_id=task_id),
    )
    assert persisted_ledger_page.total == 6
    assert {row.flow_id for row in persisted_ledger_page.items} == set(expected_exceptions)
    persisted_ledger_by_flow_id = {row.flow_id: row for row in persisted_ledger_page.items}
    for flow_id, (_, exception_branch, _) in expected_exceptions.items():
        assert persisted_ledger_by_flow_id[flow_id].exception_branch == exception_branch

    persisted_transactions = TransactionService()
    assert persisted_transactions.count_bank_rows(user_id="demo_user", task_id=task_id) == 7
    assert persisted_transactions.count_clear_rows(user_id="demo_user", task_id=task_id) == 6
    bank_f2003 = persisted_transactions.get_bank_row(
        user_id="demo_user",
        task_id=task_id,
        flow_id="F2003",
    )
    clear_f2003 = persisted_transactions.get_clear_row(
        user_id="demo_user",
        task_id=task_id,
        flow_id="F2003",
    )
    assert bank_f2003 is not None
    assert clear_f2003 is not None
    assert all(column in bank_f2003 for column in BANK_COLUMNS)
    assert all(column in clear_f2003 for column in CLEAR_COLUMNS)
    assert bank_f2003["amount"] == Decimal("300.00")
    assert clear_f2003["amount"] == Decimal("295.00")
    assert bank_f2003["bank_serial_no"] == "B202606010003"
    assert bank_f2003["credit_amount"] == Decimal("300.00")
    assert bank_f2003["remark"] == "MVP-1 金额不一致样例"
    assert clear_f2003["clearing_serial_no"] == "C202606010003"
    assert clear_f2003["transaction_amount"] == Decimal("295.00")
    assert clear_f2003["remark"] == "MVP-1 金额不一致样例"
    assert bank_f2003["summary"] == "清算金额差异"
    assert clear_f2003["summary"] == "清算金额差异"

    persisted_queue = QueueService()
    assert persisted_queue.count_rows(user_id="demo_user", task_id=task_id) == 6
    queue_f2003 = persisted_queue.get_row(
        user_id="demo_user",
        task_id=task_id,
        flow_id="F2003",
    )
    queue_f2005 = persisted_queue.get_row(
        user_id="demo_user",
        task_id=task_id,
        flow_id="F2005",
    )
    assert queue_f2003 is not None
    assert queue_f2005 is not None
    assert persisted_task.scenario_type == "BANK_ENTERPRISE"
    assert queue_f2003["error_type"] == "AMOUNT_MISMATCH"
    assert queue_f2003["exception_branch"] == "BE-R002"
    assert queue_f2003["scenario_type"] == "BANK_ENTERPRISE"
    assert queue_f2005["scenario_type"] == "BANK_ENTERPRISE"
    assert queue_f2003["status"] == "PENDING_HUMAN"
    with get_engine().connect() as connection:
        ledger_rows = connection.execute(
            select(error_ledger_table.c.flow_id, error_ledger_table.c.scenario_type).where(
                error_ledger_table.c.user_id == "demo_user",
                error_ledger_table.c.task_id == task_id,
            )
        ).all()
    ledger_scenarios = {flow_id: scenario_type for flow_id, scenario_type in ledger_rows}
    assert ledger_scenarios["F2003"] == "BANK_ENTERPRISE"
    assert ledger_scenarios["F2005"] == "BANK_ENTERPRISE"

    persisted_rag_logs = RagLogService()
    assert persisted_rag_logs.count_rows(user_id="demo_user", task_id=task_id) == 6
    rag_log_f2003 = persisted_rag_logs.get_latest_row(
        user_id="demo_user",
        task_id=task_id,
        query_marker="AMOUNT_MISMATCH",
    )
    assert rag_log_f2003 is not None
    assert rag_log_f2003["top_k"] == settings.rag_rerank_top_k
    assert "金额不一致 对账差异 处理规则" in rag_log_f2003["query_text"]
    assert "bank_amount=300.00" in rag_log_f2003["query_text"]
    assert "unionpay_reconciliation_faq_001" in rag_log_f2003["sources"]


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


def test_upload_reconciliation_files_uses_stable_task_id_for_same_content(
    tmp_path: Path,
) -> None:
    bank_path, clear_path = generate_mock_excel(tmp_path)

    def upload_once() -> str:
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
        return response.json()["data"]["task_id"]

    assert upload_once() == upload_once()


def test_upload_reconciliation_files_rejects_invalid_scenario_type(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)

    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
            data={"scenario_type": "INVALID_SCENARIO"},
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

    assert response.status_code == 400
    assert response.json()["detail"] == "scenario_type must be one of: BANK_ENTERPRISE, BANK_CLEARING"


def test_upload_reconciliation_files_persists_bank_clearing_scenario_type(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)

    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        response = client.post(
            "/api/v1/reconcile/upload",
            headers=DEMO_HEADERS,
            data={"scenario_type": "BANK_CLEARING"},
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
    task_id = response.json()["data"]["task_id"]

    persisted_task = TaskService().get(user_id="demo_user", task_id=task_id)
    persisted_queue = QueueService()
    queue_row = persisted_queue.get_row(
        user_id="demo_user",
        task_id=task_id,
        flow_id="F2003",
    )

    assert persisted_task is not None
    assert queue_row is not None
    assert persisted_task.scenario_type == "BANK_CLEARING"
    assert queue_row["scenario_type"] == "BANK_CLEARING"
    with get_engine().connect() as connection:
        task_scenario = connection.execute(
            select(reconciliation_task_table.c.scenario_type).where(
                reconciliation_task_table.c.user_id == "demo_user",
                reconciliation_task_table.c.task_id == task_id,
            )
        ).scalar_one()
        ledger_scenario = connection.execute(
            select(error_ledger_table.c.scenario_type).where(
                error_ledger_table.c.user_id == "demo_user",
                error_ledger_table.c.task_id == task_id,
                error_ledger_table.c.flow_id == "F2003",
            )
        ).scalar_one()

    assert task_scenario == "BANK_CLEARING"
    assert ledger_scenario == "BANK_CLEARING"


def test_upload_reconciliation_files_rejects_empty_bank_flow_id(
    tmp_path: Path,
) -> None:
    bank_path, clear_path = generate_mock_excel(tmp_path)
    bank_df = pd.read_excel(bank_path)
    bank_df.loc[0, "flow_id"] = None
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
    assert response.json()["detail"] == "bank_file contains empty flow_id values"


def test_reconciliation_service_builds_structured_match_results(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)

    results = ReconciliationService()._build_match_results(bank_df, clear_df)
    results_by_flow_id = {result.flow_id: result for result in results}

    assert len(results) == len(EXPECTED_BRANCHES)
    for flow_id, (error_type, exception_branch, disposition) in EXPECTED_BRANCHES.items():
        assert results_by_flow_id[flow_id].status == disposition
        assert results_by_flow_id[flow_id].error_type == error_type
        assert results_by_flow_id[flow_id].exception_branch == exception_branch
    assert results_by_flow_id["F2003"].bank_amount == Decimal("300.00")
    assert results_by_flow_id["F2003"].clear_amount == Decimal("295.00")
    assert results_by_flow_id["F2003"].amount_diff == Decimal("5.00")
    assert results_by_flow_id["F2005"].bank_amount is None
    assert results_by_flow_id["F2005"].clear_amount == Decimal("72.00")
    assert results_by_flow_id["F2006"].bank_amount == Decimal("45.00")
    assert results_by_flow_id["F2006"].clear_amount is None


def test_reconciliation_service_build_match_results_passes_scenario_type(monkeypatch) -> None:
    service = ReconciliationService()
    captured: list[str] = []

    def fake_classify(bank_df, clear_df, *, scenario_type):
        del bank_df, clear_df
        captured.append(scenario_type)
        return []

    monkeypatch.setattr(
        "bank_reconciliation_agent.services.reconciliation.exception_router.classify",
        fake_classify,
    )

    service._build_match_results(pd.DataFrame(), pd.DataFrame(), scenario_type="BANK_CLEARING")

    assert captured == ["BANK_CLEARING"]


def test_upload_rolls_back_core_writes_when_ai_stats_update_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    task_id = "TASK_ROLLBACK_TEST"
    original_replace_ai_stats = task_service.replace_ai_stats

    def failing_replace_ai_stats(**kwargs):
        original_replace_ai_stats(**kwargs)
        raise RuntimeError("boom")

    monkeypatch.setattr(task_service, "replace_ai_stats", failing_replace_ai_stats)
    monkeypatch.setattr(ReconciliationService, "_generate_task_id", lambda self, content: task_id)

    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        with pytest.raises(RuntimeError, match="boom"):
            client.post(
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

    persisted_task = TaskService().get(user_id="demo_user", task_id=task_id)
    persisted_ledger_page = LedgerService().list(
        user_id="demo_user",
        query=LedgerQuery(task_id=task_id),
    )

    assert persisted_task is not None
    assert persisted_task.ai_processed_rows == 0
    assert persisted_task.total_llm_tokens == 0
    assert persisted_ledger_page.total == 0
    assert QueueService().count_rows(user_id="demo_user", task_id=task_id) == 0


def test_upload_ignores_agent_log_side_effect_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    task_id = "TASK_SIDE_EFFECT_TEST"

    def failing_replace_task_rows(**kwargs):
        del kwargs
        raise RuntimeError("agent log unavailable")

    monkeypatch.setattr(agent_log_service, "replace_task_rows", failing_replace_task_rows)
    monkeypatch.setattr(ReconciliationService, "_generate_task_id", lambda self, content: task_id)

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
    task_id = response.json()["data"]["task_id"]
    assert QueueService().count_rows(user_id="demo_user", task_id=task_id) == 6
    assert LedgerService().list(user_id="demo_user", query=LedgerQuery(task_id=task_id)).total == 6
    persisted_task = TaskService().get(user_id="demo_user", task_id=task_id)
    assert persisted_task is not None
    assert persisted_task.ai_processed_rows == 6


def test_upload_appends_short_term_memory_after_each_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)
    task_id = "TASK_MEMORY_SHORT_TERM_TEST"
    monkeypatch.setattr(ReconciliationService, "_generate_task_id", lambda self, content: task_id)

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
    task_id = response.json()["data"]["task_id"]
    short_rows = ShortTermMemoryService().recent(thread_id=task_id)

    assert len(short_rows) == 6
    assert {row["error_type"] for row in short_rows} >= {"AMOUNT_MISMATCH", "BANK_UNARRIVED"}
    assert all(row["decision"] == "PENDING_HUMAN" for row in short_rows)


def test_upload_ignores_memory_side_effect_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)

    def failing_memory_update(**kwargs):
        del kwargs
        raise RuntimeError("memory unavailable")

    monkeypatch.setattr(reconciliation_module.memory_manager, "update_after_decision", failing_memory_update)

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


def test_write_ledger_entries_does_not_directly_touch_other_service_privates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ReconciliationService()
    task_id = "TASK_ENGINE_DECOUPLE"
    task_service.replace_task(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )
    original_ledger_init = ledger_service._ensure_initialized
    original_queue_init = queue_service._ensure_initialized
    original_task_init = task_service._ensure_initialized

    def forbid_direct_private_init(original_method):
        def wrapped():
            caller = inspect.stack()[1].function
            if caller == "_write_ledger_entries":
                raise AssertionError(f"direct private init from {caller} is forbidden")
            return original_method()

        return wrapped

    class BrokenEngine:
        def begin(self):
            raise AssertionError("should not use task_service._engine directly")

    monkeypatch.setattr(ledger_service, "_ensure_initialized", forbid_direct_private_init(original_ledger_init))
    monkeypatch.setattr(queue_service, "_ensure_initialized", forbid_direct_private_init(original_queue_init))
    monkeypatch.setattr(task_service, "_ensure_initialized", forbid_direct_private_init(original_task_init))
    monkeypatch.setattr(task_service, "_engine", BrokenEngine())
    monkeypatch.setattr(
        service,
        "_build_write_bundle",
        lambda **kwargs: ReconciliationWriteBundle(
            ledger_rows=[],
            rag_log_rows=[],
            agent_log_rows=[],
            trace_payloads=[],
            ai_processed_rows=0,
            fallback_l2_rows=0,
            fallback_l3_rows=0,
            total_prompt_tokens=0,
            total_completion_tokens=0,
        ),
    )

    service._write_ledger_entries(
        user_id="demo_user",
        task_id=task_id,
        scenario_type="BANK_ENTERPRISE",
        results=[
            ReconciliationMatchResult(
                flow_id="FLOW-DECOUPLE-001",
                status="PENDING_HUMAN",
                error_type="AMOUNT_MISMATCH",
                exception_branch="BE-R002",
                bank_amount=Decimal("100.00"),
                clear_amount=Decimal("99.00"),
                amount_diff=Decimal("1.00"),
            )
        ],
        queue_rows=[],
    )

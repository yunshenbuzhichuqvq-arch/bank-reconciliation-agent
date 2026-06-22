from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.schemas.ledger import LedgerQuery
from bank_reconciliation_agent.services.ledger import LedgerService
from scripts.generate_mock_excel import EXPECTED_BRANCHES, generate_mvp1_mock_excel
from tests.auth_helpers import demo_bearer_headers


client = TestClient(app)
DEMO_HEADERS = demo_bearer_headers()


def test_mvp2a1_upload_to_ledger_covers_five_bank_enterprise_branches(
    tmp_path: Path,
) -> None:
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
    task_id = response.json()["data"]["task_id"]

    page = LedgerService().list(
        user_id="demo_user",
        query=LedgerQuery(task_id=task_id, page=1, page_size=10_000),
    )
    rows_by_flow_id = {row.flow_id: row for row in page.items}
    expected_rows = {
        flow_id: expected
        for flow_id, expected in EXPECTED_BRANCHES.items()
        if expected[2] == "PENDING_HUMAN"
    }

    assert set(rows_by_flow_id) == set(expected_rows)
    assert {row.exception_branch for row in rows_by_flow_id.values()} == {
        "BE-R002",
        "BE-R004",
        "BE-R005",
        "BE-R006",
        "BE-R008",
    }
    for flow_id, (error_type, exception_branch, _) in expected_rows.items():
        row = rows_by_flow_id[flow_id]
        assert row.error_type == error_type
        assert row.exception_branch == exception_branch
        assert row.handle_status == "PENDING_HUMAN"
        assert row.ai_audit_opinion
        assert row.ai_confidence is not None
        assert Decimal("0") <= row.ai_confidence <= Decimal("1")
        assert row.rag_source

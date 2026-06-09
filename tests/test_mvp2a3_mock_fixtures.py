from pathlib import Path

import pandas as pd

from bank_reconciliation_agent.services.reconciliation import (
    BANK_REQUIRED_COLUMNS,
    CLEAR_REQUIRED_COLUMNS,
)
from bank_reconciliation_agent.services.exception_router import ExceptionRouter
from scripts.generate_mock_excel import (
    BANK_CLEARING_EXPECTED_BRANCHES,
    generate_mvp2a3_mock_excel,
)


def test_generate_mvp2a3_mock_excel_writes_bank_clearing_fixture_files(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp2a3_mock_excel(tmp_path)

    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)

    assert bank_path.name == "mvp2a3_core.xlsx"
    assert clear_path.name == "mvp2a3_clearing.xlsx"
    assert set(BANK_REQUIRED_COLUMNS).issubset(bank_df.columns)
    assert set(CLEAR_REQUIRED_COLUMNS).issubset(clear_df.columns)
    assert bank_df["flow_id"].is_unique
    assert clear_df["flow_id"].is_unique


def test_generate_mvp2a3_mock_excel_covers_expected_branches_and_statuses(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp2a3_mock_excel(tmp_path)

    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)
    results = {
        result.flow_id: result
        for result in ExceptionRouter().classify(
            bank_df,
            clear_df,
            scenario_type="BANK_CLEARING",
        )
    }

    expected = BANK_CLEARING_EXPECTED_BRANCHES

    assert set(expected) == set(results)
    assert expected["BC3001"] == (None, None, "AUTO_FIXED")
    assert expected["BC3002"] == ("CLEARING_SINGLE_SIDE", "BC-R001", "PENDING_HUMAN")
    assert expected["BC3003"] == ("CUTOFF_CROSS_DAY", "BC-R003", "PENDING_HUMAN")
    assert expected["BC3004"] == ("CUTOFF_CROSS_DAY", "BC-R003", "PENDING_HUMAN")
    assert expected["CORE3003"] == ("UNCLASSIFIED", None, "PENDING_HUMAN")
    assert results["BC3001"].action == "AUTO_FIX"
    assert results["BC3002"].exception_branch == "BC-R001"
    assert results["BC3003"].exception_branch == "BC-R003"
    assert results["BC3004"].exception_branch == "BC-R003"
    assert results["CORE3003"].error_type == "UNCLASSIFIED"


def test_generate_mvp2a3_mock_excel_links_t1_candidate_and_waiting_case(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp2a3_mock_excel(tmp_path)

    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)
    results = {
        result.flow_id: result
        for result in ExceptionRouter().classify(
            bank_df,
            clear_df,
            scenario_type="BANK_CLEARING",
        )
    }

    cutoff_hit = results["BC3003"]
    cutoff_wait = results["BC3004"]

    assert cutoff_hit.t1_candidate == {
        "flow_id": "CORE3003",
        "accounting_date": "2026-06-11",
    }
    assert cutoff_wait.t1_candidate is None

    matched_core = bank_df.loc[bank_df["flow_id"] == "CORE3003"].iloc[0]
    matched_clear = clear_df.loc[clear_df["flow_id"] == "BC3003"].iloc[0]
    waiting_clear = clear_df.loc[clear_df["flow_id"] == "BC3004"].iloc[0]

    assert matched_core["reference_no"] == matched_clear["reference_no"]
    assert matched_core["merchant_order_no"] == matched_clear["merchant_order_no"]
    assert matched_core["accounting_date"] == "2026-06-11"
    assert matched_clear["trade_time"] == "23:30"
    assert waiting_clear["trade_time"] == "23:45"

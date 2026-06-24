from pathlib import Path

import pandas as pd

from bank_reconciliation_agent.services.exception_router import ExceptionRouter
from bank_reconciliation_agent.services.hooks import (
    _BANK_REQUIRED_COLUMNS,
    _CLEAR_REQUIRED_COLUMNS,
)
from scripts.generate_mock_excel import (
    BANK_CLEARING_EXPECTED_BRANCHES,
    build_batch,
    generate_mvp2a3_mock_excel,
)


def test_generate_mvp2a3_mock_excel_writes_bank_clearing_fixture_files(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp2a3_mock_excel(tmp_path)

    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)

    assert bank_path.name == "mvp2a3_core.xlsx"
    assert clear_path.name == "mvp2a3_clearing.xlsx"
    assert set(_BANK_REQUIRED_COLUMNS).issubset(bank_df.columns)
    assert set(_CLEAR_REQUIRED_COLUMNS).issubset(clear_df.columns)
    assert bank_df["flow_id"].is_unique
    assert clear_df["flow_id"].is_unique


def test_build_batch_supports_bank_clearing_normal_rows_and_cutoff_link() -> None:
    bank_df, clear_df, expected = build_batch(
        scenario="bank_clearing",
        n_normal=3,
        seed=20260624,
    )

    expected_anomalies = BANK_CLEARING_EXPECTED_BRANCHES
    expected_normal_count = 3

    assert expected == expected_anomalies
    assert len(bank_df) == expected_normal_count + 2
    assert len(clear_df) == expected_normal_count + 4
    assert set(expected_anomalies).issubset(set(bank_df["flow_id"]) | set(clear_df["flow_id"]))
    assert set(bank_df["flow_id"]) - set(expected_anomalies)
    assert set(clear_df["flow_id"]) - set(expected_anomalies)

    matched_core = bank_df.loc[bank_df["flow_id"] == "CORE3003"].iloc[0]
    matched_clear = clear_df.loc[clear_df["flow_id"] == "BC3003"].iloc[0]
    assert matched_core["reference_no"] == matched_clear["reference_no"]
    assert matched_core["merchant_order_no"] == matched_clear["merchant_order_no"]


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

    assert set(expected).issubset(results)
    normal_results = {
        flow_id: result
        for flow_id, result in results.items()
        if flow_id not in expected
    }
    assert normal_results
    assert {result.action for result in normal_results.values()} == {"AUTO_FIX"}
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

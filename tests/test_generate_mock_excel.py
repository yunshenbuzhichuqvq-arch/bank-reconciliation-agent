from pathlib import Path

import pandas as pd

from scripts.generate_mock_excel import (
    BANK_COLUMNS,
    CLEAR_COLUMNS,
    EXPECTED_BRANCHES,
    generate_mock_excel,
    generate_mvp1_mock_excel,
)


def test_generate_mock_excel_writes_small_reconciliation_dataset(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mock_excel(tmp_path)

    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)

    assert bank_path.name == "bank_transactions.xlsx"
    assert clear_path.name == "clear_transactions.xlsx"
    assert list(bank_df.columns) == [
        "flow_id",
        "bank_serial_no",
        "accounting_date",
        "accounting_time",
        "value_date",
        "self_account_no_masked",
        "self_account_name_masked",
        "self_bank_name",
        "currency",
        "transaction_type",
        "transaction_direction",
        "amount",
        "debit_amount",
        "credit_amount",
        "fee_amount",
        "balance_after",
        "trade_time",
        "account_no_masked",
        "customer_name_masked",
        "counterparty_account_no_masked",
        "counterparty_name_masked",
        "counterparty_bank_name",
        "channel",
        "summary",
        "purpose",
        "posting_status",
        "branch_no",
        "teller_id",
        "transaction_code",
        "source_system",
        "remark",
    ]
    assert list(clear_df.columns) == [
        "flow_id",
        "clearing_serial_no",
        "merchant_id",
        "merchant_name",
        "store_name",
        "terminal_id",
        "channel",
        "transaction_type",
        "trade_date",
        "trade_time",
        "settlement_date",
        "amount",
        "transaction_amount",
        "fee_amount",
        "net_amount",
        "currency",
        "status",
        "summary",
        "batch_no",
        "voucher_no",
        "reference_no",
        "merchant_order_no",
        "payer_account_no_masked",
        "payer_name_masked",
        "payee_account_no_masked",
        "payee_name_masked",
        "order_description",
        "remark",
    ]
    assert len(bank_df) == 10
    assert len(clear_df) == 10
    assert set(bank_df["flow_id"]) - set(clear_df["flow_id"]) == {"F1005"}
    assert set(clear_df["flow_id"]) - set(bank_df["flow_id"]) == {"F1006"}
    assert bank_df.loc[bank_df["flow_id"] == "F1001", "amount"].iloc[0] == 100.00
    assert bank_df.loc[bank_df["flow_id"] == "F1008", "transaction_direction"].iloc[0] == "DEBIT"
    assert bank_df.loc[bank_df["flow_id"] == "F1001", "trade_time"].iloc[0] == "2026-05-21 09:10:00"
    assert clear_df.loc[clear_df["flow_id"] == "F1001", "trade_time"].iloc[0] == "2026-05-21 09:10:05"
    assert clear_df.loc[clear_df["flow_id"] == "F1001", "summary"].iloc[0] == "网银转账"


def test_generate_mock_excel_includes_amount_mismatch_case(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mock_excel(tmp_path)

    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)

    bank_amount = bank_df.loc[bank_df["flow_id"] == "F1004", "credit_amount"].iloc[0]
    clear_amount = clear_df.loc[clear_df["flow_id"] == "F1004", "transaction_amount"].iloc[0]

    assert bank_amount == 300.00
    assert clear_amount == 295.00


def test_generate_mvp1_mock_excel_writes_branch_fixture(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)

    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)
    all_flow_ids = set(bank_df["flow_id"]) | set(clear_df["flow_id"])

    assert bank_path.name == "mvp1_bank.xlsx"
    assert clear_path.name == "mvp1_clear.xlsx"
    assert list(bank_df.columns) == BANK_COLUMNS
    assert list(clear_df.columns) == CLEAR_COLUMNS
    assert set(EXPECTED_BRANCHES) == all_flow_ids
    assert bank_df["flow_id"].is_unique
    assert clear_df["flow_id"].is_unique


def test_generate_mvp1_mock_excel_covers_all_expected_branches(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)

    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)
    dispositions = {flow_id: value[2] for flow_id, value in EXPECTED_BRANCHES.items()}
    branches = {
        (error_type, exception_branch)
        for error_type, exception_branch, _disposition in EXPECTED_BRANCHES.values()
    }
    duplicate_flows = [
        flow_id
        for flow_id, (error_type, _branch, _disposition) in EXPECTED_BRANCHES.items()
        if error_type == "DUPLICATE_BOOKING"
    ]

    assert (None, None) in branches
    assert ("AMOUNT_MISMATCH", "BE-R002") in branches
    assert ("NARRATIVE_NAME_MISMATCH", "BE-R004") in branches
    assert ("BANK_UNARRIVED", "BE-R005") in branches
    assert ("BOOK_UNRECORDED", "BE-R006") in branches
    assert ("DUPLICATE_BOOKING", "BE-R008") in branches
    assert len(duplicate_flows) == 2
    assert all(disposition in {"AUTO_FIXED", "PENDING_HUMAN"} for disposition in dispositions.values())
    assert {flow_id for flow_id, disposition in dispositions.items() if disposition == "AUTO_FIXED"}
    clear_only_flows = set(clear_df["flow_id"]) - set(bank_df["flow_id"])
    bank_only_flows = set(bank_df["flow_id"]) - set(clear_df["flow_id"])
    expected_bank_unarrived = {
        flow_id
        for flow_id, (error_type, _branch, _disposition) in EXPECTED_BRANCHES.items()
        if error_type == "BANK_UNARRIVED"
    }
    expected_book_unrecorded = {
        flow_id
        for flow_id, (error_type, _branch, _disposition) in EXPECTED_BRANCHES.items()
        if error_type == "BOOK_UNRECORDED"
    }
    duplicate_flows_set = set(duplicate_flows)

    assert clear_only_flows == expected_bank_unarrived
    assert expected_book_unrecorded <= bank_only_flows
    assert (bank_only_flows - expected_book_unrecorded) <= duplicate_flows_set


def test_generate_mvp1_mock_excel_has_duplicate_booking_fixture(tmp_path: Path) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path)

    bank_df = pd.read_excel(bank_path)
    clear_flow_ids = set(pd.read_excel(clear_path)["flow_id"])
    duplicate_flows = [
        flow_id
        for flow_id, (error_type, _branch, _disposition) in EXPECTED_BRANCHES.items()
        if error_type == "DUPLICATE_BOOKING"
    ]
    duplicate_rows = bank_df[bank_df["flow_id"].isin(duplicate_flows)]

    assert len(duplicate_rows) == 2
    assert duplicate_rows["amount"].nunique() == 1
    assert duplicate_rows["counterparty_name_masked"].nunique() == 1
    assert len(set(duplicate_flows) & clear_flow_ids) == 1

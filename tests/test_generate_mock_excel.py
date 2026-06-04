from pathlib import Path

import pandas as pd

from bank_reconciliation_agent.services.reconciliation import (
    SOURCE_A_REQUIRED_COLUMNS,
    SOURCE_B_REQUIRED_COLUMNS,
)
from scripts.generate_mock_excel import generate_mock_excel


def test_generate_mock_excel_writes_small_reconciliation_dataset(tmp_path: Path) -> None:
    source_a_path, source_b_path = generate_mock_excel(tmp_path)

    source_a_df = pd.read_excel(source_a_path)
    source_b_df = pd.read_excel(source_b_path)

    assert source_a_path.name == "source_a_enterprise_book.xlsx"
    assert source_b_path.name == "source_b_bank_statement.xlsx"
    assert set(SOURCE_A_REQUIRED_COLUMNS).issubset(source_a_df.columns)
    assert set(SOURCE_B_REQUIRED_COLUMNS).issubset(source_b_df.columns)
    assert list(source_a_df.columns) == [
        "flow_id",
        "voucher_no",
        "accounting_period",
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
    assert list(source_b_df.columns) == [
        "flow_id",
        "bank_serial_no",
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
        "balance_after",
        "account_no_masked",
        "customer_name_masked",
        "counterparty_account_no_masked",
        "counterparty_name_masked",
        "counterparty_bank_name",
        "channel",
        "remark",
    ]
    assert len(source_a_df) == 10
    assert len(source_b_df) == 10
    assert set(source_a_df["flow_id"]) - set(source_b_df["flow_id"]) == {"F1005"}
    assert set(source_b_df["flow_id"]) - set(source_a_df["flow_id"]) == {"F1006"}
    assert source_a_df.loc[source_a_df["flow_id"] == "F1001", "amount"].iloc[0] == 100.00
    assert source_a_df.loc[source_a_df["flow_id"] == "F1008", "transaction_direction"].iloc[0] == "DEBIT"
    assert source_a_df.loc[source_a_df["flow_id"] == "F1001", "trade_time"].iloc[0] == "2026-05-21 09:10:00"
    assert source_b_df.loc[source_b_df["flow_id"] == "F1001", "trade_time"].iloc[0] == "2026-05-21 09:10:05"
    assert source_b_df.loc[source_b_df["flow_id"] == "F1001", "summary"].iloc[0] == "银行到账"


def test_generate_mock_excel_includes_amount_mismatch_case(tmp_path: Path) -> None:
    source_a_path, source_b_path = generate_mock_excel(tmp_path)

    source_a_df = pd.read_excel(source_a_path)
    source_b_df = pd.read_excel(source_b_path)

    source_a_amount = source_a_df.loc[source_a_df["flow_id"] == "F1004", "amount"].iloc[0]
    source_b_amount = source_b_df.loc[source_b_df["flow_id"] == "F1004", "amount"].iloc[0]

    assert source_a_amount == 300.00
    assert source_b_amount == 295.00

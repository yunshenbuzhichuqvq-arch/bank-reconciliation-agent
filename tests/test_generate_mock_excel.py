from pathlib import Path

import pandas as pd

from scripts.generate_mock_excel import generate_mock_excel


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

from pathlib import Path

import pandas as pd


SOURCE_A_COLUMNS = [
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

SOURCE_B_COLUMNS = [
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

# Backward-compatible aliases for TASK-003, where public API names are restored.
BANK_COLUMNS = SOURCE_A_COLUMNS
CLEAR_COLUMNS = SOURCE_B_COLUMNS


def generate_mock_excel(output_dir: str | Path = "mock_data") -> tuple[Path, Path]:
    """生成银企对账 Source A/B 模拟 Excel。"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_a_df = pd.DataFrame([_source_a_row(*row) for row in _source_a_base_rows()])
    source_b_df = pd.DataFrame([_source_b_row(*row) for row in _source_b_base_rows()])

    source_a_path = output_path / "source_a_enterprise_book.xlsx"
    source_b_path = output_path / "source_b_bank_statement.xlsx"
    source_a_df.to_excel(source_a_path, index=False)
    source_b_df.to_excel(source_b_path, index=False)
    return source_a_path, source_b_path


def _source_a_base_rows() -> list[tuple[str, float, str, str, str]]:
    return [
        ("F1001", 100.00, "CREDIT", "上海云杉科技有限公司", "正常平账样例"),
        ("F1002", 250.50, "CREDIT", "杭州青禾商贸有限公司", "正常平账样例"),
        ("F1003", 88.80, "DEBIT", "员工代发虚拟户", "正常平账样例"),
        ("F1004", 300.00, "CREDIT", "南京北辰供应链有限公司", "金额差错样例"),
        ("F1005", 120.00, "CREDIT", "苏州东海制造有限公司", "银行未到账样例"),
        ("F1007", 66.60, "CREDIT", "宁波星河电子有限公司", "正常平账样例"),
        ("F1008", 35.20, "DEBIT", "上海浦江物流有限公司", "正常平账样例"),
        ("F1009", 2.00, "DEBIT", "手续费虚拟户", "正常平账样例"),
        ("F1010", 510.00, "CREDIT", "无锡云帆材料有限公司", "正常平账样例"),
        ("F1011", 18.80, "CREDIT", "上海云杉科技有限公司", "正常平账样例"),
    ]


def _source_b_base_rows() -> list[tuple[str, float, str, str, str]]:
    return [
        ("F1001", 100.00, "CREDIT", "上海云杉科技有限公司", "正常平账样例"),
        ("F1002", 250.50, "CREDIT", "杭州青禾商贸有限公司", "正常平账样例"),
        ("F1003", 88.80, "DEBIT", "员工代发虚拟户", "正常平账样例"),
        ("F1004", 295.00, "CREDIT", "南京北辰供应链有限公司", "金额差错样例"),
        ("F1006", 45.00, "CREDIT", "常州临港贸易有限公司", "企业未入账样例"),
        ("F1007", 66.60, "CREDIT", "宁波星河电子有限公司", "正常平账样例"),
        ("F1008", 35.20, "DEBIT", "上海浦江物流有限公司", "正常平账样例"),
        ("F1009", 2.00, "DEBIT", "手续费虚拟户", "正常平账样例"),
        ("F1010", 510.00, "CREDIT", "无锡云帆材料有限公司", "正常平账样例"),
        ("F1011", 18.80, "CREDIT", "上海云杉科技有限公司", "正常平账样例"),
    ]


def _source_a_row(
    flow_id: str, amount: float, direction: str, counterparty_name: str, remark: str,
) -> dict[str, object]:
    suffix = flow_id[-4:]
    debit_amount = amount if direction == "DEBIT" else 0.00
    credit_amount = amount if direction == "CREDIT" else 0.00
    time_text = _trade_time_for(flow_id)
    return {
        "flow_id": flow_id,
        "voucher_no": f"VCH-{suffix}",
        "accounting_period": "2026-05",
        "accounting_date": "2026-05-21",
        "accounting_time": time_text,
        "value_date": "2026-05-21",
        "self_account_no_masked": "6222********0001",
        "self_account_name_masked": "上海晨星贸易有限公司",
        "self_bank_name": "中国银行上海分行",
        "currency": "CNY",
        "transaction_type": "TRANSFER" if amount != 2.00 else "FEE",
        "transaction_direction": direction,
        "amount": amount,
        "debit_amount": debit_amount,
        "credit_amount": credit_amount,
        "fee_amount": 0.00,
        "balance_after": 10000.00 + credit_amount - debit_amount,
        "trade_time": f"2026-05-21 {time_text}",
        "account_no_masked": "6222********0001",
        "customer_name_masked": "上海晨星贸易有限公司",
        "counterparty_account_no_masked": f"6214********{suffix}",
        "counterparty_name_masked": counterparty_name,
        "counterparty_bank_name": "模拟银行",
        "channel": "ERP",
        "summary": "企业账簿记账",
        "purpose": "货款" if direction == "CREDIT" else "付款",
        "posting_status": "POSTED",
        "branch_no": "SH001",
        "teller_id": "ERP_SYSTEM",
        "transaction_code": "BOOK_ENTRY",
        "source_system": "ENTERPRISE_ERP",
        "remark": remark,
    }


def _source_b_row(
    flow_id: str, amount: float, direction: str, counterparty_name: str, remark: str,
) -> dict[str, object]:
    suffix = flow_id[-4:]
    time_text = _trade_time_for(flow_id)
    return {
        "flow_id": flow_id,
        "bank_serial_no": f"B20260521{suffix}",
        "trade_date": "2026-05-21",
        "trade_time": f"2026-05-21 {time_text[:-2]}05",
        "settlement_date": "2026-05-21",
        "amount": amount,
        "transaction_amount": amount,
        "fee_amount": 0.00,
        "net_amount": amount,
        "currency": "CNY",
        "status": "SUCCESS",
        "summary": "银行到账" if direction == "CREDIT" else "银行付款",
        "balance_after": 10000.00 + (amount if direction == "CREDIT" else -amount),
        "account_no_masked": "6222********0001",
        "customer_name_masked": "上海晨星贸易有限公司",
        "counterparty_account_no_masked": f"6214********{suffix}",
        "counterparty_name_masked": counterparty_name,
        "counterparty_bank_name": "模拟银行",
        "channel": "网上银行",
        "remark": remark,
    }


def _trade_time_for(flow_id: str) -> str:
    minute = {"F1001": 10}.get(flow_id, int(flow_id[-2:]))
    return f"09:{minute:02d}:00"


if __name__ == "__main__":
    source_a, source_b = generate_mock_excel()
    print(f"Generated: {source_a}")
    print(f"Generated: {source_b}")

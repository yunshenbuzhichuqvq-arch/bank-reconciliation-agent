from pathlib import Path

from faker import Faker
import pandas as pd

from scripts.mock_narratives import sample_narrative

MOCK_FAKER_SEED = 20260624
MOCK_FAKER = Faker("zh_CN")
DEFAULT_BANK_ENTERPRISE_NORMAL_ROWS = 12
FAKER_FILLABLE_FIELDS = frozenset(
    {
        "self_bank_name",
        "counterparty_bank_name",
        "store_name",
        "terminal_id",
    }
)


BANK_SOURCE_COLUMNS = [
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
    "debit_amount",
    "credit_amount",
    "balance_after",
    "counterparty_account_no_masked",
    "counterparty_name_masked",
    "counterparty_bank_name",
    "channel",
    "summary",
    "purpose",
    "remark",
]

BANK_COLUMNS = [
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

CLEAR_SOURCE_COLUMNS = [
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
    "transaction_amount",
    "fee_amount",
    "net_amount",
    "currency",
    "status",
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

CLEAR_COLUMNS = [
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

EXPECTED_BRANCHES: dict[str, tuple[str | None, str | None, str]] = {
    "F2001": (None, None, "AUTO_FIXED"),
    "F2003": ("AMOUNT_MISMATCH", "BE-R002", "PENDING_HUMAN"),
    "F2004": ("NARRATIVE_NAME_MISMATCH", "BE-R004", "PENDING_HUMAN"),
    "F2005": ("BANK_UNARRIVED", "BE-R005", "PENDING_HUMAN"),
    "F2006": ("BOOK_UNRECORDED", "BE-R006", "PENDING_HUMAN"),
    "F2007": ("DUPLICATE_BOOKING", "BE-R008", "PENDING_HUMAN"),
    "F2008": ("DUPLICATE_BOOKING", "BE-R008", "PENDING_HUMAN"),
}

BANK_CLEARING_EXPECTED_BRANCHES: dict[str, tuple[str | None, str | None, str]] = {
    "BC3001": (None, None, "AUTO_FIXED"),
    "BC3002": ("CLEARING_SINGLE_SIDE", "BC-R001", "PENDING_HUMAN"),
    "BC3003": ("CUTOFF_CROSS_DAY", "BC-R003", "PENDING_HUMAN"),
    "BC3004": ("CUTOFF_CROSS_DAY", "BC-R003", "PENDING_HUMAN"),
    "CORE3003": ("UNCLASSIFIED", None, "PENDING_HUMAN"),
}


def _reset_mock_faker() -> None:
    Faker.seed(MOCK_FAKER_SEED)
    MOCK_FAKER.seed_instance(MOCK_FAKER_SEED)


def _faker_value(field: str) -> str:
    if field not in FAKER_FILLABLE_FIELDS:
        raise ValueError(f"{field} is not faker-fillable")
    if field in {"self_bank_name", "counterparty_bank_name"}:
        return f"{MOCK_FAKER.city_name()}银行{MOCK_FAKER.city_name()}分行"
    if field == "store_name":
        return f"{MOCK_FAKER.street_name()}门店"
    if field == "terminal_id":
        return MOCK_FAKER.bothify(text="T####")
    raise ValueError(f"no faker generator for {field}")


def _enrich_bank_dataframe(bank_df: pd.DataFrame) -> pd.DataFrame:
    """补充标准化字段和真实银行流水常见字段，保留原始字段用于审计回溯。"""
    bank_df = bank_df.copy()
    bank_df["transaction_direction"] = bank_df.apply(
        lambda row: "CREDIT" if row["credit_amount"] > 0 else "DEBIT",
        axis=1,
    )
    bank_df["amount"] = bank_df[["debit_amount", "credit_amount"]].max(axis=1)
    bank_df["fee_amount"] = bank_df["transaction_type"].map(lambda value: 2.00 if value == "FEE" else 0.00)
    bank_df["trade_time"] = bank_df["accounting_date"].astype(str) + " " + bank_df["accounting_time"].astype(str)
    bank_df["account_no_masked"] = bank_df["self_account_no_masked"]
    bank_df["customer_name_masked"] = bank_df["self_account_name_masked"]
    bank_df["posting_status"] = "POSTED"
    bank_df["branch_no"] = "SH001"
    bank_df["teller_id"] = bank_df["channel"].map(
        {
            "柜面": "TELLER_021",
            "网上银行": "E_BANK",
            "手机银行": "M_BANK",
            "批量系统": "BATCH_SYS",
            "清算平台": "CLEARING_SYS",
        }
    ).fillna("SYSTEM")
    bank_df["transaction_code"] = bank_df["transaction_type"].map(
        {
            "TRANSFER_IN": "TRF_IN",
            "TRANSFER_OUT": "TRF_OUT",
            "BATCH_PAYROLL": "BATCH_PAY",
            "FEE": "FEE_DEBIT",
            "REFUND": "REFUND_IN",
        }
    ).fillna("OTHER")
    bank_df["source_system"] = bank_df["channel"].map(
        {
            "柜面": "CORE_COUNTER",
            "网上银行": "E_BANKING",
            "手机银行": "MOBILE_BANKING",
            "批量系统": "BATCH_PAYMENT",
            "清算平台": "CLEARING_PLATFORM",
        }
    ).fillna("CORE_BANKING")
    extra_columns = [
        column
        for column in ("voucher_no", "reference_no", "merchant_order_no")
        if column in bank_df.columns
    ]
    return bank_df[BANK_COLUMNS + extra_columns]


def _enrich_clear_dataframe(clear_df: pd.DataFrame) -> pd.DataFrame:
    """补充与 PRD 入库模型一致的标准字段，同时保留清算侧原始业务字段。"""
    clear_df = clear_df.copy()
    clear_df["amount"] = clear_df["transaction_amount"]
    clear_df["summary"] = clear_df["order_description"]
    return clear_df[CLEAR_COLUMNS]


def _reset_batch_faker(seed: int) -> Faker:
    Faker.seed(seed)
    faker = Faker("zh_CN")
    faker.seed_instance(seed)
    return faker


def _bank_name(faker: Faker) -> str:
    return f"{faker.city_name()}银行{faker.city_name()}分行"


def _masked_account(index: int) -> str:
    return f"6214********{index:04d}"


def _normal_bank_enterprise_rows(
    *,
    faker: Faker,
    n_normal: int,
    flow_prefix: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    bank_rows: list[dict[str, object]] = []
    clear_rows: list[dict[str, object]] = []
    for index in range(1, n_normal + 1):
        flow_id = f"{flow_prefix}{index:04d}"
        amount = round(80 + index * 17.35, 2)
        day = 1 + (index % 10)
        hour = 9 + (index % 8)
        minute = (index * 7) % 60
        trade_date = f"2026-06-{day:02d}"
        accounting_time = f"{hour:02d}:{minute:02d}:00"
        clear_time = f"{hour:02d}:{minute:02d}:05"
        counterparty_name = faker.company()
        counterparty_account = _masked_account(3000 + index)
        summary = sample_narrative("formal" if index % 2 else "colloquial", faker)
        is_credit = index % 3 != 0
        debit_amount = 0.00 if is_credit else amount
        credit_amount = amount if is_credit else 0.00

        bank_rows.append(
            _bank_enterprise_bank_row(
                flow_id=flow_id,
                serial=f"B202606{index:06d}",
                accounting_date=trade_date,
                accounting_time=accounting_time,
                transaction_type="TRANSFER_IN" if is_credit else "TRANSFER_OUT",
                debit_amount=debit_amount,
                credit_amount=credit_amount,
                balance_after=10000 + index * 100 + credit_amount - debit_amount,
                counterparty_account=counterparty_account,
                counterparty_name=counterparty_name,
                counterparty_bank_name=_bank_name(faker),
                channel="网上银行" if index % 2 else "手机银行",
                summary=summary,
                purpose="货款" if is_credit else "费用",
                remark="批次正常自动平账样例",
            )
        )
        clear_rows.append(
            _bank_enterprise_clear_row(
                flow_id=flow_id,
                serial=f"C202606{index:06d}",
                store_name=f"{faker.street_name()}门店",
                terminal_id=faker.bothify(text="T####"),
                trade_date=trade_date,
                trade_time=clear_time,
                transaction_amount=amount,
                batch_no=f"BAT202606{index:04d}",
                voucher_no=f"VCH{index:04d}",
                reference_no=f"REF202606{index:06d}",
                order_no=f"ORD202606{index:06d}",
                payer_account=counterparty_account if is_credit else "6222********0001",
                payer_name=counterparty_name if is_credit else "上海晨星贸易有限公司",
                payee_account="6222********0001" if is_credit else counterparty_account,
                payee_name="上海晨星贸易有限公司" if is_credit else counterparty_name,
                description=summary,
                remark="批次正常自动平账样例",
            )
        )
    return bank_rows, clear_rows


def _bank_enterprise_anomaly_rows(
    *,
    faker: Faker,
    flow_prefix: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    bank_rows = [
        _bank_enterprise_bank_row(
            flow_id=f"{flow_prefix}2001",
            serial="B202606010001",
            accounting_time="09:00:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=128.00,
            balance_after=10128.00,
            counterparty_account="6214********2001",
            counterparty_name=faker.company(),
            counterparty_bank_name=_bank_name(faker),
            channel="网上银行",
            summary=sample_narrative("formal", faker),
            purpose="货款",
            remark="批次自动平账哨兵样例",
        ),
        _bank_enterprise_bank_row(
            flow_id=f"{flow_prefix}2003",
            serial="B202606010003",
            accounting_time="10:10:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=300.00,
            balance_after=10339.50,
            counterparty_account="6214********2003",
            counterparty_name="南京北辰供应链有限公司",
            counterparty_bank_name=_bank_name(faker),
            channel="清算平台",
            summary=sample_narrative("ambiguous", faker),
            purpose="货款",
            remark="MVP-1 金额不一致样例",
        ),
        _bank_enterprise_bank_row(
            flow_id=f"{flow_prefix}2004",
            serial="B202606010004",
            accounting_time="11:20:00",
            transaction_type="REFUND",
            debit_amount=0.00,
            credit_amount=66.60,
            balance_after=10406.10,
            counterparty_account="6214********2004",
            counterparty_name="宁波星河电子有限公司",
            counterparty_bank_name=_bank_name(faker),
            channel="清算平台",
            summary="退款",
            purpose="订单退款",
            remark="MVP-1 摘要客户名不一致样例",
        ),
        _bank_enterprise_bank_row(
            flow_id=f"{flow_prefix}2006",
            serial="B202606010006",
            accounting_time="14:10:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=45.00,
            balance_after=10451.10,
            counterparty_account="6214********2006",
            counterparty_name="苏州东海制造有限公司",
            counterparty_bank_name=_bank_name(faker),
            channel="网上银行",
            summary=sample_narrative("ambiguous", faker),
            purpose="预收款",
            remark="MVP-1 银行有企业无样例",
        ),
        _bank_enterprise_bank_row(
            flow_id=f"{flow_prefix}2007",
            serial="B202606010007",
            accounting_time="15:00:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=199.99,
            balance_after=10651.09,
            counterparty_account="6214********2007",
            counterparty_name="杭州青禾商贸有限公司",
            counterparty_bank_name=_bank_name(faker),
            channel="网上银行",
            summary=sample_narrative("ambiguous", faker),
            purpose="服务费",
            remark="MVP-1 疑似重复入账样例",
        ),
        _bank_enterprise_bank_row(
            flow_id=f"{flow_prefix}2008",
            serial="B202606010008",
            accounting_time="15:02:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=199.99,
            balance_after=10851.08,
            counterparty_account="6214********2008",
            counterparty_name="杭州青禾商贸有限公司",
            counterparty_bank_name=_bank_name(faker),
            channel="网上银行",
            summary=sample_narrative("ambiguous", faker),
            purpose="服务费",
            remark="MVP-1 疑似重复入账样例",
        ),
    ]
    clear_rows = [
        _bank_enterprise_clear_row(
            flow_id=f"{flow_prefix}2001",
            serial="C202606010001",
            terminal_id="T2001",
            trade_time="09:00:05",
            transaction_amount=128.00,
            batch_no="BAT2026060101",
            voucher_no="VCH2001",
            reference_no="REF202606010001",
            order_no="ORD202606010001",
            payer_account="6214********2001",
            payer_name=bank_rows[0]["counterparty_name_masked"],
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description=bank_rows[0]["summary"],
            remark="批次自动平账哨兵样例",
            store_name=f"{faker.street_name()}门店",
            terminal_id_generated=faker.bothify(text="T####"),
        ),
        _bank_enterprise_clear_row(
            flow_id=f"{flow_prefix}2003",
            serial="C202606010003",
            terminal_id="T2003",
            trade_time="10:10:05",
            transaction_amount=295.00,
            batch_no="BAT2026060102",
            voucher_no="VCH2003",
            reference_no="REF202606010003",
            order_no="ORD202606010003",
            payer_account="6214********2003",
            payer_name="南京北辰供应链有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description=bank_rows[1]["summary"],
            remark="MVP-1 金额不一致样例",
            store_name=f"{faker.street_name()}门店",
            terminal_id_generated=faker.bothify(text="T####"),
        ),
        _bank_enterprise_clear_row(
            flow_id=f"{flow_prefix}2004",
            serial="C202606010004",
            terminal_id="T2004",
            trade_time="11:20:05",
            transaction_amount=66.60,
            batch_no="BAT2026060102",
            voucher_no="VCH2004",
            reference_no="REF202606010004",
            order_no="ORD202606010004",
            payer_account="6214********2004",
            payer_name="宁波星河电子有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description=sample_narrative("formal", faker),
            remark="MVP-1 摘要客户名不一致样例",
            store_name=f"{faker.street_name()}门店",
            terminal_id_generated=faker.bothify(text="T####"),
        ),
        _bank_enterprise_clear_row(
            flow_id=f"{flow_prefix}2005",
            serial="C202606010005",
            terminal_id="T2005",
            trade_time="13:30:05",
            transaction_amount=72.00,
            batch_no="BAT2026060103",
            voucher_no="VCH2005",
            reference_no="REF202606010005",
            order_no="ORD202606010005",
            payer_account="6214********2005",
            payer_name="广州南岭服务有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description=sample_narrative("ambiguous", faker),
            remark="MVP-1 企业有银行无样例",
            store_name=f"{faker.street_name()}门店",
            terminal_id_generated=faker.bothify(text="T####"),
        ),
        _bank_enterprise_clear_row(
            flow_id=f"{flow_prefix}2007",
            serial="C202606010007",
            terminal_id="T2007",
            trade_time="15:00:05",
            transaction_amount=199.99,
            batch_no="BAT2026060104",
            voucher_no="VCH2007",
            reference_no="REF202606010007",
            order_no="ORD202606010007",
            payer_account="6214********2007",
            payer_name="杭州青禾商贸有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description=bank_rows[4]["summary"],
            remark="MVP-1 疑似重复入账样例",
            store_name=f"{faker.street_name()}门店",
            terminal_id_generated=faker.bothify(text="T####"),
        ),
    ]
    return bank_rows, clear_rows


def build_batch(
    scenario: str = "bank_enterprise",
    *,
    n_normal: int = DEFAULT_BANK_ENTERPRISE_NORMAL_ROWS,
    seed: int = MOCK_FAKER_SEED,
    flow_prefix: str = "F",
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, tuple[str | None, str | None, str]]]:
    if scenario != "bank_enterprise":
        raise ValueError(f"unsupported scenario: {scenario}")

    faker = _reset_batch_faker(seed)
    bank_rows, clear_rows = _normal_bank_enterprise_rows(
        faker=faker,
        n_normal=n_normal,
        flow_prefix=flow_prefix,
    )
    anomaly_bank_rows, anomaly_clear_rows = _bank_enterprise_anomaly_rows(
        faker=faker,
        flow_prefix=flow_prefix,
    )
    bank_rows.extend(anomaly_bank_rows)
    clear_rows.extend(anomaly_clear_rows)

    expected = {
        f"{flow_prefix}{flow_id[1:]}": branch
        for flow_id, branch in EXPECTED_BRANCHES.items()
    }
    return (
        _enrich_bank_dataframe(pd.DataFrame(bank_rows, columns=BANK_SOURCE_COLUMNS)),
        _enrich_clear_dataframe(pd.DataFrame(clear_rows, columns=CLEAR_SOURCE_COLUMNS)),
        expected,
    )


def _bank_enterprise_bank_row(
    *,
    flow_id: str,
    serial: str,
    accounting_time: str,
    transaction_type: str,
    debit_amount: float,
    credit_amount: float,
    balance_after: float,
    counterparty_account: str,
    counterparty_name: str,
    counterparty_bank_name: str,
    channel: str,
    summary: str,
    purpose: str,
    remark: str,
    accounting_date: str = "2026-06-01",
) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "bank_serial_no": serial,
        "accounting_date": accounting_date,
        "accounting_time": accounting_time,
        "value_date": accounting_date,
        "self_account_no_masked": "6222********0001",
        "self_account_name_masked": "上海晨星贸易有限公司",
        "self_bank_name": "上海银行浦东分行",
        "currency": "CNY",
        "transaction_type": transaction_type,
        "debit_amount": debit_amount,
        "credit_amount": credit_amount,
        "balance_after": balance_after,
        "counterparty_account_no_masked": counterparty_account,
        "counterparty_name_masked": counterparty_name,
        "counterparty_bank_name": counterparty_bank_name,
        "channel": channel,
        "summary": summary,
        "purpose": purpose,
        "remark": remark,
    }


def _bank_enterprise_clear_row(
    *,
    flow_id: str,
    serial: str,
    terminal_id: str,
    trade_time: str,
    transaction_amount: float,
    batch_no: str,
    voucher_no: str,
    reference_no: str,
    order_no: str,
    payer_account: str,
    payer_name: str,
    payee_account: str,
    payee_name: str,
    description: str,
    remark: str,
    store_name: str = "批次门店",
    terminal_id_generated: str | None = None,
    trade_date: str = "2026-06-01",
) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "clearing_serial_no": serial,
        "merchant_id": "M1000001",
        "merchant_name": "上海晨星贸易有限公司",
        "store_name": store_name,
        "terminal_id": terminal_id_generated or terminal_id,
        "channel": "ONLINE_BANKING",
        "transaction_type": "PAYMENT",
        "trade_date": trade_date,
        "trade_time": trade_time,
        "settlement_date": trade_date,
        "transaction_amount": transaction_amount,
        "fee_amount": 0.00,
        "net_amount": transaction_amount,
        "currency": "CNY",
        "status": "SUCCESS",
        "batch_no": batch_no,
        "voucher_no": voucher_no,
        "reference_no": reference_no,
        "merchant_order_no": order_no,
        "payer_account_no_masked": payer_account,
        "payer_name_masked": payer_name,
        "payee_account_no_masked": payee_account,
        "payee_name_masked": payee_name,
        "order_description": description,
        "remark": remark,
    }


def _write_excel_pair(
    output_dir: str | Path,
    bank_filename: str,
    clear_filename: str,
    bank_df: pd.DataFrame,
    clear_df: pd.DataFrame,
) -> tuple[Path, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    bank_path = output_path / bank_filename
    clear_path = output_path / clear_filename
    bank_df.to_excel(bank_path, index=False)
    clear_df.to_excel(clear_path, index=False)
    return bank_path, clear_path


def generate_mock_excel(output_dir: str | Path = "mock_data") -> tuple[Path, Path]:
    """生成银行端和清算端模拟 Excel，为上传解析和后续对账测试提供固定样本。"""
    bank_df, clear_df, _expected = build_batch(
        n_normal=DEFAULT_BANK_ENTERPRISE_NORMAL_ROWS,
        flow_prefix="F1",
    )
    return _write_excel_pair(
        output_dir,
        "bank_transactions.xlsx",
        "clear_transactions.xlsx",
        bank_df,
        clear_df,
    )

    _reset_mock_faker()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    bank_rows = [
        [
            "F1001",
            "B202605210001",
            "2026-05-21",
            "09:10:00",
            "2026-05-21",
            "6222********0001",
            "上海晨星贸易有限公司",
            _faker_value("self_bank_name"),
            "CNY",
            "TRANSFER_IN",
            0.00,
            100.00,
            10100.00,
            "6214********1001",
            "上海云杉科技有限公司",
            _faker_value("counterparty_bank_name"),
            "网上银行",
            "网银转账",
            "货款",
            "正常平账样例",
        ],
        [
            "F1002",
            "B202605210002",
            "2026-05-21",
            "10:20:00",
            "2026-05-21",
            "6222********0001",
            "上海晨星贸易有限公司",
            _faker_value("self_bank_name"),
            "CNY",
            "TRANSFER_IN",
            0.00,
            250.50,
            10350.50,
            "6214********1002",
            "杭州青禾商贸有限公司",
            _faker_value("counterparty_bank_name"),
            "柜面",
            "柜面入账",
            "服务费",
            "正常平账样例",
        ],
        [
            "F1003",
            "B202605210003",
            "2026-05-21",
            "11:30:00",
            "2026-05-21",
            "6222********0001",
            "上海晨星贸易有限公司",
            _faker_value("self_bank_name"),
            "CNY",
            "BATCH_PAYROLL",
            88.80,
            0.00,
            10261.70,
            "6214********1003",
            "员工代发虚拟户",
            _faker_value("counterparty_bank_name"),
            "批量系统",
            "批量代发",
            "代发工资",
            "正常平账样例",
        ],
        [
            "F1004",
            "B202605210004",
            "2026-05-21",
            "13:40:00",
            "2026-05-21",
            "6222********0001",
            "上海晨星贸易有限公司",
            _faker_value("self_bank_name"),
            "CNY",
            "TRANSFER_IN",
            0.00,
            300.00,
            10561.70,
            "6214********1004",
            "南京北辰供应链有限公司",
            _faker_value("counterparty_bank_name"),
            "清算平台",
            "清算金额差异",
            "货款",
            "金额差错样例",
        ],
        [
            "F1005",
            "B202605210005",
            "2026-05-21",
            "15:00:00",
            "2026-05-21",
            "6222********0001",
            "上海晨星贸易有限公司",
            _faker_value("self_bank_name"),
            "CNY",
            "TRANSFER_IN",
            0.00,
            120.00,
            10681.70,
            "6214********1005",
            "苏州东海制造有限公司",
            _faker_value("counterparty_bank_name"),
            "网上银行",
            "银行端单边账",
            "预收款",
            "银行端存在清算端缺失",
        ],
        [
            "F1008",
            "B202605210008",
            "2026-05-21",
            "17:05:00",
            "2026-05-21",
            "6222********0001",
            "上海晨星贸易有限公司",
            _faker_value("self_bank_name"),
            "CNY",
            "TRANSFER_OUT",
            35.20,
            0.00,
            10646.50,
            "6214********1008",
            "上海浦江物流有限公司",
            _faker_value("counterparty_bank_name"),
            "网上银行",
            "网银付款",
            "物流费",
            "正常平账样例",
        ],
        [
            "F1009",
            "B202605210009",
            "2026-05-21",
            "17:20:00",
            "2026-05-21",
            "6222********0001",
            "上海晨星贸易有限公司",
            _faker_value("self_bank_name"),
            "CNY",
            "FEE",
            2.00,
            0.00,
            10644.50,
            "6214********1009",
            "清算服务费虚拟户",
            _faker_value("counterparty_bank_name"),
            "清算平台",
            "手续费扣收",
            "渠道手续费",
            "正常平账样例",
        ],
        [
            "F1010",
            "B202605210010",
            "2026-05-21",
            "17:45:00",
            "2026-05-21",
            "6222********0001",
            "上海晨星贸易有限公司",
            _faker_value("self_bank_name"),
            "CNY",
            "TRANSFER_IN",
            0.00,
            510.00,
            11154.50,
            "6214********1010",
            "无锡云帆材料有限公司",
            _faker_value("counterparty_bank_name"),
            "网上银行",
            "跨行转账收入",
            "材料款",
            "正常平账样例",
        ],
        [
            "F1011",
            "B202605210011",
            "2026-05-21",
            "18:05:00",
            "2026-05-21",
            "6222********0001",
            "上海晨星贸易有限公司",
            _faker_value("self_bank_name"),
            "CNY",
            "REFUND",
            0.00,
            18.80,
            11173.30,
            "6214********1011",
            "上海云杉科技有限公司",
            _faker_value("counterparty_bank_name"),
            "清算平台",
            "退款入账",
            "订单退款",
            "正常平账样例",
        ],
        [
            "F1007",
            "B202605210007",
            "2026-05-21",
            "16:30:00",
            "2026-05-21",
            "6222********0001",
            "上海晨星贸易有限公司",
            _faker_value("self_bank_name"),
            "CNY",
            "TRANSFER_IN",
            0.00,
            66.60,
            10748.30,
            "6214********1007",
            "宁波星河电子有限公司",
            _faker_value("counterparty_bank_name"),
            "手机银行",
            "正常转账",
            "零星收款",
            "正常平账样例",
        ],
    ]
    clear_rows = [
        [
            "F1001",
            "C202605210001",
            "M1000001",
            "上海晨星贸易有限公司",
            _faker_value("store_name"),
            _faker_value("terminal_id"),
            "ONLINE_BANKING",
            "PAYMENT",
            "2026-05-21",
            "09:10:05",
            "2026-05-21",
            100.00,
            0.00,
            100.00,
            "CNY",
            "SUCCESS",
            "BAT2026052101",
            "VCH0001",
            "REF202605210001",
            "ORD202605210001",
            "6214********1001",
            "上海云杉科技有限公司",
            "6222********0001",
            "上海晨星贸易有限公司",
            "网银转账",
            "正常平账样例",
        ],
        [
            "F1002",
            "C202605210002",
            "M1000001",
            "上海晨星贸易有限公司",
            _faker_value("store_name"),
            _faker_value("terminal_id"),
            "COUNTER",
            "PAYMENT",
            "2026-05-21",
            "10:20:05",
            "2026-05-21",
            250.50,
            0.00,
            250.50,
            "CNY",
            "SUCCESS",
            "BAT2026052101",
            "VCH0002",
            "REF202605210002",
            "ORD202605210002",
            "6214********1002",
            "杭州青禾商贸有限公司",
            "6222********0001",
            "上海晨星贸易有限公司",
            "柜面入账",
            "正常平账样例",
        ],
        [
            "F1003",
            "C202605210003",
            "M1000001",
            "上海晨星贸易有限公司",
            _faker_value("store_name"),
            _faker_value("terminal_id"),
            "BATCH",
            "PAYROLL",
            "2026-05-21",
            "11:30:05",
            "2026-05-21",
            88.80,
            0.00,
            88.80,
            "CNY",
            "SUCCESS",
            "BAT2026052102",
            "VCH0003",
            "REF202605210003",
            "ORD202605210003",
            "6222********0001",
            "上海晨星贸易有限公司",
            "6214********1003",
            "员工代发虚拟户",
            "批量代发",
            "正常平账样例",
        ],
        [
            "F1004",
            "C202605210004",
            "M1000001",
            "上海晨星贸易有限公司",
            _faker_value("store_name"),
            _faker_value("terminal_id"),
            "CLEARING",
            "PAYMENT",
            "2026-05-21",
            "13:40:05",
            "2026-05-21",
            295.00,
            0.00,
            295.00,
            "CNY",
            "SUCCESS",
            "BAT2026052102",
            "VCH0004",
            "REF202605210004",
            "ORD202605210004",
            "6214********1004",
            "南京北辰供应链有限公司",
            "6222********0001",
            "上海晨星贸易有限公司",
            "清算金额差异",
            "金额差错样例",
        ],
        [
            "F1006",
            "C202605210006",
            "M1000001",
            "上海晨星贸易有限公司",
            _faker_value("store_name"),
            _faker_value("terminal_id"),
            "CLEARING",
            "PAYMENT",
            "2026-05-21",
            "15:30:05",
            "2026-05-21",
            45.00,
            0.00,
            45.00,
            "CNY",
            "SUCCESS",
            "BAT2026052103",
            "VCH0006",
            "REF202605210006",
            "ORD202605210006",
            "6214********1006",
            "广州南岭服务有限公司",
            "6222********0001",
            "上海晨星贸易有限公司",
            "清算端单边账",
            "清算端存在银行端缺失",
        ],
        [
            "F1008",
            "C202605210008",
            "M1000001",
            "上海晨星贸易有限公司",
            _faker_value("store_name"),
            _faker_value("terminal_id"),
            "ONLINE_BANKING",
            "PAYMENT",
            "2026-05-21",
            "17:05:05",
            "2026-05-21",
            35.20,
            0.00,
            35.20,
            "CNY",
            "SUCCESS",
            "BAT2026052104",
            "VCH0008",
            "REF202605210008",
            "ORD202605210008",
            "6222********0001",
            "上海晨星贸易有限公司",
            "6214********1008",
            "上海浦江物流有限公司",
            "网银付款",
            "正常平账样例",
        ],
        [
            "F1009",
            "C202605210009",
            "M1000001",
            "上海晨星贸易有限公司",
            _faker_value("store_name"),
            _faker_value("terminal_id"),
            "CLEARING",
            "FEE",
            "2026-05-21",
            "17:20:05",
            "2026-05-21",
            2.00,
            0.00,
            2.00,
            "CNY",
            "SUCCESS",
            "BAT2026052104",
            "VCH0009",
            "REF202605210009",
            "ORD202605210009",
            "6222********0001",
            "上海晨星贸易有限公司",
            "6214********1009",
            "清算服务费虚拟户",
            "手续费扣收",
            "正常平账样例",
        ],
        [
            "F1010",
            "C202605210010",
            "M1000001",
            "上海晨星贸易有限公司",
            _faker_value("store_name"),
            _faker_value("terminal_id"),
            "ONLINE_BANKING",
            "PAYMENT",
            "2026-05-21",
            "17:45:05",
            "2026-05-21",
            510.00,
            0.00,
            510.00,
            "CNY",
            "SUCCESS",
            "BAT2026052105",
            "VCH0010",
            "REF202605210010",
            "ORD202605210010",
            "6214********1010",
            "无锡云帆材料有限公司",
            "6222********0001",
            "上海晨星贸易有限公司",
            "跨行转账收入",
            "正常平账样例",
        ],
        [
            "F1011",
            "C202605210011",
            "M1000001",
            "上海晨星贸易有限公司",
            _faker_value("store_name"),
            _faker_value("terminal_id"),
            "CLEARING",
            "REFUND",
            "2026-05-21",
            "18:05:05",
            "2026-05-21",
            18.80,
            0.00,
            18.80,
            "CNY",
            "SUCCESS",
            "BAT2026052105",
            "VCH0011",
            "REF202605210011",
            "ORD202605210011",
            "6214********1011",
            "上海云杉科技有限公司",
            "6222********0001",
            "上海晨星贸易有限公司",
            "退款入账",
            "正常平账样例",
        ],
        [
            "F1007",
            "C202605210007",
            "M1000001",
            "上海晨星贸易有限公司",
            _faker_value("store_name"),
            _faker_value("terminal_id"),
            "MOBILE_BANKING",
            "PAYMENT",
            "2026-05-21",
            "16:30:05",
            "2026-05-21",
            66.60,
            0.00,
            66.60,
            "CNY",
            "SUCCESS",
            "BAT2026052103",
            "VCH0007",
            "REF202605210007",
            "ORD202605210007",
            "6214********1007",
            "宁波星河电子有限公司",
            "6222********0001",
            "上海晨星贸易有限公司",
            "正常转账",
            "正常平账样例",
        ],
    ]

    bank_path = output_path / "bank_transactions.xlsx"
    clear_path = output_path / "clear_transactions.xlsx"

    bank_df = _enrich_bank_dataframe(pd.DataFrame(bank_rows, columns=BANK_SOURCE_COLUMNS))
    clear_df = _enrich_clear_dataframe(pd.DataFrame(clear_rows, columns=CLEAR_SOURCE_COLUMNS))
    clear_df["trade_time"] = clear_df["trade_date"].astype(str) + " " + clear_df["trade_time"].astype(str)

    bank_df.to_excel(bank_path, index=False)
    clear_df.to_excel(clear_path, index=False)

    return bank_path, clear_path


def generate_mvp1_mock_excel(
    output_dir: str | Path = "mock_data",
    *,
    include_fuzzy_sample: bool = False,
) -> tuple[Path, Path]:
    """生成覆盖 MVP-1 五分支的银企对账 mock，返回 (bank_path, clear_path)。"""
    bank_df, clear_df, _expected = build_batch(
        n_normal=DEFAULT_BANK_ENTERPRISE_NORMAL_ROWS,
        flow_prefix="F",
    )
    if include_fuzzy_sample:
        fuzzy_bank = _enrich_bank_dataframe(
            pd.DataFrame(
                [
                    _bank_enterprise_bank_row(
                        flow_id="F2009-BANK",
                        serial="B202606010009",
                        accounting_time="16:00:00",
                        transaction_type="TRANSFER_OUT",
                        debit_amount=55.55,
                        credit_amount=0.00,
                        balance_after=10795.53,
                        counterparty_account="6214********2009",
                        counterparty_name="无锡远帆设备有限公司",
                        counterparty_bank_name="上海银行浦东分行",
                        channel="网上银行",
                        summary=sample_narrative("formal", _reset_batch_faker(MOCK_FAKER_SEED + 1)),
                        purpose="设备款",
                        remark="MVP-1 flow_id 不一致候选匹配样例",
                    )
                ],
                columns=BANK_SOURCE_COLUMNS,
            )
        )
        fuzzy_clear = _enrich_clear_dataframe(
            pd.DataFrame(
                [
                    _bank_enterprise_clear_row(
                        flow_id="F2009-CLEAR",
                        serial="C202606010009",
                        terminal_id="T2009",
                        trade_time="16:00:05",
                        transaction_amount=55.55,
                        batch_no="BAT2026060105",
                        voucher_no="VCH2009",
                        reference_no="REF202606010009",
                        order_no="ORD202606010009",
                        payer_account="6222********0001",
                        payer_name="上海晨星贸易有限公司",
                        payee_account="6214********2009",
                        payee_name="无锡远帆设备有限公司",
                        description=fuzzy_bank["summary"].iloc[0],
                        remark="MVP-1 flow_id 不一致候选匹配样例",
                    )
                ],
                columns=CLEAR_SOURCE_COLUMNS,
            )
        )
        bank_df = pd.concat([bank_df, fuzzy_bank], ignore_index=True)
        clear_df = pd.concat([clear_df, fuzzy_clear], ignore_index=True)

    return _write_excel_pair(
        output_dir,
        "mvp1_bank.xlsx",
        "mvp1_clear.xlsx",
        bank_df,
        clear_df,
    )

    _reset_mock_faker()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    bank_rows = [
        _bank_source_row(
            flow_id="F2001",
            serial="B202606010001",
            accounting_time="09:00:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=128.00,
            balance_after=10128.00,
            counterparty_account="6214********2001",
            counterparty_name="上海云杉科技有限公司",
            channel="网上银行",
            summary="网银转账",
            purpose="货款",
            remark="MVP-1 自动平账样例",
        ),
        _bank_source_row(
            flow_id="F2002",
            serial="B202606010002",
            accounting_time="09:30:00",
            transaction_type="TRANSFER_OUT",
            debit_amount=88.50,
            credit_amount=0.00,
            balance_after=10039.50,
            counterparty_account="6214********2002",
            counterparty_name="上海浦江物流有限公司",
            channel="网上银行",
            summary="网银付款",
            purpose="物流费",
            remark="MVP-1 自动平账样例",
        ),
        _bank_source_row(
            flow_id="F2003",
            serial="B202606010003",
            accounting_time="10:10:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=300.00,
            balance_after=10339.50,
            counterparty_account="6214********2003",
            counterparty_name="南京北辰供应链有限公司",
            channel="清算平台",
            summary="清算金额差异",
            purpose="货款",
            remark="MVP-1 金额不一致样例",
        ),
        _bank_source_row(
            flow_id="F2004",
            serial="B202606010004",
            accounting_time="11:20:00",
            transaction_type="REFUND",
            debit_amount=0.00,
            credit_amount=66.60,
            balance_after=10406.10,
            counterparty_account="6214********2004",
            counterparty_name="宁波星河电子有限公司",
            channel="清算平台",
            summary="退款入账",
            purpose="订单退款",
            remark="MVP-1 摘要客户名不一致样例",
        ),
        _bank_source_row(
            flow_id="F2006",
            serial="B202606010006",
            accounting_time="14:10:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=45.00,
            balance_after=10451.10,
            counterparty_account="6214********2006",
            counterparty_name="苏州东海制造有限公司",
            channel="网上银行",
            summary="银行端单边账",
            purpose="预收款",
            remark="MVP-1 银行有企业无样例",
        ),
        _bank_source_row(
            flow_id="F2007",
            serial="B202606010007",
            accounting_time="15:00:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=199.99,
            balance_after=10651.09,
            counterparty_account="6214********2007",
            counterparty_name="杭州青禾商贸有限公司",
            channel="网上银行",
            summary="重复入账检测",
            purpose="服务费",
            remark="MVP-1 疑似重复入账样例",
        ),
        _bank_source_row(
            flow_id="F2008",
            serial="B202606010008",
            accounting_time="15:02:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=199.99,
            balance_after=10851.08,
            counterparty_account="6214********2008",
            counterparty_name="杭州青禾商贸有限公司",
            channel="网上银行",
            summary="重复入账检测",
            purpose="服务费",
            remark="MVP-1 疑似重复入账样例",
        ),
    ]
    clear_rows = [
        _clear_source_row(
            flow_id="F2001",
            serial="C202606010001",
            terminal_id="T2001",
            trade_time="09:00:05",
            transaction_amount=128.00,
            batch_no="BAT2026060101",
            voucher_no="VCH2001",
            reference_no="REF202606010001",
            order_no="ORD202606010001",
            payer_account="6214********2001",
            payer_name="上海云杉科技有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description="网银转账",
            remark="MVP-1 自动平账样例",
        ),
        _clear_source_row(
            flow_id="F2002",
            serial="C202606010002",
            terminal_id="T2002",
            trade_time="09:30:05",
            transaction_amount=88.50,
            batch_no="BAT2026060101",
            voucher_no="VCH2002",
            reference_no="REF202606010002",
            order_no="ORD202606010002",
            payer_account="6222********0001",
            payer_name="上海晨星贸易有限公司",
            payee_account="6214********2002",
            payee_name="上海浦江物流有限公司",
            description="网银付款",
            remark="MVP-1 自动平账样例",
        ),
        _clear_source_row(
            flow_id="F2003",
            serial="C202606010003",
            terminal_id="T2003",
            trade_time="10:10:05",
            transaction_amount=295.00,
            batch_no="BAT2026060102",
            voucher_no="VCH2003",
            reference_no="REF202606010003",
            order_no="ORD202606010003",
            payer_account="6214********2003",
            payer_name="南京北辰供应链有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description="清算金额差异",
            remark="MVP-1 金额不一致样例",
        ),
        _clear_source_row(
            flow_id="F2004",
            serial="C202606010004",
            terminal_id="T2004",
            trade_time="11:20:05",
            transaction_amount=66.60,
            batch_no="BAT2026060102",
            voucher_no="VCH2004",
            reference_no="REF202606010004",
            order_no="ORD202606010004",
            payer_account="6214********2004",
            payer_name="宁波星河电子有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description="正常转账",
            remark="MVP-1 摘要客户名不一致样例",
        ),
        _clear_source_row(
            flow_id="F2005",
            serial="C202606010005",
            terminal_id="T2005",
            trade_time="13:30:05",
            transaction_amount=72.00,
            batch_no="BAT2026060103",
            voucher_no="VCH2005",
            reference_no="REF202606010005",
            order_no="ORD202606010005",
            payer_account="6214********2005",
            payer_name="广州南岭服务有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description="企业账簿单边账",
            remark="MVP-1 企业有银行无样例",
        ),
        _clear_source_row(
            flow_id="F2007",
            serial="C202606010007",
            terminal_id="T2007",
            trade_time="15:00:05",
            transaction_amount=199.99,
            batch_no="BAT2026060104",
            voucher_no="VCH2007",
            reference_no="REF202606010007",
            order_no="ORD202606010007",
            payer_account="6214********2007",
            payer_name="杭州青禾商贸有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description="重复入账检测",
            remark="MVP-1 疑似重复入账样例",
        ),
    ]

    if include_fuzzy_sample:
        bank_rows.append(
            _bank_source_row(
                flow_id="F2009-BANK",
                serial="B202606010009",
                accounting_time="16:00:00",
                transaction_type="TRANSFER_OUT",
                debit_amount=55.55,
                credit_amount=0.00,
                balance_after=10795.53,
                counterparty_account="6214********2009",
                counterparty_name="无锡远帆设备有限公司",
                channel="网上银行",
                summary="网银付款",
                purpose="设备款",
                remark="MVP-1 flow_id 不一致候选匹配样例",
            )
        )
        clear_rows.append(
            _clear_source_row(
                flow_id="F2009-CLEAR",
                serial="C202606010009",
                terminal_id="T2009",
                trade_time="16:00:05",
                transaction_amount=55.55,
                batch_no="BAT2026060105",
                voucher_no="VCH2009",
                reference_no="REF202606010009",
                order_no="ORD202606010009",
                payer_account="6222********0001",
                payer_name="上海晨星贸易有限公司",
                payee_account="6214********2009",
                payee_name="无锡远帆设备有限公司",
                description="网银付款",
                remark="MVP-1 flow_id 不一致候选匹配样例",
            )
        )

    bank_path = output_path / "mvp1_bank.xlsx"
    clear_path = output_path / "mvp1_clear.xlsx"

    bank_df = _enrich_bank_dataframe(pd.DataFrame(bank_rows, columns=BANK_SOURCE_COLUMNS))
    clear_df = _enrich_clear_dataframe(pd.DataFrame(clear_rows, columns=CLEAR_SOURCE_COLUMNS))

    bank_df.to_excel(bank_path, index=False)
    clear_df.to_excel(clear_path, index=False)

    return bank_path, clear_path


def generate_mvp2a3_mock_excel(output_dir: str | Path = "mock_data") -> tuple[Path, Path]:
    """生成覆盖清算副链路最小闭环的 mock，返回 (core_path, clearing_path)。"""
    _reset_mock_faker()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    bank_rows = [
        _bank_source_row(
            flow_id="BC3001",
            serial="B202606100001",
            accounting_date="2026-06-10",
            value_date="2026-06-10",
            accounting_time="10:00:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=88.80,
            balance_after=20088.80,
            counterparty_account="6214********3001",
            counterparty_name="杭州清河商贸有限公司",
            channel="清算平台",
            summary="清算正常配平",
            purpose="门店收款",
            remark="MVP-2a3 正常配平样例",
        ),
        _bank_source_row(
            flow_id="CORE3003",
            serial="B202606110003",
            accounting_date="2026-06-11",
            value_date="2026-06-11",
            accounting_time="09:05:00",
            transaction_type="TRANSFER_IN",
            debit_amount=0.00,
            credit_amount=150.00,
            balance_after=20238.80,
            counterparty_account="6214********3003",
            counterparty_name="苏州清源零售有限公司",
            channel="清算平台",
            summary="跨日切 T+1 核心补记",
            purpose="门店收款",
            remark="MVP-2a3 跨日切命中样例",
            voucher_no="VCH3003",
            reference_no="REF3003",
            merchant_order_no="ORD3003",
        ),
    ]

    clear_rows = [
        _clear_source_row(
            flow_id="BC3001",
            serial="C202606100001",
            trade_date="2026-06-10",
            settlement_date="2026-06-10",
            terminal_id="T3001",
            trade_time="10:00:00",
            transaction_amount=88.80,
            batch_no="BAT2026061001",
            voucher_no="VCH3001",
            reference_no="REF3001",
            order_no="ORD3001",
            payer_account="6214********3001",
            payer_name="杭州清河商贸有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description="清算正常配平",
            remark="MVP-2a3 正常配平样例",
        ),
        _clear_source_row(
            flow_id="BC3002",
            serial="C202606100002",
            trade_date="2026-06-10",
            settlement_date="2026-06-10",
            terminal_id="T3002",
            trade_time="10:00:00",
            transaction_amount=66.60,
            batch_no="BAT2026061001",
            voucher_no="VCH3002",
            reference_no="REF3002",
            order_no="ORD3002",
            payer_account="6214********3002",
            payer_name="宁波清越服务有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description="清算端日间单边",
            remark="MVP-2a3 BC-R001 样例",
        ),
        _clear_source_row(
            flow_id="BC3003",
            serial="C202606100003",
            trade_date="2026-06-10",
            settlement_date="2026-06-10",
            terminal_id="T3003",
            trade_time="23:30",
            transaction_amount=150.00,
            batch_no="BAT2026061002",
            voucher_no="VCH3003",
            reference_no="REF3003",
            order_no="ORD3003",
            payer_account="6214********3003",
            payer_name="苏州清源零售有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description="清算端跨日切可追溯",
            remark="MVP-2a3 BC-R003 命中样例",
        ),
        _clear_source_row(
            flow_id="BC3004",
            serial="C202606100004",
            trade_date="2026-06-10",
            settlement_date="2026-06-10",
            terminal_id="T3004",
            trade_time="23:45",
            transaction_amount=175.50,
            batch_no="BAT2026061002",
            voucher_no="VCH3004",
            reference_no="REF3004",
            order_no="ORD3004",
            payer_account="6214********3004",
            payer_name="绍兴清禾餐饮有限公司",
            payee_account="6222********0001",
            payee_name="上海晨星贸易有限公司",
            description="清算端跨日切待补齐",
            remark="MVP-2a3 BC-R003 待补齐样例",
        ),
    ]

    bank_path = output_path / "mvp2a3_core.xlsx"
    clear_path = output_path / "mvp2a3_clearing.xlsx"

    bank_df = _enrich_bank_dataframe(pd.DataFrame(bank_rows))
    clear_df = _enrich_clear_dataframe(pd.DataFrame(clear_rows))

    bank_df.to_excel(bank_path, index=False)
    clear_df.to_excel(clear_path, index=False)

    return bank_path, clear_path


def _bank_source_row(
    *,
    flow_id: str,
    serial: str,
    accounting_date: str = "2026-06-01",
    value_date: str = "2026-06-01",
    accounting_time: str,
    transaction_type: str,
    debit_amount: float,
    credit_amount: float,
    balance_after: float,
    counterparty_account: str,
    counterparty_name: str,
    channel: str,
    summary: str,
    purpose: str,
    remark: str,
    voucher_no: str | None = None,
    reference_no: str | None = None,
    merchant_order_no: str | None = None,
) -> dict[str, object]:
    _reset_mock_faker()
    row = {
        "flow_id": flow_id,
        "bank_serial_no": serial,
        "accounting_date": accounting_date,
        "accounting_time": accounting_time,
        "value_date": value_date,
        "self_account_no_masked": "6222********0001",
        "self_account_name_masked": "上海晨星贸易有限公司",
        "self_bank_name": _faker_value("self_bank_name"),
        "currency": "CNY",
        "transaction_type": transaction_type,
        "debit_amount": debit_amount,
        "credit_amount": credit_amount,
        "balance_after": balance_after,
        "counterparty_account_no_masked": counterparty_account,
        "counterparty_name_masked": counterparty_name,
        "counterparty_bank_name": _faker_value("counterparty_bank_name"),
        "channel": channel,
        "summary": summary,
        "purpose": purpose,
        "remark": remark,
    }
    if voucher_no is not None:
        row["voucher_no"] = voucher_no
    if reference_no is not None:
        row["reference_no"] = reference_no
    if merchant_order_no is not None:
        row["merchant_order_no"] = merchant_order_no
    return row


def _clear_source_row(
    *,
    flow_id: str,
    serial: str,
    trade_date: str = "2026-06-01",
    settlement_date: str = "2026-06-01",
    terminal_id: str,
    trade_time: str,
    transaction_amount: float,
    batch_no: str,
    voucher_no: str,
    reference_no: str,
    order_no: str,
    payer_account: str,
    payer_name: str,
    payee_account: str,
    payee_name: str,
    description: str,
    remark: str,
) -> dict[str, object]:
    _reset_mock_faker()
    return {
        "flow_id": flow_id,
        "clearing_serial_no": serial,
        "merchant_id": "M1000001",
        "merchant_name": "上海晨星贸易有限公司",
        "store_name": _faker_value("store_name"),
        "terminal_id": _faker_value("terminal_id"),
        "channel": "ONLINE_BANKING",
        "transaction_type": "PAYMENT",
        "trade_date": trade_date,
        "trade_time": trade_time,
        "settlement_date": settlement_date,
        "transaction_amount": transaction_amount,
        "fee_amount": 0.00,
        "net_amount": transaction_amount,
        "currency": "CNY",
        "status": "SUCCESS",
        "batch_no": batch_no,
        "voucher_no": voucher_no,
        "reference_no": reference_no,
        "merchant_order_no": order_no,
        "payer_account_no_masked": payer_account,
        "payer_name_masked": payer_name,
        "payee_account_no_masked": payee_account,
        "payee_name_masked": payee_name,
        "order_description": description,
        "remark": remark,
    }


if __name__ == "__main__":
    bank_file, clear_file = generate_mock_excel()
    mvp1_bank_file, mvp1_clear_file = generate_mvp1_mock_excel()
    mvp2a3_bank_file, mvp2a3_clear_file = generate_mvp2a3_mock_excel()
    print(f"Generated {bank_file}")
    print(f"Generated {clear_file}")
    print(f"Generated {mvp1_bank_file}")
    print(f"Generated {mvp1_clear_file}")
    print(f"Generated {mvp2a3_bank_file}")
    print(f"Generated {mvp2a3_clear_file}")

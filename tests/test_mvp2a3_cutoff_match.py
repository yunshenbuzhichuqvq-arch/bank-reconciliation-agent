from datetime import date
from decimal import Decimal

import pandas as pd

from bank_reconciliation_agent.services.exception_router import ExceptionRouter


def _core_row(
    flow_id: str,
    amount: str,
    *,
    accounting_date: object,
    reference_no: str | None = None,
    merchant_order_no: str | None = None,
    voucher_no: str | None = None,
) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "amount": Decimal(amount),
        "summary": "核心流水",
        "accounting_date": accounting_date,
        "reference_no": reference_no,
        "merchant_order_no": merchant_order_no,
        "voucher_no": voucher_no,
    }


def _clearing_row(
    flow_id: str,
    amount: str,
    *,
    trade_time: str = "23:30",
    trade_date: object = "2026-06-09",
    reference_no: str | None = None,
    merchant_order_no: str | None = None,
    voucher_no: str | None = None,
) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "amount": Decimal(amount),
        "summary": "清算流水",
        "trade_time": trade_time,
        "trade_date": trade_date,
        "payer_name_masked": f"付款方-{flow_id}",
        "payee_name_masked": f"收款方-{flow_id}",
        "reference_no": reference_no,
        "merchant_order_no": merchant_order_no,
        "voucher_no": voucher_no,
    }


def test_bank_clearing_bc_r003_attaches_t1_candidate_when_amount_reference_and_date_match() -> None:
    bank_df = pd.DataFrame(
        [
            _core_row(
                "CORE_T1",
                "100.00",
                accounting_date=date(2026, 6, 10),
                reference_no="REF-100",
            )
        ]
    )
    clear_df = pd.DataFrame(
        [_clearing_row("CLEAR_CUTOFF", "100.00", reference_no="REF-100")]
    )

    results = {
        result.flow_id: result
        for result in ExceptionRouter().classify(
            bank_df,
            clear_df,
            scenario_type="BANK_CLEARING",
        )
    }

    assert results["CLEAR_CUTOFF"].exception_branch == "BC-R003"
    assert results["CLEAR_CUTOFF"].t1_candidate == {
        "flow_id": "CORE_T1",
        "accounting_date": "2026-06-10",
    }


def test_bank_clearing_bc_r003_keeps_candidate_empty_when_match_conditions_fail() -> None:
    bank_df = pd.DataFrame(
        [
            _core_row(
                "CORE_BAD_REF",
                "100.00",
                accounting_date="2026-06-10",
                reference_no="REF-OTHER",
            ),
            _core_row(
                "CORE_BAD_AMOUNT",
                "99.99",
                accounting_date="2026-06-10",
                merchant_order_no="ORDER-100",
            ),
            _core_row(
                "CORE_BAD_DATE",
                "100.00",
                accounting_date="2026-06-11",
                voucher_no="VOUCHER-100",
            ),
        ]
    )
    clear_df = pd.DataFrame(
        [
            _clearing_row(
                "CLEAR_BAD_REF",
                "100.00",
                reference_no="REF-100",
            ),
            _clearing_row(
                "CLEAR_BAD_AMOUNT",
                "100.00",
                merchant_order_no="ORDER-100",
            ),
            _clearing_row(
                "CLEAR_BAD_DATE",
                "100.00",
                voucher_no="VOUCHER-100",
            ),
        ]
    )

    results = {
        result.flow_id: result
        for result in ExceptionRouter().classify(
            bank_df,
            clear_df,
            scenario_type="BANK_CLEARING",
        )
    }

    assert results["CLEAR_BAD_REF"].exception_branch == "BC-R003"
    assert results["CLEAR_BAD_REF"].t1_candidate is None
    assert results["CLEAR_BAD_AMOUNT"].exception_branch == "BC-R003"
    assert results["CLEAR_BAD_AMOUNT"].t1_candidate is None
    assert results["CLEAR_BAD_DATE"].exception_branch == "BC-R003"
    assert results["CLEAR_BAD_DATE"].t1_candidate is None

from decimal import Decimal

import pandas as pd

from bank_reconciliation_agent.services.exception_router import ExceptionRouter


def _bank_row(
    flow_id: str,
    amount: str,
    *,
    summary: str = "正常入账",
    counterparty_name_masked: str = "交易对手",
) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "amount": Decimal(amount),
        "summary": summary,
        "counterparty_name_masked": counterparty_name_masked,
    }


def _clear_row(
    flow_id: str,
    amount: str,
    *,
    summary: str = "正常入账",
    payee_name_masked: str = "交易对手",
) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "amount": Decimal(amount),
        "summary": summary,
        "payee_name_masked": payee_name_masked,
    }


def test_exception_router_classifies_auto_fix_and_five_exception_branches() -> None:
    bank_df = pd.DataFrame(
        [
            _bank_row("AUTO", "100.00"),
            _bank_row("AMOUNT", "120.00"),
            _bank_row("NARRATIVE", "130.00", summary="订单退款"),
            _bank_row("BOOK_ONLY", "140.00"),
            _bank_row("DUP_MATCHED", "150.00", counterparty_name_masked="重复客户"),
            _bank_row("DUP_BANK_ONLY", "150.00", counterparty_name_masked="重复客户"),
        ]
    )
    clear_df = pd.DataFrame(
        [
            _clear_row("AUTO", "100.00"),
            _clear_row("AMOUNT", "119.99"),
            _clear_row("NARRATIVE", "130.00", summary="正常入账"),
            _clear_row("BANK_UNARRIVED", "160.00"),
            _clear_row("DUP_MATCHED", "150.00", payee_name_masked="重复客户"),
        ]
    )

    results = {result.flow_id: result for result in ExceptionRouter().classify(bank_df, clear_df)}

    assert results["AUTO"].action == "AUTO_FIX"
    assert results["AUTO"].error_type is None
    assert results["AUTO"].exception_branch is None
    assert results["AUTO"].amount_diff == Decimal("0.00")

    assert results["AMOUNT"].action == "EXCEPTION"
    assert results["AMOUNT"].error_type == "AMOUNT_MISMATCH"
    assert results["AMOUNT"].exception_branch == "BE-R002"
    assert results["AMOUNT"].amount_diff == Decimal("0.01")

    assert results["NARRATIVE"].error_type == "NARRATIVE_NAME_MISMATCH"
    assert results["NARRATIVE"].exception_branch == "BE-R004"

    assert results["BANK_UNARRIVED"].error_type == "BANK_UNARRIVED"
    assert results["BANK_UNARRIVED"].exception_branch == "BE-R005"
    assert results["BANK_UNARRIVED"].bank_amount is None
    assert results["BANK_UNARRIVED"].clear_amount == Decimal("160.00")

    assert results["BOOK_ONLY"].error_type == "BOOK_UNRECORDED"
    assert results["BOOK_ONLY"].exception_branch == "BE-R006"
    assert results["BOOK_ONLY"].bank_amount == Decimal("140.00")
    assert results["BOOK_ONLY"].clear_amount is None

    assert results["DUP_MATCHED"].error_type == "DUPLICATE_BOOKING"
    assert results["DUP_MATCHED"].exception_branch == "BE-R008"
    assert results["DUP_BANK_ONLY"].error_type == "DUPLICATE_BOOKING"
    assert results["DUP_BANK_ONLY"].exception_branch == "BE-R008"


def test_exception_router_detects_clear_side_duplicates() -> None:
    bank_df = pd.DataFrame([_bank_row("DUP_CLEAR_MATCHED", "90.00")])
    clear_df = pd.DataFrame(
        [
            _clear_row("DUP_CLEAR_MATCHED", "90.00", payee_name_masked="重复收款方"),
            _clear_row("DUP_CLEAR_ONLY", "90.00", payee_name_masked="重复收款方"),
        ]
    )

    results = {result.flow_id: result for result in ExceptionRouter().classify(bank_df, clear_df)}

    assert results["DUP_CLEAR_MATCHED"].error_type == "DUPLICATE_BOOKING"
    assert results["DUP_CLEAR_MATCHED"].exception_branch == "BE-R008"
    assert results["DUP_CLEAR_ONLY"].error_type == "DUPLICATE_BOOKING"
    assert results["DUP_CLEAR_ONLY"].exception_branch == "BE-R008"

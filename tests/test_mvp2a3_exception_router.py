from decimal import Decimal

import pandas as pd

from bank_reconciliation_agent.core.config import Settings
from bank_reconciliation_agent.services.exception_router import ExceptionRouter


def _bank_row(flow_id: str, amount: str) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "amount": Decimal(amount),
        "summary": "核心流水",
        "counterparty_name_masked": "企业客户",
        "trade_time": "10:00",
    }


def _clearing_row(
    flow_id: str,
    amount: str,
    *,
    trade_time: str,
    payer_name_masked: str | None = None,
    payee_name_masked: str | None = None,
) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "amount": Decimal(amount),
        "summary": "清算流水",
        "trade_time": trade_time,
        "payer_name_masked": payer_name_masked or f"付款方-{flow_id}",
        "payee_name_masked": payee_name_masked or f"收款方-{flow_id}",
    }


def test_bank_enterprise_classify_remains_unchanged_with_explicit_scenario() -> None:
    bank_df = pd.DataFrame([_bank_row("BOOK_ONLY", "140.00")])
    clear_df = pd.DataFrame([_clearing_row("BANK_UNARRIVED", "160.00", trade_time="10:00")])

    results = {
        result.flow_id: result
        for result in ExceptionRouter().classify(
            bank_df,
            clear_df,
            scenario_type="BANK_ENTERPRISE",
        )
    }

    assert results["BANK_UNARRIVED"].error_type == "BANK_UNARRIVED"
    assert results["BANK_UNARRIVED"].exception_branch == "BE-R005"
    assert results["BOOK_ONLY"].error_type == "BOOK_UNRECORDED"
    assert results["BOOK_ONLY"].exception_branch == "BE-R006"


def test_bank_clearing_classifies_cutoff_and_single_side() -> None:
    bank_df = pd.DataFrame([])
    clear_df = pd.DataFrame(
        [
            _clearing_row("CUT_OFF", "100.00", trade_time="23:30"),
            _clearing_row("DAY_TIME", "120.00", trade_time="10:00"),
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

    assert results["CUT_OFF"].error_type == "CUTOFF_CROSS_DAY"
    assert results["CUT_OFF"].exception_branch == "BC-R003"
    assert results["DAY_TIME"].error_type == "CLEARING_SINGLE_SIDE"
    assert results["DAY_TIME"].exception_branch == "BC-R001"


def test_bank_clearing_cutoff_window_boundary_is_start_inclusive_end_exclusive() -> None:
    bank_df = pd.DataFrame([])
    clear_df = pd.DataFrame(
        [
            _clearing_row("BEFORE", "100.00", trade_time="21:59"),
            _clearing_row("START", "100.00", trade_time="22:00"),
            _clearing_row("END_MINUS_ONE", "100.00", trade_time="23:59"),
            _clearing_row("END", "100.00", trade_time="00:00"),
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

    assert results["BEFORE"].exception_branch == "BC-R001"
    assert results["START"].exception_branch == "BC-R003"
    assert results["END_MINUS_ONE"].exception_branch == "BC-R003"
    assert results["END"].exception_branch == "BC-R001"


def test_settings_support_cutoff_window_override() -> None:
    settings = Settings(cutoff_window="21:00-23:00")

    assert settings.cutoff_window == "21:00-23:00"

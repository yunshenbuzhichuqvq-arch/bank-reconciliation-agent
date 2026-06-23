from decimal import Decimal

import pandas as pd

from bank_reconciliation_agent.services.exception_router import ExceptionRouter
from scripts.generate_mock_excel import generate_mvp1_mock_excel


def _bank_row(
    flow_id: str,
    amount: str,
    *,
    trade_date: str = "2026-06-01",
    counterparty: str = "上海云杉科技有限公司",
) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "amount": Decimal(amount),
        "trade_time": f"{trade_date} 09:00:00",
        "accounting_date": trade_date,
        "summary": "正常入账",
        "counterparty_name_masked": counterparty,
    }


def _clear_row(
    flow_id: str,
    amount: str,
    *,
    trade_date: str = "2026-06-01",
    counterparty: str = "上海云杉科技",
) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "amount": Decimal(amount),
        "trade_time": f"{trade_date} 09:00:05",
        "trade_date": trade_date,
        "summary": "正常入账",
        "payee_name_masked": counterparty,
    }


def test_unique_cross_flow_candidate_marks_both_sides() -> None:
    results = {
        result.flow_id: result
        for result in ExceptionRouter().classify(
            pd.DataFrame([_bank_row("BANK-001", "128.00")]),
            pd.DataFrame([_clear_row("CLEAR-001", "128.00")]),
        )
    }

    bank_result = results["BANK-001"]
    clear_result = results["CLEAR-001"]
    assert (bank_result.action, bank_result.error_type, bank_result.exception_branch) == (
        "EXCEPTION",
        "FUZZY_MATCH_CANDIDATE",
        "BE-R007",
    )
    assert bank_result.fuzzy_candidate == {
        "flow_id": "CLEAR-001",
        "amount": "128.00",
        "trade_date": "2026-06-01",
        "counterparty": "上海云杉科技",
    }
    assert clear_result.fuzzy_candidate == {
        "flow_id": "BANK-001",
        "amount": "128.00",
        "trade_date": "2026-06-01",
        "counterparty": "上海云杉科技有限公司",
    }


def test_ambiguous_candidates_remain_single_sided() -> None:
    results = {
        result.flow_id: result
        for result in ExceptionRouter().classify(
            pd.DataFrame([_bank_row("BANK-001", "128.00")]),
            pd.DataFrame(
                [
                    _clear_row("CLEAR-001", "128.00"),
                    _clear_row("CLEAR-002", "128.00", counterparty="云杉科技有限公司"),
                ]
            ),
        )
    }

    assert results["BANK-001"].error_type == "BOOK_UNRECORDED"
    assert results["CLEAR-001"].error_type == "BANK_UNARRIVED"
    assert results["CLEAR-002"].error_type == "BANK_UNARRIVED"
    assert all(result.fuzzy_candidate is None for result in results.values())


def test_exact_match_and_true_single_sides_are_unchanged() -> None:
    results = {
        result.flow_id: result
        for result in ExceptionRouter().classify(
            pd.DataFrame(
                [
                    _bank_row("EXACT", "100.00"),
                    _bank_row("BANK-ONLY", "45.00", counterparty="无关银行对手方"),
                ]
            ),
            pd.DataFrame(
                [
                    _clear_row("EXACT", "100.00"),
                    _clear_row("CLEAR-ONLY", "72.00", counterparty="无关企业对手方"),
                ]
            ),
        )
    }

    assert results["EXACT"].action == "AUTO_FIX"
    assert results["BANK-ONLY"].error_type == "BOOK_UNRECORDED"
    assert results["CLEAR-ONLY"].error_type == "BANK_UNARRIVED"


def test_mvp1_mock_contains_fuzzy_pair_and_true_single_sides(tmp_path) -> None:
    bank_path, clear_path = generate_mvp1_mock_excel(tmp_path, include_fuzzy_sample=True)
    bank_df = pd.read_excel(bank_path)
    clear_df = pd.read_excel(clear_path)
    results = {
        result.flow_id: result for result in ExceptionRouter().classify(bank_df, clear_df)
    }

    assert results["F2009-BANK"].error_type == "FUZZY_MATCH_CANDIDATE"
    assert results["F2009-CLEAR"].error_type == "FUZZY_MATCH_CANDIDATE"
    assert results["F2005"].error_type == "BANK_UNARRIVED"
    assert results["F2006"].error_type == "BOOK_UNRECORDED"

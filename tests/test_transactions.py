from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from bank_reconciliation_agent.services.transactions import TransactionService


def test_to_datetime_uses_date_hint_for_hh_mm_time_text() -> None:
    result = TransactionService()._to_datetime("23:30", date_hint=date(2026, 5, 21))

    assert result == datetime(2026, 5, 21, 23, 30)


def test_to_datetime_uses_date_hint_for_hh_mm_ss_time_text() -> None:
    result = TransactionService()._to_datetime("10:00:05", date_hint="2026-05-21")

    assert result == datetime(2026, 5, 21, 10, 0, 5)


def test_to_datetime_keeps_full_datetime_text_behavior() -> None:
    result = TransactionService()._to_datetime("2026-05-21 09:10:00")

    assert result == datetime(2026, 5, 21, 9, 10, 0)


def test_to_datetime_raises_for_time_text_without_date_hint() -> None:
    with pytest.raises(ValueError):
        TransactionService()._to_datetime("23:30")


def _bank_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "flow_id": "CORE_T1",
                "amount": Decimal("100.00"),
                "debit_amount": Decimal("0.00"),
                "credit_amount": Decimal("100.00"),
                "trade_time": datetime(2026, 6, 11, 10, 0, 0),
                "accounting_date": date(2026, 6, 11),
                "reference_no": "REF-100",
                "merchant_order_no": "ORD-100",
                "voucher_no": "VCH-100",
            }
        ]
    )


def _clear_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "flow_id": "CLEAR_CUTOFF",
                "amount": Decimal("100.00"),
                "transaction_amount": Decimal("100.00"),
                "net_amount": Decimal("100.00"),
                "trade_time": datetime(2026, 6, 10, 23, 30, 0),
                "trade_date": date(2026, 6, 10),
            }
        ]
    )


def test_bank_t1_reference_fields_are_persisted_and_read_back() -> None:
    service = TransactionService()
    service.replace_task_rows(
        user_id="u_ref",
        task_id="T_REF",
        bank_df=_bank_df(),
        clear_df=_clear_df(),
    )

    row = service.get_bank_row(user_id="u_ref", task_id="T_REF", flow_id="CORE_T1")

    assert row is not None
    assert row["reference_no"] == "REF-100"
    assert row["merchant_order_no"] == "ORD-100"
    assert row["voucher_no"] == "VCH-100"


def test_list_bank_rows_is_scoped_to_user_and_task() -> None:
    service = TransactionService()
    service.replace_task_rows(
        user_id="u_a", task_id="T_LIST", bank_df=_bank_df(), clear_df=_clear_df()
    )
    service.replace_task_rows(
        user_id="u_b", task_id="T_LIST", bank_df=_bank_df(), clear_df=_clear_df()
    )

    rows_a = service.list_bank_rows(user_id="u_a", task_id="T_LIST")

    assert [row["flow_id"] for row in rows_a] == ["CORE_T1"]
    assert service.list_bank_rows(user_id="u_a", task_id="OTHER") == []


def test_flow_belongs_to_task_checks_both_sides_with_tenant_scope() -> None:
    service = TransactionService()
    service.replace_task_rows(
        user_id="u_own", task_id="T_OWN", bank_df=_bank_df(), clear_df=_clear_df()
    )

    assert service.flow_belongs_to_task(user_id="u_own", task_id="T_OWN", flow_id="CORE_T1") is True
    assert (
        service.flow_belongs_to_task(user_id="u_own", task_id="T_OWN", flow_id="CLEAR_CUTOFF")
        is True
    )
    assert service.flow_belongs_to_task(user_id="u_own", task_id="T_OWN", flow_id="GHOST") is False
    assert (
        service.flow_belongs_to_task(user_id="intruder", task_id="T_OWN", flow_id="CORE_T1")
        is False
    )

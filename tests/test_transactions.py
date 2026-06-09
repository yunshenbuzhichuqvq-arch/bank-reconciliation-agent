from datetime import date, datetime

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

import pandas as pd
from pandas.testing import assert_frame_equal

from bank_reconciliation_agent.services.reconciliation import ReconciliationService
from scripts.generate_mock_excel import (
    BANK_CLEARING_EXPECTED_BRANCHES,
    DEFAULT_BANK_CLEARING_NORMAL_ROWS,
    DEFAULT_BANK_ENTERPRISE_NORMAL_ROWS,
    EXPECTED_BRANCHES,
    build_batch,
)


def _results_by_flow_id(
    bank_df: pd.DataFrame,
    clear_df: pd.DataFrame,
    *,
    scenario_type: str,
) -> dict[str, object]:
    results = ReconciliationService()._build_match_results(
        bank_df,
        clear_df,
        scenario_type=scenario_type,
    )
    return {result.flow_id: result for result in results}


def test_bank_enterprise_normal_rows_are_auto_fixed() -> None:
    bank_df, clear_df, expected = build_batch(
        scenario="bank_enterprise",
        n_normal=DEFAULT_BANK_ENTERPRISE_NORMAL_ROWS,
    )

    results = _results_by_flow_id(bank_df, clear_df, scenario_type="BANK_ENTERPRISE")
    normal_flow_ids = set(results) - set(expected)

    assert len(normal_flow_ids) == DEFAULT_BANK_ENTERPRISE_NORMAL_ROWS
    assert all(results[flow_id].status == "AUTO_FIXED" for flow_id in normal_flow_ids)


def test_bank_clearing_normal_rows_are_auto_fixed() -> None:
    bank_df, clear_df, expected = build_batch(
        scenario="bank_clearing",
        n_normal=DEFAULT_BANK_CLEARING_NORMAL_ROWS,
    )

    results = _results_by_flow_id(bank_df, clear_df, scenario_type="BANK_CLEARING")
    normal_flow_ids = set(results) - set(expected)

    assert len(normal_flow_ids) == DEFAULT_BANK_CLEARING_NORMAL_ROWS
    assert all(results[flow_id].status == "AUTO_FIXED" for flow_id in normal_flow_ids)


def test_mock_batch_exception_counts_match_expected_branches() -> None:
    bank_df, clear_df, expected = build_batch(
        scenario="bank_enterprise",
        n_normal=DEFAULT_BANK_ENTERPRISE_NORMAL_ROWS,
    )
    clearing_bank_df, clearing_clear_df, clearing_expected = build_batch(
        scenario="bank_clearing",
        n_normal=DEFAULT_BANK_CLEARING_NORMAL_ROWS,
    )

    results = _results_by_flow_id(bank_df, clear_df, scenario_type="BANK_ENTERPRISE")
    clearing_results = _results_by_flow_id(
        clearing_bank_df,
        clearing_clear_df,
        scenario_type="BANK_CLEARING",
    )

    assert expected == EXPECTED_BRANCHES
    assert clearing_expected == BANK_CLEARING_EXPECTED_BRANCHES
    assert set(expected) <= set(results)
    assert set(clearing_expected) <= set(clearing_results)
    assert sum(result.status == "PENDING_HUMAN" for result in results.values()) == sum(
        disposition == "PENDING_HUMAN"
        for _error_type, _exception_branch, disposition in expected.values()
    )
    assert sum(result.status == "PENDING_HUMAN" for result in clearing_results.values()) == sum(
        disposition == "PENDING_HUMAN"
        for _error_type, _exception_branch, disposition in clearing_expected.values()
    )


def test_mock_batches_keep_field_diversity() -> None:
    bank_df, clear_df, _expected = build_batch(
        scenario="bank_enterprise",
        n_normal=DEFAULT_BANK_ENTERPRISE_NORMAL_ROWS,
    )
    clearing_bank_df, clearing_clear_df, _clearing_expected = build_batch(
        scenario="bank_clearing",
        n_normal=DEFAULT_BANK_CLEARING_NORMAL_ROWS,
    )

    assert bank_df["counterparty_name_masked"].nunique() > 1
    assert bank_df["summary"].nunique() > 1
    assert clear_df["store_name"].nunique() > 1
    assert clear_df["terminal_id"].nunique() > 1
    assert clearing_bank_df["counterparty_name_masked"].nunique() > 1
    assert clearing_bank_df["summary"].nunique() > 1
    assert clearing_clear_df["store_name"].nunique() > 1
    assert clearing_clear_df["terminal_id"].nunique() > 1


def test_build_batch_is_deterministic_for_same_seed() -> None:
    first_bank_df, first_clear_df, first_expected = build_batch(
        scenario="bank_enterprise",
        n_normal=DEFAULT_BANK_ENTERPRISE_NORMAL_ROWS,
        seed=20260624,
    )
    second_bank_df, second_clear_df, second_expected = build_batch(
        scenario="bank_enterprise",
        n_normal=DEFAULT_BANK_ENTERPRISE_NORMAL_ROWS,
        seed=20260624,
    )
    first_clearing_bank_df, first_clearing_clear_df, first_clearing_expected = build_batch(
        scenario="bank_clearing",
        n_normal=DEFAULT_BANK_CLEARING_NORMAL_ROWS,
        seed=20260624,
    )
    second_clearing_bank_df, second_clearing_clear_df, second_clearing_expected = build_batch(
        scenario="bank_clearing",
        n_normal=DEFAULT_BANK_CLEARING_NORMAL_ROWS,
        seed=20260624,
    )

    assert_frame_equal(first_bank_df, second_bank_df)
    assert_frame_equal(first_clear_df, second_clear_df)
    assert first_expected == second_expected
    assert_frame_equal(first_clearing_bank_df, second_clearing_bank_df)
    assert_frame_equal(first_clearing_clear_df, second_clearing_clear_df)
    assert first_clearing_expected == second_clearing_expected

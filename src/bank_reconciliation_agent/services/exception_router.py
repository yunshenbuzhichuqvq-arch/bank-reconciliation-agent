from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import NamedTuple

import pandas as pd

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.services.rule_engine import rule_engine_for


REVERSAL_KEYWORDS = {"冲正", "红冲", "退款", "抹账", "撤销"}


class BranchResult(NamedTuple):
    flow_id: str
    action: str
    error_type: str | None
    exception_branch: str | None
    bank_amount: Decimal | None
    clear_amount: Decimal | None
    amount_diff: Decimal | None
    t1_candidate: dict[str, str] | None = None
    fuzzy_candidate: dict[str, str] | None = None


class ExceptionRouter:
    def classify(
        self,
        bank_df: pd.DataFrame,
        clear_df: pd.DataFrame,
        *,
        scenario_type: str = "BANK_ENTERPRISE",
    ) -> list[BranchResult]:
        bank_by_flow_id = self._rows_by_flow_id(bank_df)
        clear_by_flow_id = self._rows_by_flow_id(clear_df)
        bank_duplicates = self._duplicate_flow_ids(
            bank_df,
            party_column=self._bank_party_column(scenario_type),
        )
        clear_duplicates = self._duplicate_flow_ids(
            clear_df,
            party_column=self._clear_party_column(scenario_type),
        )
        rule_engine = rule_engine_for(scenario_type)

        results: list[BranchResult] = []
        for flow_id in sorted(bank_by_flow_id.keys() | clear_by_flow_id.keys()):
            bank_row = bank_by_flow_id.get(flow_id)
            clear_row = clear_by_flow_id.get(flow_id)
            bank_amount = self._amount_from_row(bank_row)
            clear_amount = self._amount_from_row(clear_row)

            facts = {
                "flow_matched": bank_row is not None and clear_row is not None,
                "amount_equal": bank_amount == clear_amount
                if bank_amount is not None and clear_amount is not None
                else False,
                "present_side": self._present_side(bank_row, clear_row),
                "narrative_or_name_mismatch": self._has_narrative_mismatch(
                    bank_row,
                    clear_row,
                    bank_amount,
                    clear_amount,
                ),
                "duplicate_suspected": flow_id in bank_duplicates or flow_id in clear_duplicates,
            }
            if scenario_type == "BANK_CLEARING":
                facts["in_cutoff_window"] = self._in_cutoff_window(clear_row)
            match = rule_engine.evaluate(facts)
            t1_candidate = None
            if (
                scenario_type == "BANK_CLEARING"
                and match.exception_branch == "BC-R003"
                and clear_row is not None
            ):
                t1_candidate = self._find_t1_candidate(clear_row, bank_df)
            results.append(
                BranchResult(
                    flow_id=flow_id,
                    action=match.action,
                    error_type=match.error_type,
                    exception_branch=match.exception_branch,
                    bank_amount=bank_amount,
                    clear_amount=clear_amount,
                    amount_diff=self._amount_diff(bank_amount, clear_amount),
                    t1_candidate=t1_candidate,
                )
            )

        return self._apply_fuzzy_match(
            results,
            bank_by_flow_id,
            clear_by_flow_id,
            scenario_type=scenario_type,
        )

    def _apply_fuzzy_match(
        self,
        results: list[BranchResult],
        bank_by_flow_id: dict[str, dict[str, object]],
        clear_by_flow_id: dict[str, dict[str, object]],
        *,
        scenario_type: str,
    ) -> list[BranchResult]:
        if scenario_type != "BANK_ENTERPRISE":
            return results

        results_by_flow_id = {result.flow_id: result for result in results}
        bank_only = [
            flow_id
            for flow_id, result in results_by_flow_id.items()
            if result.error_type == "BOOK_UNRECORDED"
        ]
        clear_only = [
            flow_id
            for flow_id, result in results_by_flow_id.items()
            if result.error_type == "BANK_UNARRIVED"
        ]
        candidates_by_bank = {
            bank_flow_id: [
                clear_flow_id
                for clear_flow_id in clear_only
                if self._is_fuzzy_match(
                    bank_by_flow_id[bank_flow_id],
                    clear_by_flow_id[clear_flow_id],
                    scenario_type=scenario_type,
                )
            ]
            for bank_flow_id in bank_only
        }
        candidates_by_clear = {
            clear_flow_id: [
                bank_flow_id
                for bank_flow_id in bank_only
                if clear_flow_id in candidates_by_bank[bank_flow_id]
            ]
            for clear_flow_id in clear_only
        }

        for bank_flow_id, clear_candidates in candidates_by_bank.items():
            if len(clear_candidates) != 1:
                continue
            clear_flow_id = clear_candidates[0]
            if len(candidates_by_clear[clear_flow_id]) != 1:
                continue
            bank_row = bank_by_flow_id[bank_flow_id]
            clear_row = clear_by_flow_id[clear_flow_id]
            results_by_flow_id[bank_flow_id] = results_by_flow_id[bank_flow_id]._replace(
                error_type="FUZZY_MATCH_CANDIDATE",
                exception_branch="BE-R007",
                fuzzy_candidate=self._fuzzy_candidate(
                    clear_row,
                    party_column=self._clear_party_column(scenario_type),
                ),
            )
            results_by_flow_id[clear_flow_id] = results_by_flow_id[clear_flow_id]._replace(
                error_type="FUZZY_MATCH_CANDIDATE",
                exception_branch="BE-R007",
                fuzzy_candidate=self._fuzzy_candidate(
                    bank_row,
                    party_column=self._bank_party_column(scenario_type),
                ),
            )

        return [results_by_flow_id[result.flow_id] for result in results]

    def _is_fuzzy_match(
        self,
        bank_row: dict[str, object],
        clear_row: dict[str, object],
        *,
        scenario_type: str,
    ) -> bool:
        bank_party = self._normalize_summary(
            bank_row.get(self._bank_party_column(scenario_type))
        )
        clear_party = self._normalize_summary(
            clear_row.get(self._clear_party_column(scenario_type))
        )
        return (
            self._amount_from_row(bank_row) == self._amount_from_row(clear_row)
            and self._trade_date(bank_row) == self._trade_date(clear_row)
            and bool(bank_party)
            and bool(clear_party)
            and (bank_party in clear_party or clear_party in bank_party)
        )

    def _fuzzy_candidate(
        self,
        row: dict[str, object],
        *,
        party_column: str,
    ) -> dict[str, str]:
        amount = self._amount_from_row(row)
        trade_date = self._trade_date(row)
        return {
            "flow_id": str(row["flow_id"]),
            "amount": str(amount),
            "trade_date": trade_date.isoformat() if trade_date is not None else "",
            "counterparty": self._normalize_summary(row.get(party_column)),
        }

    def _trade_date(self, row: dict[str, object]) -> date | None:
        for key in ("trade_time", "trade_date", "accounting_date"):
            value = row.get(key)
            if self._is_empty(value):
                continue
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, date):
                return value
            try:
                return datetime.fromisoformat(str(value).strip()).date()
            except ValueError:
                continue
        return None

    def _bank_party_column(self, scenario_type: str) -> str:
        if scenario_type == "BANK_CLEARING":
            return "customer_name_masked"
        return "counterparty_name_masked"

    def _clear_party_column(self, scenario_type: str) -> str:
        if scenario_type == "BANK_CLEARING":
            return "payer_name_masked"
        return "payee_name_masked"

    def _rows_by_flow_id(self, dataframe: pd.DataFrame) -> dict[str, dict[str, object]]:
        return {
            str(row["flow_id"]): row
            for row in dataframe.to_dict("records")
        }

    def _duplicate_flow_ids(self, dataframe: pd.DataFrame, *, party_column: str) -> set[str]:
        if dataframe.empty:
            return set()

        groups: dict[tuple[Decimal, str | None], list[str]] = {}
        for row in dataframe.to_dict("records"):
            key = (
                self._to_decimal(row["amount"]),
                self._to_optional_string(row.get(party_column)),
            )
            groups.setdefault(key, []).append(str(row["flow_id"]))

        return {
            flow_id
            for flow_ids in groups.values()
            if len(flow_ids) >= 2
            for flow_id in flow_ids
        }

    def _present_side(
        self,
        bank_row: dict[str, object] | None,
        clear_row: dict[str, object] | None,
    ) -> str | None:
        # ADR-015: this shared fact reports which source is missing. In clearing,
        # `A` means the core/bank row is absent and the clearing row is present.
        if bank_row is None and clear_row is not None:
            return "A"
        if bank_row is not None and clear_row is None:
            return "B"
        return None

    def _has_narrative_mismatch(
        self,
        bank_row: dict[str, object] | None,
        clear_row: dict[str, object] | None,
        bank_amount: Decimal | None,
        clear_amount: Decimal | None,
    ) -> bool:
        if bank_row is None or clear_row is None or bank_amount != clear_amount:
            return False

        bank_summary = self._normalize_summary(bank_row.get("summary"))
        clear_summary = self._normalize_summary(clear_row.get("summary"))
        return (
            bank_summary != clear_summary
            or self._contains_reversal_keyword(bank_summary)
            or self._contains_reversal_keyword(clear_summary)
        )

    def _contains_reversal_keyword(self, value: str) -> bool:
        return any(keyword in value for keyword in REVERSAL_KEYWORDS)

    def _in_cutoff_window(self, clear_row: dict[str, object] | None) -> bool:
        if clear_row is None:
            return False
        trade_time = self._parse_trade_time(clear_row.get("trade_time"))
        if trade_time is None:
            return False
        start, end = self._parse_cutoff_window(settings.cutoff_window)
        if start < end:
            return start <= trade_time < end
        return trade_time >= start or trade_time < end

    def _normalize_summary(self, value: object) -> str:
        return "" if self._is_empty(value) else str(value).strip()

    def _amount_from_row(self, row: dict[str, object] | None) -> Decimal | None:
        if row is None:
            return None
        return self._to_decimal(row["amount"])

    def _amount_diff(
        self,
        bank_amount: Decimal | None,
        clear_amount: Decimal | None,
    ) -> Decimal | None:
        if bank_amount is None or clear_amount is None:
            return None
        return bank_amount - clear_amount

    def _find_t1_candidate(
        self,
        clear_row: dict[str, object],
        bank_df: pd.DataFrame,
    ) -> dict[str, str] | None:
        clear_amount = self._amount_from_row(clear_row)
        trade_date = self._parse_date(clear_row.get("trade_date"))
        if clear_amount is None or trade_date is None:
            return None

        target_accounting_date = trade_date + timedelta(days=1)
        clear_references = self._reference_values(clear_row)
        if not clear_references:
            return None

        for bank_row in bank_df.to_dict("records"):
            if self._amount_from_row(bank_row) != clear_amount:
                continue
            if self._parse_date(bank_row.get("accounting_date")) != target_accounting_date:
                continue
            if not clear_references & self._reference_values(bank_row):
                continue
            return {
                "flow_id": str(bank_row["flow_id"]),
                "accounting_date": target_accounting_date.isoformat(),
            }

        return None

    def _to_decimal(self, value: object) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"))

    def _to_optional_string(self, value: object) -> str | None:
        if self._is_empty(value):
            return None
        return str(value)

    def _parse_cutoff_window(self, value: str) -> tuple[time, time]:
        start_raw, end_raw = [item.strip() for item in value.split("-", maxsplit=1)]
        return self._parse_clock_time(start_raw), self._parse_clock_time(end_raw)

    def _parse_trade_time(self, value: object) -> time | None:
        if self._is_empty(value):
            return None
        try:
            return self._parse_clock_time(str(value).strip())
        except ValueError:
            return None

    def _parse_date(self, value: object) -> date | None:
        if self._is_empty(value):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value).strip())
        except ValueError:
            return None

    def _reference_values(self, row: dict[str, object]) -> set[str]:
        return {
            value
            for key in ("reference_no", "merchant_order_no", "voucher_no")
            if (value := self._to_optional_string(row.get(key)))
        }

    def _parse_clock_time(self, value: str) -> time:
        if value == "24:00":
            return time(0, 0)
        hour_text, minute_text = value.split(":", maxsplit=1)
        return time(hour=int(hour_text), minute=int(minute_text))

    def _is_empty(self, value: object) -> bool:
        return value is None or bool(pd.isna(value))


exception_router = ExceptionRouter()

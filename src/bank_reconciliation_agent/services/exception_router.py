from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

import pandas as pd

from bank_reconciliation_agent.services.rule_engine import rule_engine


REVERSAL_KEYWORDS = {"冲正", "红冲", "退款", "抹账", "撤销"}


class BranchResult(NamedTuple):
    flow_id: str
    action: str
    error_type: str | None
    exception_branch: str | None
    bank_amount: Decimal | None
    clear_amount: Decimal | None
    amount_diff: Decimal | None


class ExceptionRouter:
    def classify(self, bank_df: pd.DataFrame, clear_df: pd.DataFrame) -> list[BranchResult]:
        bank_by_flow_id = self._rows_by_flow_id(bank_df)
        clear_by_flow_id = self._rows_by_flow_id(clear_df)
        bank_duplicates = self._duplicate_flow_ids(
            bank_df,
            party_column="counterparty_name_masked",
        )
        clear_duplicates = self._duplicate_flow_ids(
            clear_df,
            party_column="payee_name_masked",
        )

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
            match = rule_engine.evaluate(facts)
            results.append(
                BranchResult(
                    flow_id=flow_id,
                    action=match.action,
                    error_type=match.error_type,
                    exception_branch=match.exception_branch,
                    bank_amount=bank_amount,
                    clear_amount=clear_amount,
                    amount_diff=self._amount_diff(bank_amount, clear_amount),
                )
            )

        return results

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

    def _to_decimal(self, value: object) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"))

    def _to_optional_string(self, value: object) -> str | None:
        if self._is_empty(value):
            return None
        return str(value)

    def _is_empty(self, value: object) -> bool:
        return value is None or bool(pd.isna(value))


exception_router = ExceptionRouter()

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import pandas as pd
from fastapi import HTTPException
from pydantic import ValidationError

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.services.task import task_service


def validation_hook(
    bank_df: pd.DataFrame,
    clear_df: pd.DataFrame,
    *,
    scenario_type: str,
) -> None:
    _validate_columns(bank_df, _BANK_REQUIRED_COLUMNS, "bank_file")
    _validate_columns(clear_df, _CLEAR_REQUIRED_COLUMNS, "clear_file")
    _validate_data_types(bank_df, "bank_file")
    _validate_data_types(clear_df, "clear_file")
    _validate_unique_flow_ids(bank_df, "bank_file")
    _validate_unique_flow_ids(clear_df, "clear_file")
    log.info(
        "validation_hook_passed",
        hook_name="ValidationHook",
        scenario_type=scenario_type,
    )


def auth_hook(*, user_id: str, task_id: str) -> None:
    if task_service.get(user_id=user_id, task_id=task_id) is None:
        log.warning(
            "auth_hook_forbidden",
            hook_name="AuthHook",
            user_id=user_id,
            task_id=task_id,
        )
        raise HTTPException(status_code=403, detail="forbidden task access")

    log.info(
        "auth_hook_passed",
        hook_name="AuthHook",
        user_id=user_id,
        task_id=task_id,
    )


class SchemaValidationError(ValueError):
    """Raised when audit output does not satisfy AuditDecision schema."""


def schema_hook(payload: AuditDecision | dict[str, object]) -> AuditDecision:
    try:
        decision = AuditDecision.model_validate(payload)
    except ValidationError as exc:
        log.warning(
            "schema_hook_failed",
            hook_name="SchemaHook",
            error_type=type(exc).__name__,
        )
        raise SchemaValidationError("schema validation failed") from exc

    log.info(
        "schema_hook_passed",
        hook_name="SchemaHook",
    )
    return decision


def memory_hook(state: dict[str, object]) -> dict[str, object]:
    log.info(
        "memory_hook_skipped",
        hook_name="MemoryHook",
        memory_skipped=True,
    )
    return state


@dataclass
class ConstraintResult:
    ok: bool
    violated: list[str]


def constraint_hook(
    decision: AuditDecision,
    *,
    amount_diff: Decimal | None,
    rag_best_score: float | None,
) -> ConstraintResult:
    violated: list[str] = []
    if amount_diff is not None and abs(amount_diff) > Decimal("10000") and decision.risk_level == "LOW":
        violated.append("C3")
    if decision.decision == "PENDING_HUMAN" and _is_placeholder_reason(decision.reason):
        violated.append("C4")
    if decision.decision == "AUTO_FIXED" and decision.confidence < 0.85:
        violated.append("C5")
    if decision.decision == "AUTO_FIXED" and (rag_best_score is None or rag_best_score < 0.5):
        violated.append("C6")

    result = ConstraintResult(ok=not violated, violated=violated)
    log.info(
        "constraint_hook_evaluated",
        hook_name="ConstraintHook",
        violated=violated,
    )
    return result


def decision_hook(decision: AuditDecision, constraint: ConstraintResult) -> str:
    next_action = "PENDING_HUMAN" if not constraint.ok else decision.decision
    log.info(
        "decision_hook_routed",
        hook_name="DecisionHook",
        violated=constraint.violated,
        next_action=next_action,
    )
    return next_action


def _validate_columns(
    dataframe: pd.DataFrame,
    required_columns: Sequence[str],
    file_label: str,
) -> None:
    missing = [col for col in required_columns if col not in dataframe.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"{file_label} missing required columns: {', '.join(missing)}",
        )


def _validate_data_types(dataframe: pd.DataFrame, file_label: str) -> None:
    for col in _NUMERIC_COLUMNS:
        if col not in dataframe.columns:
            continue
        non_numeric = dataframe[col].apply(
            lambda x: not (pd.isna(x) or isinstance(x, (int, float)))
        )
        if non_numeric.any():
            bad_values = dataframe.loc[non_numeric, col].head(3).tolist()
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{file_label} column '{col}' contains non-numeric values: "
                    f"{bad_values}"
                ),
            )

    if dataframe["flow_id"].isna().any():
        raise HTTPException(
            status_code=400,
            detail=f"{file_label} contains empty flow_id values",
        )

    flow_id_series = dataframe["flow_id"].astype(str)
    empty_flow_ids = flow_id_series.str.strip().eq("")
    invalid_flow_ids = flow_id_series.str.strip().str.lower().isin({"nan", "none", "null"})
    if empty_flow_ids.any() or invalid_flow_ids.any():
        raise HTTPException(
            status_code=400,
            detail=f"{file_label} contains empty flow_id values",
        )


def _validate_unique_flow_ids(dataframe: pd.DataFrame, file_label: str) -> None:
    duplicated = dataframe.loc[dataframe["flow_id"].duplicated(), "flow_id"]
    if duplicated.empty:
        return
    raise HTTPException(
        status_code=400,
        detail=f"{file_label} contains duplicate flow_id: {duplicated.iloc[0]}",
    )


def _is_placeholder_reason(reason: str) -> bool:
    normalized = reason.strip().lower()
    return not normalized or normalized in {"todo", "tbd", "pending", "placeholder", "n/a", "-"}


_BANK_REQUIRED_COLUMNS = [
    "flow_id", "bank_serial_no", "accounting_date", "accounting_time",
    "value_date", "self_account_no_masked", "self_account_name_masked",
    "self_bank_name", "currency", "transaction_type", "transaction_direction",
    "amount", "debit_amount", "credit_amount", "fee_amount", "balance_after",
    "trade_time", "account_no_masked", "customer_name_masked",
    "counterparty_account_no_masked", "counterparty_name_masked",
    "counterparty_bank_name", "channel", "summary", "purpose",
    "posting_status", "branch_no", "teller_id", "transaction_code",
    "source_system", "remark",
]

_CLEAR_REQUIRED_COLUMNS = [
    "flow_id", "clearing_serial_no", "merchant_id", "merchant_name",
    "store_name", "terminal_id", "channel", "transaction_type",
    "trade_date", "trade_time", "settlement_date", "amount",
    "transaction_amount", "fee_amount", "net_amount", "currency",
    "status", "summary", "batch_no", "voucher_no", "reference_no",
    "merchant_order_no", "payer_account_no_masked", "payer_name_masked",
    "payee_account_no_masked", "payee_name_masked", "order_description", "remark",
]

_NUMERIC_COLUMNS = [
    "amount", "debit_amount", "credit_amount", "fee_amount",
    "transaction_amount", "net_amount", "balance_after",
]

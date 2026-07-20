from __future__ import annotations

import hashlib
from io import BytesIO

import pandas as pd
from fastapi import HTTPException, UploadFile

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.services.exception_router import BranchResult, exception_router
from bank_reconciliation_agent.services.reconciliation_types import (
    ReconciliationMatchResult,
    ReconciliationMatchSummary,
)


def generate_task_id(content: object) -> str:
    if isinstance(content, tuple) and len(content) == 2:
        bank_df, clear_df = content
        if isinstance(bank_df, pd.DataFrame) and isinstance(clear_df, pd.DataFrame):
            payload = (
                bank_df.to_csv(index=False, lineterminator="\n").encode("utf-8")
                + b"\n--CLEAR--\n"
                + clear_df.to_csv(index=False, lineterminator="\n").encode("utf-8")
            )
        else:
            payload = str(content).encode("utf-8")
    elif isinstance(content, bytes):
        payload = content
    else:
        payload = str(content).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:12]
    return f"TASK_{digest}"


def validate_file_size(upload_file: UploadFile, content_length: int) -> None:
    if content_length > settings.max_upload_bytes:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{upload_file.filename} exceeds maximum file size of "
                f"{settings.max_upload_bytes} bytes"
            ),
        )


def read_dataframe(content: bytes, file_label: str) -> pd.DataFrame:
    try:
        dataframe = pd.read_excel(BytesIO(content))
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{file_label} must be a readable Excel file",
        ) from exc
    if len(dataframe) > settings.max_upload_rows:
        raise HTTPException(
            status_code=400,
            detail=f"{file_label} exceeds maximum of {settings.max_upload_rows} rows",
        )
    return dataframe


def build_match_results(
    bank_df: pd.DataFrame,
    clear_df: pd.DataFrame,
    *,
    scenario_type: str = "BANK_ENTERPRISE",
) -> list[ReconciliationMatchResult]:
    return [
        to_match_result(result)
        for result in exception_router.classify(
            bank_df,
            clear_df,
            scenario_type=scenario_type,
        )
    ]


def to_match_result(result: BranchResult) -> ReconciliationMatchResult:
    status = "AUTO_FIXED" if result.action == "AUTO_FIX" else "PENDING_HUMAN"
    if result.error_type == "FUZZY_MATCH_CANDIDATE":
        status = "PENDING_AI"
    return ReconciliationMatchResult(
        flow_id=result.flow_id,
        status=status,
        error_type=result.error_type,
        exception_branch=result.exception_branch,
        bank_amount=result.bank_amount,
        clear_amount=result.clear_amount,
        amount_diff=result.amount_diff,
        t1_candidate=result.t1_candidate,
        fuzzy_candidate=result.fuzzy_candidate,
    )


def summarize_match_results(
    results: list[ReconciliationMatchResult],
) -> ReconciliationMatchSummary:
    return ReconciliationMatchSummary(
        auto_fixed_rows=sum(result.status == "AUTO_FIXED" for result in results),
        pending_ai_rows=sum(result.status == "PENDING_AI" for result in results),
        pending_human_rows=sum(result.status == "PENDING_HUMAN" for result in results),
    )

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from typing import NamedTuple

import pandas as pd
from fastapi import HTTPException, UploadFile

from bank_reconciliation_agent.agents.audit_agent import AuditDecision, audit_agent
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.rag.retriever import rule_retriever
from bank_reconciliation_agent.schemas.ledger import LedgerQuery, LedgerRow
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchRequest
from bank_reconciliation_agent.schemas.reconciliation import (
    ReconciliationAuditDecision,
    ReconciliationExceptionItem,
    ReconciliationExceptionListResponse,
    ReconciliationRagEvidence,
    ReconciliationStartResponse,
    ReconciliationStatusResponse,
    ReconciliationUploadResponse,
)
from bank_reconciliation_agent.services.agent_log import agent_log_service
from bank_reconciliation_agent.services.exception_router import BranchResult, exception_router
from bank_reconciliation_agent.services.ledger import ledger_service
from bank_reconciliation_agent.services.queue import queue_service
from bank_reconciliation_agent.services.rag_log import rag_log_service
from bank_reconciliation_agent.services.task import task_service
from bank_reconciliation_agent.services.trace import trace_writer
from bank_reconciliation_agent.services.transactions import transaction_service


BANK_REQUIRED_COLUMNS = [
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

CLEAR_REQUIRED_COLUMNS = [
    "flow_id", "clearing_serial_no", "merchant_id", "merchant_name",
    "store_name", "terminal_id", "channel", "transaction_type",
    "trade_date", "trade_time", "settlement_date", "amount",
    "transaction_amount", "fee_amount", "net_amount", "currency",
    "status", "summary", "batch_no", "voucher_no", "reference_no",
    "merchant_order_no", "payer_account_no_masked", "payer_name_masked",
    "payee_account_no_masked", "payee_name_masked", "order_description", "remark",
]

NUMERIC_COLUMNS = [
    "amount", "debit_amount", "credit_amount", "fee_amount",
    "transaction_amount", "net_amount", "balance_after",
]


class ReconciliationMatchSummary(NamedTuple):
    auto_fixed_rows: int
    pending_ai_rows: int
    pending_human_rows: int


class ReconciliationMatchResult(NamedTuple):
    flow_id: str
    status: str
    error_type: str | None
    exception_branch: str | None
    bank_amount: Decimal | None
    clear_amount: Decimal | None
    amount_diff: Decimal | None


class ReconciliationService:

    async def upload(
        self,
        *,
        user_id: str,
        bank_file: UploadFile,
        clear_file: UploadFile,
    ) -> ReconciliationUploadResponse:
        bank_content = await bank_file.read()
        clear_content = await clear_file.read()
        self._validate_file_size(bank_file, len(bank_content))
        self._validate_file_size(clear_file, len(clear_content))

        bank_df = self._read_dataframe(bank_content, "bank_file")
        clear_df = self._read_dataframe(clear_content, "clear_file")
        self._validate_columns(bank_df, BANK_REQUIRED_COLUMNS, "bank_file")
        self._validate_columns(clear_df, CLEAR_REQUIRED_COLUMNS, "clear_file")
        self._validate_data_types(bank_df, "bank_file")
        self._validate_data_types(clear_df, "clear_file")
        self._validate_unique_flow_ids(bank_df, "bank_file")
        self._validate_unique_flow_ids(clear_df, "clear_file")

        match_results = self._build_match_results(bank_df, clear_df)
        match_summary = self._summarize_match_results(match_results)
        task_id = self._generate_task_id(bank_content + clear_content)

        task_service.replace_task(
            user_id=user_id,
            task_id=task_id,
            total_bank_rows=len(bank_df),
            total_clear_rows=len(clear_df),
            auto_fixed_rows=match_summary.auto_fixed_rows,
            pending_ai_rows=match_summary.pending_ai_rows,
            pending_human_rows=match_summary.pending_human_rows,
        )
        transaction_service.replace_task_rows(
            user_id=user_id,
            task_id=task_id,
            bank_df=bank_df,
            clear_df=clear_df,
        )

        self._write_queue_entries(user_id, task_id, match_results)
        self._write_ledger_entries(user_id, task_id, match_results)

        return ReconciliationUploadResponse(
            task_id=task_id,
            total_bank_rows=len(bank_df),
            total_clear_rows=len(clear_df),
            auto_fixed_rows=match_summary.auto_fixed_rows,
            pending_ai_rows=match_summary.pending_ai_rows,
            pending_human_rows=match_summary.pending_human_rows,
        )

    def _generate_task_id(self, content: bytes) -> str:
        digest = hashlib.sha256(content).hexdigest()[:12]
        return f"TASK_{digest}"

    def _validate_file_size(self, upload_file: UploadFile, content_length: int) -> None:
        if content_length > settings.max_upload_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"{upload_file.filename} exceeds maximum file size of {settings.max_upload_bytes} bytes",
            )

    def _read_dataframe(self, content: bytes, file_label: str) -> pd.DataFrame:
        try:
            df = pd.read_excel(BytesIO(content))
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"{file_label} must be a readable Excel file",
            ) from exc
        if len(df) > settings.max_upload_rows:
            raise HTTPException(
                status_code=400,
                detail=f"{file_label} exceeds maximum of {settings.max_upload_rows} rows",
            )
        return df

    def _validate_columns(
        self, dataframe: pd.DataFrame, required_columns: list[str], file_label: str,
    ) -> None:
        missing = [col for col in required_columns if col not in dataframe.columns]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"{file_label} missing required columns: {', '.join(missing)}",
            )

    def _validate_data_types(
        self, dataframe: pd.DataFrame, file_label: str,
    ) -> None:
        for col in NUMERIC_COLUMNS:
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

    def _validate_unique_flow_ids(
        self, dataframe: pd.DataFrame, file_label: str,
    ) -> None:
        duplicated = dataframe.loc[dataframe["flow_id"].duplicated(), "flow_id"]
        if duplicated.empty:
            return
        raise HTTPException(
            status_code=400,
            detail=f"{file_label} contains duplicate flow_id: {duplicated.iloc[0]}",
        )

    def _build_match_results(
        self, bank_df: pd.DataFrame, clear_df: pd.DataFrame,
    ) -> list[ReconciliationMatchResult]:
        return [
            self._to_match_result(result)
            for result in exception_router.classify(bank_df, clear_df)
        ]

    def _to_match_result(self, result: BranchResult) -> ReconciliationMatchResult:
        return ReconciliationMatchResult(
            flow_id=result.flow_id,
            status="AUTO_FIXED" if result.action == "AUTO_FIX" else "PENDING_HUMAN",
            error_type=result.error_type,
            exception_branch=result.exception_branch,
            bank_amount=result.bank_amount,
            clear_amount=result.clear_amount,
            amount_diff=result.amount_diff,
        )

    def _summarize_match_results(
        self, results: list[ReconciliationMatchResult],
    ) -> ReconciliationMatchSummary:
        return ReconciliationMatchSummary(
            auto_fixed_rows=sum(r.status == "AUTO_FIXED" for r in results),
            pending_ai_rows=sum(r.status == "PENDING_AI" for r in results),
            pending_human_rows=sum(r.status == "PENDING_HUMAN" for r in results),
        )

    def start(self, *, user_id: str, task_id: str) -> ReconciliationStartResponse:
        if not task_service.update_status(user_id=user_id, task_id=task_id, status="AI_RUNNING"):
            raise HTTPException(status_code=404, detail="reconciliation task not found")
        return ReconciliationStartResponse(task_id=task_id, status="AI_RUNNING")

    def get_status(self, *, user_id: str, task_id: str) -> ReconciliationStatusResponse:
        task = task_service.get(user_id=user_id, task_id=task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="reconciliation task not found")
        return ReconciliationStatusResponse(
            task_id=task_id, status=task.status,
            auto_fixed_rows=task.auto_fixed_rows,
            pending_ai_rows=task.pending_ai_rows,
            ai_processed_rows=task.unresolved_rows,
            pending_human_rows=task.pending_human_rows,
            unresolved_rows=task.unresolved_rows,
        )

    def get_exceptions(self, *, user_id: str, task_id: str) -> ReconciliationExceptionListResponse:
        task = task_service.get(user_id=user_id, task_id=task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="reconciliation task not found")

        page = ledger_service.list(
            user_id=user_id,
            query=LedgerQuery(task_id=task_id, page=1, page_size=10_000),
        )
        items: list[ReconciliationExceptionItem] = []
        for row in page.items:
            amount_diff = self._format_optional_decimal(row.discrepancy_amount)
            evidence = self._evidence_from_rag_source(row.rag_source)
            items.append(ReconciliationExceptionItem(
                flow_id=row.flow_id,
                status="PENDING_HUMAN",
                error_type=row.error_type,
                exception_branch=row.exception_branch,
                bank_amount=self._format_optional_decimal(row.bank_amount),
                clear_amount=self._format_optional_decimal(row.clear_amount),
                amount_diff=amount_diff,
                rag_evidence=evidence,
                audit_decision=ReconciliationAuditDecision(
                    flow_id=row.flow_id,
                    decision=row.handle_status,
                    risk_level="MEDIUM",
                    reason=row.ai_audit_opinion or "",
                    evidence=evidence,
                    confidence=float(row.ai_confidence) if row.ai_confidence else 0.0,
                ),
            ))

        return ReconciliationExceptionListResponse(
            task_id=task_id, total=len(items), items=items,
        )

    def _format_optional_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return f"{value:.2f}"

    def _retrieve_rag_items_by_query(self, query: str) -> list[RagSearchItem]:
        response = rule_retriever.search(RagSearchRequest(query=query, top_k=2, min_score=0.0))
        return response.items

    def _evidence_from_rag_source(self, rag_source: str | None) -> list[ReconciliationRagEvidence]:
        if not rag_source:
            return []
        chunk_ids = [chunk_id.strip() for chunk_id in rag_source.split(",") if chunk_id.strip()]
        return [
            self._to_reconciliation_evidence(item)
            for item in rule_retriever.get_by_chunk_ids(chunk_ids)
        ]

    def _build_rag_query(self, result: ReconciliationMatchResult) -> str:
        query_prefix_by_error_type = {
            "AMOUNT_MISMATCH": "金额不一致 对账差异 处理规则",
            "BANK_UNARRIVED": "银行未到账 企业已记账 单边 查询查复",
            "BOOK_UNRECORDED": "银行已到账 企业未入账 补登 单边",
            "NARRATIVE_NAME_MISMATCH": "摘要 客户名 不一致 冲正 退款 核对",
            "DUPLICATE_BOOKING": "重复记账 重复入账 一端多记 排查",
        }
        prefix = query_prefix_by_error_type.get(
            result.error_type or "",
            f"{result.error_type or ''} reconciliation exception",
        )
        return (
            f"{result.error_type or ''} {prefix} "
            f"bank_amount={self._format_optional_decimal(result.bank_amount)} "
            f"clear_amount={self._format_optional_decimal(result.clear_amount)} "
            f"amount_diff={self._format_optional_decimal(result.amount_diff)}"
        )

    def _to_reconciliation_evidence(self, item: RagSearchItem) -> ReconciliationRagEvidence:
        return ReconciliationRagEvidence(
            chunk_id=item.chunk_id, source=item.source,
            source_name=item.source_name, source_url=item.source_url,
            source_file=item.source_file, section_title=item.section_title,
            element_type=item.element_type, business_tags=item.business_tags,
            score=item.score, content=item.content,
        )

    def _to_reconciliation_audit_decision(
        self, decision: AuditDecision,
    ) -> ReconciliationAuditDecision:
        return ReconciliationAuditDecision(
            flow_id=decision.flow_id, decision=decision.decision,
            risk_level=decision.risk_level, reason=decision.reason,
            evidence=[self._to_reconciliation_evidence(item) for item in decision.evidence],
            confidence=decision.confidence,
        )

    def _write_queue_entries(
        self,
        user_id: str,
        task_id: str,
        results: list[ReconciliationMatchResult],
    ) -> None:
        queue_rows: list[dict[str, object]] = []
        for result in results:
            if result.status == "AUTO_FIXED":
                continue
            queue_rows.append({
                "task_id": task_id, "flow_id": result.flow_id,
                "bank_transaction_id": None, "clear_transaction_id": None,
                "error_type": result.error_type or "",
                "exception_branch": result.exception_branch,
                "status": result.status,
                "risk_level": "MEDIUM", "retry_count": 0,
            })
        queue_service.replace_task_rows(user_id=user_id, task_id=task_id, rows=queue_rows)

    def _write_ledger_entries(
        self,
        user_id: str,
        task_id: str,
        results: list[ReconciliationMatchResult],
    ) -> None:
        rows: list[LedgerRow] = []
        rag_log_rows: list[dict[str, object]] = []
        agent_log_rows: list[dict[str, object]] = []
        for result in results:
            if result.status == "AUTO_FIXED":
                continue

            rag_query = self._build_rag_query(result)
            rag_items = self._retrieve_rag_items_by_query(rag_query)
            rag_hit = {
                "chunk_ids": [item.chunk_id for item in rag_items],
                "best_score": max((item.score for item in rag_items), default=None),
            }
            rule_hit = {
                "error_type": result.error_type or "",
                "exception_branch": result.exception_branch,
            }
            rag_log_rows.append(rag_log_service.build_row(
                user_id=user_id,
                task_id=task_id,
                query_text=rag_query,
                top_k=2,
                items=rag_items,
            ))
            audit_decision = audit_agent.decide(
                flow_id=result.flow_id, error_type=result.error_type or "",
                exception_branch=result.exception_branch,
                bank_amount=self._format_optional_decimal(result.bank_amount),
                clear_amount=self._format_optional_decimal(result.clear_amount),
                amount_diff=self._format_optional_decimal(result.amount_diff),
                evidence=rag_items,
            )
            agent_output = {
                "decision": audit_decision.decision,
                "risk_level": audit_decision.risk_level,
                "ai_suggestion": audit_decision.ai_suggestion,
                "reason": audit_decision.reason,
                "confidence": audit_decision.confidence,
            }
            input_payload = {
                "flow_id": result.flow_id,
                "rule_hit": rule_hit,
                "rag_hit": rag_hit,
                "bank_amount": self._format_optional_decimal(result.bank_amount),
                "clear_amount": self._format_optional_decimal(result.clear_amount),
                "amount_diff": self._format_optional_decimal(result.amount_diff),
            }
            agent_log_rows.append(agent_log_service.build_row(
                user_id=user_id,
                task_id=task_id,
                queue_id=None,
                agent_name="AuditAgent",
                event_type="AUDIT_DECISION",
                input_payload=input_payload,
                output_payload=agent_output,
            ))
            trace_writer.write(
                task_id=task_id,
                flow_id=result.flow_id,
                payload={
                    "task_id": task_id,
                    "flow_id": result.flow_id,
                    "user_id": user_id,
                    "rule_hit": rule_hit,
                    "rag_hit": rag_hit,
                    "agent_output": agent_output,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            rows.append(LedgerRow(
                id=0, task_id=task_id, flow_id=result.flow_id,
                error_type=result.error_type or "",
                exception_branch=result.exception_branch,
                bank_amount=result.bank_amount,
                clear_amount=result.clear_amount,
                discrepancy_amount=self._ledger_discrepancy_amount(result),
                ai_audit_opinion=audit_decision.reason,
                ai_confidence=Decimal(str(audit_decision.confidence)).quantize(Decimal("0.0001")),
                rag_source=", ".join(item.chunk_id for item in rag_items) or None,
                handle_status=audit_decision.decision,
            ))

        ledger_service.replace_task_rows(user_id=user_id, task_id=task_id, rows=rows)
        rag_log_service.replace_task_rows(user_id=user_id, task_id=task_id, rows=rag_log_rows)
        agent_log_service.replace_task_rows(user_id=user_id, task_id=task_id, rows=agent_log_rows)

    def _ledger_discrepancy_amount(self, result: ReconciliationMatchResult) -> Decimal:
        if result.amount_diff is not None:
            return abs(result.amount_diff)
        if result.bank_amount is not None:
            return result.bank_amount
        if result.clear_amount is not None:
            return result.clear_amount
        return Decimal("0.00")


reconciliation_service = ReconciliationService()

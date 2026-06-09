from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from typing import NamedTuple

import pandas as pd
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgentError
from bank_reconciliation_agent.agents.trace_agent import TraceAgentError
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.llm.cost import compute_cost
from bank_reconciliation_agent.core.llm.provider import LLMUnavailable
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.rag.retriever import rule_retriever
from bank_reconciliation_agent.schemas.ledger import LedgerQuery, LedgerRow
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchResponse
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
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item


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

AGENT_PROCESSING_ERRORS = (
    LLMUnavailable,
    ExtractionAgentError,
    TraceAgentError,
    ValidationError,
    json.JSONDecodeError,
)


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
    t1_candidate: dict[str, str] | None = None


class ReconciliationService:

    async def upload(
        self,
        *,
        user_id: str,
        scenario_type: str = "BANK_ENTERPRISE",
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

        match_results = self._build_match_results(
            bank_df,
            clear_df,
            scenario_type=scenario_type,
        )
        match_summary = self._summarize_match_results(match_results)
        task_id = self._generate_task_id(bank_content + clear_content)

        task_service.replace_task(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
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

        self._write_queue_entries(user_id, task_id, scenario_type, match_results)
        self._write_ledger_entries(user_id, task_id, scenario_type, match_results)

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
        self,
        bank_df: pd.DataFrame,
        clear_df: pd.DataFrame,
        *,
        scenario_type: str = "BANK_ENTERPRISE",
    ) -> list[ReconciliationMatchResult]:
        return [
            self._to_match_result(result)
            for result in exception_router.classify(
                bank_df,
                clear_df,
                scenario_type=scenario_type,
            )
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
            t1_candidate=result.t1_candidate,
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
            ai_processed_rows=task.ai_processed_rows,
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
            evidence = self._evidence_from_rag_source(
                row.rag_source,
                scenario_type=task.scenario_type,
            )
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

    def _evidence_from_rag_source(
        self,
        rag_source: str | None,
        *,
        scenario_type: str = "BANK_ENTERPRISE",
    ) -> list[ReconciliationRagEvidence]:
        if not rag_source:
            return []
        chunk_ids = [chunk_id.strip() for chunk_id in rag_source.split(",") if chunk_id.strip()]
        return [
            self._to_reconciliation_evidence(item)
            for item in rule_retriever.get_by_chunk_ids(
                chunk_ids,
                scenario_type=scenario_type,
            )
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
            fallback_applied=decision.fallback_applied,
            fallback_level=decision.fallback_level,
            next_action=decision.next_action,
        )

    def _write_queue_entries(
        self,
        user_id: str,
        task_id: str,
        scenario_type: str,
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
        queue_service.replace_task_rows(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            rows=queue_rows,
        )

    def _write_ledger_entries(
        self,
        user_id: str,
        task_id: str,
        scenario_type: str,
        results: list[ReconciliationMatchResult],
    ) -> None:
        rows: list[LedgerRow] = []
        rag_log_rows: list[dict[str, object]] = []
        agent_log_rows: list[dict[str, object]] = []
        ai_processed_rows = 0
        fallback_l2_rows = 0
        fallback_l3_rows = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        for result in results:
            if result.status == "AUTO_FIXED":
                continue

            rag_query = self._build_rag_query(result)
            rule_hit = {
                "error_type": result.error_type or "",
                "exception_branch": result.exception_branch,
            }
            try:
                workflow_state = self._run_workflow_for_result(
                    user_id=user_id,
                    task_id=task_id,
                    scenario_type=scenario_type,
                    result=result,
                    rag_query=rag_query,
                )
            except AGENT_PROCESSING_ERRORS as exc:
                log.warning(
                    "reconciliation_row_agent_fallback",
                    flow_id=result.flow_id,
                    task_id=task_id,
                    error_type=type(exc).__name__,
                )
                workflow_state = self._agent_error_workflow_state(
                    user_id=user_id,
                    task_id=task_id,
                    scenario_type=scenario_type,
                    result=result,
                    error=exc,
                )
            rag_items = [
                RagSearchItem.model_validate(item)
                for item in workflow_state["rag_context"]
            ]
            rag_response = RagSearchResponse.model_validate(
                workflow_state.get("rag_response", {"items": rag_items})
            )
            rag_hit = {
                "chunk_ids": [item.chunk_id for item in rag_items],
                "best_score": max((item.score for item in rag_items), default=None),
            }
            rag_log_rows.append(rag_log_service.build_row(
                user_id=user_id,
                task_id=task_id,
                query_text=rag_query,
                top_k=settings.rag_rerank_top_k,
                items=rag_items,
                response=rag_response,
            ))
            audit_decision = AuditDecision.model_validate(workflow_state["audit_decision"])
            fallback_path = workflow_state.get("fallback_path")
            prompt_tokens = sum(int(row.get("prompt_tokens", 0)) for row in workflow_state["agent_logs"])
            completion_tokens = sum(
                int(row.get("completion_tokens", 0)) for row in workflow_state["agent_logs"]
            )
            llm_tokens = prompt_tokens + completion_tokens
            ai_processed_rows += 1
            fallback_l2_rows += int(bool(fallback_path and "L2" in fallback_path))
            fallback_l3_rows += int(bool(fallback_path and "L3" in fallback_path))
            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens
            agent_output = {
                "decision": audit_decision.decision,
                "risk_level": audit_decision.risk_level,
                "ai_suggestion": audit_decision.ai_suggestion,
                "reason": audit_decision.reason,
                "confidence": audit_decision.confidence,
                "fallback_applied": audit_decision.fallback_applied,
                "fallback_level": audit_decision.fallback_level,
                "next_action": audit_decision.next_action,
                "fallback_path": fallback_path,
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
                prompt_version=self._prompt_version_from_logs(workflow_state["agent_logs"]),
                fallback_level=audit_decision.fallback_level,
                llm_tokens=llm_tokens,
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
                fallback_path=fallback_path,
                handle_status=audit_decision.decision,
            ))

        ledger_service.replace_task_rows(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            rows=rows,
        )
        rag_log_service.replace_task_rows(user_id=user_id, task_id=task_id, rows=rag_log_rows)
        agent_log_service.replace_task_rows(user_id=user_id, task_id=task_id, rows=agent_log_rows)
        task_service.replace_ai_stats(
            user_id=user_id,
            task_id=task_id,
            ai_processed_rows=ai_processed_rows,
            fallback_l2_rows=fallback_l2_rows,
            fallback_l3_rows=fallback_l3_rows,
            total_llm_tokens=total_prompt_tokens + total_completion_tokens,
            total_llm_cost=compute_cost(total_prompt_tokens, total_completion_tokens),
        )

    def _run_workflow_for_result(
        self,
        *,
        user_id: str,
        task_id: str,
        scenario_type: str,
        result: ReconciliationMatchResult,
        rag_query: str,
    ) -> ReconciliationState:
        bank_row = transaction_service.get_bank_row(
            user_id=user_id,
            task_id=task_id,
            flow_id=result.flow_id,
        )
        clear_row = transaction_service.get_clear_row(
            user_id=user_id,
            task_id=task_id,
            flow_id=result.flow_id,
        )
        return run_item({
            "task_id": task_id,
            "user_id": user_id,
            "thread_id": task_id,
            "scenario_type": scenario_type,
            "current_queue_id": None,
            "source_a_item": bank_row or {"flow_id": result.flow_id},
            "source_b_item": clear_row or {"flow_id": result.flow_id},
            "error_type": result.error_type,
            "exception_branch": result.exception_branch,
            "math_result": {
                "bank_amount": self._format_optional_decimal(result.bank_amount),
                "clear_amount": self._format_optional_decimal(result.clear_amount),
                "amount_diff": self._format_optional_decimal(result.amount_diff),
            },
            "extraction_result": {},
            "rag_context": [],
            "audit_decision": {},
            "confidence": None,
            "retry_count": 0,
            "fallback_level": 0,
            "next_action": "",
            "error_message": None,
            "agent_logs": [],
            "rag_query": rag_query,
            "t1_candidate": result.t1_candidate,
        })

    def _agent_error_workflow_state(
        self,
        *,
        user_id: str,
        task_id: str,
        scenario_type: str,
        result: ReconciliationMatchResult,
        error: Exception,
    ) -> ReconciliationState:
        reason = f"AI 处理异常，自动转人工：{type(error).__name__}"
        decision = AuditDecision(
            flow_id=result.flow_id,
            decision="PENDING_HUMAN",
            risk_level="HIGH",
            reason=reason,
            ai_suggestion="PENDING_HUMAN",
            evidence=[],
            confidence=0.0,
            fallback_applied=True,
            fallback_level=1,
            next_action="PENDING_HUMAN",
        )
        return {
            "task_id": task_id,
            "user_id": user_id,
            "thread_id": task_id,
            "scenario_type": scenario_type,
            "current_queue_id": None,
            "source_a_item": {"flow_id": result.flow_id},
            "source_b_item": {"flow_id": result.flow_id},
            "error_type": result.error_type,
            "exception_branch": result.exception_branch,
            "math_result": {
                "bank_amount": self._format_optional_decimal(result.bank_amount),
                "clear_amount": self._format_optional_decimal(result.clear_amount),
                "amount_diff": self._format_optional_decimal(result.amount_diff),
            },
            "extraction_result": {},
            "rag_context": [],
            "audit_decision": decision.model_dump(mode="json"),
            "confidence": 0.0,
            "retry_count": 0,
            "fallback_level": 1,
            "next_action": "PENDING_HUMAN",
            "error_message": reason,
            "agent_logs": [
                {
                    "agent_name": "AuditAgent",
                    "step": "agent_error_fallback",
                    "flow_id": result.flow_id,
                    "fallback_level": 1,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "llm_tokens": 0,
                    "error_message": reason,
                }
            ],
            "fallback_path": "AI_ERROR->HUMAN",
            "t1_candidate": result.t1_candidate,
        }

    def _ledger_discrepancy_amount(self, result: ReconciliationMatchResult) -> Decimal:
        if result.amount_diff is not None:
            return abs(result.amount_diff)
        if result.bank_amount is not None:
            return result.bank_amount
        if result.clear_amount is not None:
            return result.clear_amount
        return Decimal("0.00")

    def _prompt_version_from_logs(self, logs: list[dict[str, object]]) -> str | None:
        for row in reversed(logs):
            prompt_version = row.get("prompt_version")
            if prompt_version is not None:
                return str(prompt_version)
        return None


reconciliation_service = ReconciliationService()

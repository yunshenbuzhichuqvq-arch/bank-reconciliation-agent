from __future__ import annotations

import hashlib
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Callable, NamedTuple

import pandas as pd
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.agents.extraction_agent import ExtractionAgentError
from bank_reconciliation_agent.agents.trace_agent import TraceAgentError
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.db.session import get_engine
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
from bank_reconciliation_agent.services.hooks import auth_hook, validation_hook
from bank_reconciliation_agent.services.ledger import error_ledger_table, ledger_service
from bank_reconciliation_agent.services.memory.manager import memory_manager
from bank_reconciliation_agent.services.queue import queue_service, reconciliation_queue_table
from bank_reconciliation_agent.services.queue_client import enqueue_reconciliation
from bank_reconciliation_agent.services.rag_log import rag_log_service
from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.services.live_registry import mark_finished, register
from bank_reconciliation_agent.services.stream_emitter import QueueEmitter, StreamEmitter
from bank_reconciliation_agent.services.task import reconciliation_task_table, task_service
from bank_reconciliation_agent.services.trace import trace_writer
from bank_reconciliation_agent.services.transactions import transaction_service
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item


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


class ReconciliationWriteBundle(NamedTuple):
    ledger_rows: list[LedgerRow]
    rag_log_rows: list[dict[str, object]]
    agent_log_rows: list[dict[str, object]]
    trace_payloads: list[tuple[str, dict[str, object]]]
    ai_processed_rows: int
    fallback_l2_rows: int
    fallback_l3_rows: int
    total_prompt_tokens: int
    total_completion_tokens: int
    saved_prompt_tokens: int = 0
    saved_completion_tokens: int = 0

    @property
    def saved_cost(self) -> Decimal:
        return compute_cost(self.saved_prompt_tokens, self.saved_completion_tokens)


class ReconciliationService:
    def __init__(self) -> None:
        self._engine = get_engine()

    def _ensure_core_transaction_tables(self) -> None:
        error_ledger_table.metadata.create_all(self._engine, tables=[error_ledger_table])
        reconciliation_queue_table.metadata.create_all(
            self._engine,
            tables=[reconciliation_queue_table],
        )
        reconciliation_task_table.metadata.create_all(
            self._engine,
            tables=[reconciliation_task_table],
        )

    async def upload(
        self,
        *,
        user_id: str,
        scenario_type: str = "BANK_ENTERPRISE",
        bank_file: UploadFile,
        clear_file: UploadFile,
        emitter: StreamEmitter | None = None,
    ) -> ReconciliationUploadResponse:
        bank_content = await bank_file.read()
        clear_content = await clear_file.read()
        self._validate_file_size(bank_file, len(bank_content))
        self._validate_file_size(clear_file, len(clear_content))

        bank_df = self._read_dataframe(bank_content, "bank_file")
        clear_df = self._read_dataframe(clear_content, "clear_file")
        validation_hook(bank_df, clear_df, scenario_type=scenario_type)

        task_id = self._generate_task_id((bank_df, clear_df))
        return self._execute_reconciliation(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            bank_df=bank_df,
            clear_df=clear_df,
            emitter=emitter,
        )

    async def upload_async(
        self,
        *,
        user_id: str,
        scenario_type: str,
        bank_file: UploadFile,
        clear_file: UploadFile,
        force: bool = False,
    ) -> ReconciliationUploadResponse:
        bank_content = await bank_file.read()
        clear_content = await clear_file.read()
        self._validate_file_size(bank_file, len(bank_content))
        self._validate_file_size(clear_file, len(clear_content))

        bank_df = self._read_dataframe(bank_content, "bank_file")
        clear_df = self._read_dataframe(clear_content, "clear_file")
        validation_hook(bank_df, clear_df, scenario_type=scenario_type)
        task_id = self._generate_task_id((bank_df, clear_df))
        existing_task = task_service.get(user_id=user_id, task_id=task_id)
        terminal_statuses = {"UPLOADED", "COMPLETED", "FAILED"}
        if existing_task is not None:
            if force and existing_task.status == "RUNNING":
                raise HTTPException(status_code=409, detail="running task cannot be forced")
            if not force or existing_task.status not in terminal_statuses:
                return ReconciliationUploadResponse(
                    task_id=existing_task.task_id,
                    status=existing_task.status,
                    total_bank_rows=existing_task.total_bank_rows,
                    total_clear_rows=existing_task.total_clear_rows,
                    auto_fixed_rows=existing_task.auto_fixed_rows,
                    pending_ai_rows=existing_task.pending_ai_rows,
                    pending_human_rows=existing_task.pending_human_rows,
                )

        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        bank_path = upload_dir / f"{task_id}_bank.xlsx"
        clear_path = upload_dir / f"{task_id}_clear.xlsx"
        bank_path.write_bytes(bank_content)
        clear_path.write_bytes(clear_content)

        task_service.replace_task(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            total_bank_rows=0,
            total_clear_rows=0,
            auto_fixed_rows=0,
            pending_ai_rows=0,
            pending_human_rows=0,
            status="QUEUED",
        )
        await enqueue_reconciliation(
            task_id,
            user_id,
            scenario_type,
            str(bank_path),
            str(clear_path),
            force=force and existing_task is not None,
        )
        return ReconciliationUploadResponse(
            task_id=task_id,
            status="QUEUED",
            total_bank_rows=len(bank_df),
            total_clear_rows=len(clear_df),
            auto_fixed_rows=0,
            pending_ai_rows=0,
            pending_human_rows=0,
        )

    def run_reconciliation_job(
        self,
        *,
        user_id: str,
        task_id: str,
        scenario_type: str,
        bank_path: str,
        clear_path: str,
    ) -> None:
        log.info("reconciliation_job_started", task_id=task_id, user_id=user_id)
        existing_task = task_service.get(user_id=user_id, task_id=task_id)
        if existing_task is not None and existing_task.status in {"UPLOADED", "COMPLETED"}:
            log.info("reconciliation_job_skipped", task_id=task_id, user_id=user_id)
            return
        task_service.update_status(user_id=user_id, task_id=task_id, status="RUNNING")
        try:
            bank_df = self._read_dataframe(Path(bank_path).read_bytes(), "bank_file")
            clear_df = self._read_dataframe(Path(clear_path).read_bytes(), "clear_file")
            self._execute_reconciliation(
                user_id=user_id,
                task_id=task_id,
                scenario_type=scenario_type,
                bank_df=bank_df,
                clear_df=clear_df,
            )
            log.info("reconciliation_job_completed", task_id=task_id, user_id=user_id)
        except (RedisConnectionError, OperationalError) as exc:
            log.warning(
                "reconciliation_job_retrying",
                task_id=task_id,
                user_id=user_id,
                error_type=type(exc).__name__,
            )
            raise
        except Exception as exc:
            task_service.update_status(user_id=user_id, task_id=task_id, status="FAILED")
            log.warning(
                "reconciliation_job_failed",
                task_id=task_id,
                user_id=user_id,
                error_type=type(exc).__name__,
            )

    def _execute_reconciliation(
        self,
        *,
        user_id: str,
        task_id: str,
        scenario_type: str,
        bank_df: pd.DataFrame,
        clear_df: pd.DataFrame,
        emitter: StreamEmitter | None = None,
    ) -> ReconciliationUploadResponse:
        match_results = self._build_match_results(
            bank_df,
            clear_df,
            scenario_type=scenario_type,
        )
        match_summary = self._summarize_match_results(match_results)

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

        queue_rows = self._write_queue_entries(user_id, task_id, scenario_type, match_results)
        self._write_ledger_entries(
            user_id,
            task_id,
            scenario_type,
            match_results,
            queue_rows=queue_rows,
            emitter=emitter,
        )

        return ReconciliationUploadResponse(
            task_id=task_id,
            total_bank_rows=len(bank_df),
            total_clear_rows=len(clear_df),
            auto_fixed_rows=match_summary.auto_fixed_rows,
            pending_ai_rows=match_summary.pending_ai_rows,
            pending_human_rows=match_summary.pending_human_rows,
        )

    def _generate_task_id(self, content: object) -> str:
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
        auth_hook(user_id=user_id, task_id=task_id)
        if not task_service.update_status(user_id=user_id, task_id=task_id, status="AI_RUNNING"):
            raise HTTPException(status_code=404, detail="reconciliation task not found")
        return ReconciliationStartResponse(task_id=task_id, status="AI_RUNNING")

    async def start_live(self, *, user_id: str, task_id: str) -> ReconciliationStartResponse:
        auth_hook(user_id=user_id, task_id=task_id)
        task = task_service.get(user_id=user_id, task_id=task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="reconciliation task not found")
        if task.status != "UPLOADED":
            raise HTTPException(status_code=409, detail="reconciliation task is not startable")

        if not task_service.update_status(user_id=user_id, task_id=task_id, status="AI_RUNNING"):
            raise HTTPException(status_code=404, detail="reconciliation task not found")
        emitter = register(task_id)
        asyncio.create_task(self._run_live_task(user_id=user_id, task_id=task_id, emitter=emitter))
        return ReconciliationStartResponse(task_id=task_id, status="AI_RUNNING")

    async def _run_live_task(self, *, user_id: str, task_id: str, emitter: QueueEmitter) -> None:
        try:
            await asyncio.to_thread(
                self._emit_live_progress,
                user_id=user_id,
                task_id=task_id,
                emitter=emitter,
            )
            task_service.update_status(user_id=user_id, task_id=task_id, status="COMPLETED")
            emitter.emit(
                self._build_live_event(
                    event_type=StreamEventType.TASK_DONE,
                    seq=2,
                    task_id=task_id,
                    payload={"status": "COMPLETED"},
                )
            )
        except Exception as exc:
            task_service.update_status(user_id=user_id, task_id=task_id, status="FAILED")
            emitter.emit(
                self._build_live_event(
                    event_type=StreamEventType.TASK_DONE,
                    seq=1,
                    task_id=task_id,
                    payload={"status": "FAILED", "error_message": str(exc)},
                )
            )
        finally:
            mark_finished(task_id)

    def _emit_live_progress(self, *, user_id: str, task_id: str, emitter: QueueEmitter) -> None:
        task = task_service.get(user_id=user_id, task_id=task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="reconciliation task not found")
        total = max(task.total_bank_rows, task.total_clear_rows)
        exception_dist: dict[str, int] = {}
        ledger_page = ledger_service.list(
            user_id=user_id,
            query=LedgerQuery(task_id=task_id, page=1, page_size=10_000),
        )
        for row in ledger_page.items:
            exception_dist[row.error_type] = exception_dist.get(row.error_type, 0) + 1
        emitter.emit(
            self._build_live_event(
                event_type=StreamEventType.TASK_PROGRESS,
                seq=1,
                task_id=task_id,
                payload={
                    "processed": total,
                    "total": total,
                    "auto_fixed": task.auto_fixed_rows,
                    "pending_ai": task.pending_ai_rows,
                    "pending_human": task.pending_human_rows,
                    "unresolved": task.unresolved_rows,
                    "exception_dist": exception_dist,
                },
            )
        )

    def _build_live_event(
        self,
        *,
        event_type: StreamEventType,
        seq: int,
        task_id: str,
        payload: dict[str, object],
    ) -> AgentStreamEvent:
        return AgentStreamEvent(
            event_type=event_type,
            seq=seq,
            task_id=task_id,
            ts=datetime.now(timezone.utc),
            payload=payload,
        )

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
    ) -> list[dict[str, object]]:
        del user_id, scenario_type
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
        return queue_rows

    def _write_ledger_entries(
        self,
        user_id: str,
        task_id: str,
        scenario_type: str,
        results: list[ReconciliationMatchResult],
        *,
        queue_rows: list[dict[str, object]],
        emitter: StreamEmitter | None = None,
    ) -> None:
        self._ensure_core_transaction_tables()
        write_bundle = self._build_write_bundle(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            results=results,
            emitter=emitter,
        )
        with self._engine.begin() as connection:
            ledger_service.replace_task_rows(
                user_id=user_id,
                task_id=task_id,
                scenario_type=scenario_type,
                rows=write_bundle.ledger_rows,
                connection=connection,
            )
            queue_service.replace_task_rows(
                user_id=user_id,
                task_id=task_id,
                scenario_type=scenario_type,
                rows=queue_rows,
                connection=connection,
            )
            task_service.replace_ai_stats(
                user_id=user_id,
                task_id=task_id,
                ai_processed_rows=write_bundle.ai_processed_rows,
                fallback_l2_rows=write_bundle.fallback_l2_rows,
                fallback_l3_rows=write_bundle.fallback_l3_rows,
                total_llm_tokens=(
                    write_bundle.total_prompt_tokens + write_bundle.total_completion_tokens
                ),
                total_llm_cost=compute_cost(
                    write_bundle.total_prompt_tokens,
                    write_bundle.total_completion_tokens,
                ),
                connection=connection,
            )

        self._run_side_effect(
            side_effect_name="rag_log",
            operation=lambda: rag_log_service.replace_task_rows(
                user_id=user_id,
                task_id=task_id,
                rows=write_bundle.rag_log_rows,
            ),
            task_id=task_id,
        )
        self._run_side_effect(
            side_effect_name="agent_log",
            operation=lambda: agent_log_service.replace_task_rows(
                user_id=user_id,
                task_id=task_id,
                rows=write_bundle.agent_log_rows,
            ),
            task_id=task_id,
        )
        for flow_id, payload in write_bundle.trace_payloads:
            self._run_side_effect(
                side_effect_name="trace",
                operation=lambda flow_id=flow_id, payload=payload: trace_writer.write(
                    task_id=task_id,
                    flow_id=flow_id,
                    payload=payload,
                ),
                task_id=task_id,
                flow_id=flow_id,
            )
        for ledger_row in write_bundle.ledger_rows:
            queue_row = queue_service.get_row(
                user_id=user_id,
                task_id=task_id,
                flow_id=ledger_row.flow_id,
            )
            if queue_row is None:
                continue
            self._run_side_effect(
                side_effect_name="memory",
                operation=lambda ledger_row=ledger_row, queue_row=queue_row: memory_manager.update_after_decision(
                    user_id=user_id,
                    thread_id=task_id,
                    error_type=ledger_row.error_type,
                    decision={
                        "queue_id": queue_row["id"],
                        "flow_id": ledger_row.flow_id,
                        "risk_level": queue_row["risk_level"],
                        "decision": ledger_row.handle_status,
                        "confidence": ledger_row.ai_confidence,
                        "exception_branch": ledger_row.exception_branch,
                        "bank_amount": ledger_row.bank_amount,
                        "clear_amount": ledger_row.clear_amount,
                        "amount_diff": ledger_row.discrepancy_amount,
                        "ai_suggestion": queue_row["status"],
                        "summary": queue_row.get("error_type"),
                    },
                    is_human_confirmed=False,
                ),
                task_id=task_id,
                flow_id=ledger_row.flow_id,
            )

    def _build_write_bundle(
        self,
        *,
        user_id: str,
        task_id: str,
        scenario_type: str,
        results: list[ReconciliationMatchResult],
        emitter: StreamEmitter | None = None,
    ) -> ReconciliationWriteBundle:
        rows: list[LedgerRow] = []
        rag_log_rows: list[dict[str, object]] = []
        agent_log_rows: list[dict[str, object]] = []
        trace_payloads: list[tuple[str, dict[str, object]]] = []
        ai_processed_rows = 0
        fallback_l2_rows = 0
        fallback_l3_rows = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        saved_prompt_tokens = 0
        saved_completion_tokens = 0
        stream_seq = 0
        for result in results:
            if result.status == "AUTO_FIXED":
                continue

            rag_query = self._build_rag_query(result)
            rule_hit = {
                "error_type": result.error_type or "",
                "exception_branch": result.exception_branch,
            }
            try:
                workflow_kwargs = {
                    "user_id": user_id,
                    "task_id": task_id,
                    "scenario_type": scenario_type,
                    "result": result,
                    "rag_query": rag_query,
                }
                if emitter is not None:
                    workflow_kwargs["emitter"] = emitter
                    workflow_kwargs["stream_seq_start"] = stream_seq
                workflow_state = self._run_workflow_for_result(**workflow_kwargs)
                if emitter is not None:
                    stream_seq = int(workflow_state.get("stream_seq", stream_seq))
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
            consumed_logs = [
                row for row in workflow_state["agent_logs"] if not row.get("cached", False)
            ]
            cached_logs = [row for row in workflow_state["agent_logs"] if row.get("cached", False)]
            prompt_tokens = sum(int(row.get("prompt_tokens", 0)) for row in consumed_logs)
            completion_tokens = sum(
                int(row.get("completion_tokens", 0)) for row in consumed_logs
            )
            saved_prompt_tokens += sum(int(row.get("prompt_tokens", 0)) for row in cached_logs)
            saved_completion_tokens += sum(
                int(row.get("completion_tokens", 0)) for row in cached_logs
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
                post_hook_results=self._post_hook_results(workflow_state),
                prompt_version=self._prompt_version_from_logs(workflow_state["agent_logs"]),
                fallback_level=audit_decision.fallback_level,
                llm_tokens=llm_tokens,
            ))
            trace_payloads.append((
                result.flow_id,
                {
                    "task_id": task_id,
                    "flow_id": result.flow_id,
                    "user_id": user_id,
                    "rule_hit": rule_hit,
                    "rag_hit": rag_hit,
                    "agent_output": agent_output,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            ))
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
        return ReconciliationWriteBundle(
            ledger_rows=rows,
            rag_log_rows=rag_log_rows,
            agent_log_rows=agent_log_rows,
            trace_payloads=trace_payloads,
            ai_processed_rows=ai_processed_rows,
            fallback_l2_rows=fallback_l2_rows,
            fallback_l3_rows=fallback_l3_rows,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            saved_prompt_tokens=saved_prompt_tokens,
            saved_completion_tokens=saved_completion_tokens,
        )

    def _run_side_effect(
        self,
        *,
        side_effect_name: str,
        operation: Callable[[], object],
        task_id: str,
        flow_id: str | None = None,
    ) -> None:
        try:
            operation()
        except Exception as exc:
            log.warning(
                "reconciliation_side_effect_failed",
                task_id=task_id,
                flow_id=flow_id,
                side_effect_failed=side_effect_name,
                error_type=type(exc).__name__,
            )

    def _run_workflow_for_result(
        self,
        *,
        user_id: str,
        task_id: str,
        scenario_type: str,
        result: ReconciliationMatchResult,
        rag_query: str,
        stream_seq_start: int = 0,
        emitter: StreamEmitter | None = None,
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
        state = {
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
            "stream_seq": stream_seq_start,
            "rag_query": rag_query,
            "t1_candidate": result.t1_candidate,
        }
        if emitter is None:
            return run_item(state)
        return run_item(state, emitter=emitter)

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

    def _post_hook_results(self, workflow_state: ReconciliationState) -> dict[str, object]:
        decision_log = next(
            (
                row for row in reversed(workflow_state["agent_logs"])
                if row.get("agent_name") == "DecisionHook"
            ),
            {},
        )
        return {
            "schema_retries": int(workflow_state.get("retry_count", 0)),
            "constraint_violated": list(decision_log.get("violated", [])),
            "decision_route": str(decision_log.get("next_action", workflow_state.get("next_action", ""))),
        }


reconciliation_service = ReconciliationService()

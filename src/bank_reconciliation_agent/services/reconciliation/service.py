"""Application facade for reconciliation requests and task lifecycle.

Stable implementation details live in the sibling ``input``, ``batch``,
``flow`` and ``persistence`` modules. Keep this module focused on ordering
those components and preserving the API/Worker compatibility surface.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError
from fastapi import HTTPException, UploadFile
from bank_reconciliation_agent.agents.audit_agent import AuditDecision
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.schemas.ledger import LedgerQuery
from bank_reconciliation_agent.schemas.reconciliation import (
    ReconciliationAuditDecision,
    ReconciliationExceptionItem,
    ReconciliationExceptionListResponse,
    ReconciliationRagEvidence,
    ReconciliationStartResponse,
    ReconciliationStatusResponse,
    ReconciliationUploadResponse,
)
from bank_reconciliation_agent.services.hooks import auth_hook, validation_hook
from bank_reconciliation_agent.services.exception_router import BranchResult
from bank_reconciliation_agent.services.ledger import ledger_service
from bank_reconciliation_agent.services.queue_client import enqueue_reconciliation
from bank_reconciliation_agent.services.reconciliation.batch import (
    build_write_bundle,
    get_reconciliation_executor as _get_reconciliation_executor,
    merge_flow_bundles,
)
from bank_reconciliation_agent.services.reconciliation.flow import (
    agent_error_workflow_state,
    build_flow_bundle,
    evidence_from_rag_source,
    finalize_recorder,
    format_optional_decimal,
    to_reconciliation_audit_decision,
)
from bank_reconciliation_agent.services.reconciliation.input import (
    build_match_results,
    generate_task_id,
    read_dataframe,
    summarize_match_results,
    to_match_result,
    validate_file_size,
)
from bank_reconciliation_agent.services.reconciliation.persistence import (
    ensure_core_transaction_tables,
    persist_write_bundle,
)
from bank_reconciliation_agent.services.reconciliation.types import (
    ReconciliationFlowBundle,
    ReconciliationMatchResult,
    ReconciliationMatchSummary,
    ReconciliationWriteBundle,
)
from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from bank_reconciliation_agent.services.live_registry import mark_finished, register
from bank_reconciliation_agent.services.stream_emitter import (
    QueueEmitter,
    StreamEmitter,
)
from bank_reconciliation_agent.services.task import task_service
from bank_reconciliation_agent.services.trace import (
    NoOpRecorder,
    TraceRecorder,
)
from bank_reconciliation_agent.services.transactions import transaction_service
from bank_reconciliation_agent.services.workflow import ReconciliationState, run_item
from bank_reconciliation_agent.schemas.trace import TraceSpan


def get_reconciliation_executor():
    """Compatibility export for callers that inspect the flow executor."""

    return _get_reconciliation_executor()


class ReconciliationService:
    def __init__(self) -> None:
        self._engine = get_engine()

    def _ensure_core_transaction_tables(self) -> None:
        ensure_core_transaction_tables(self._engine)

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

        new_force_count = 0
        if existing_task is not None and force:
            new_force_count = existing_task.force_requeue_count + 1

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
            force_requeue_count=new_force_count,
        )
        if new_force_count > 0:
            log.info(
                "force_requeued",
                user_id=user_id,
                task_id=task_id,
                previous_status=existing_task.status,
                force_requeue_count=new_force_count,
                outcome="force_requeued",
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
            status="RUNNING",
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

        task_service.update_status(user_id=user_id, task_id=task_id, status="UPLOADED")

        return ReconciliationUploadResponse(
            task_id=task_id,
            total_bank_rows=len(bank_df),
            total_clear_rows=len(clear_df),
            auto_fixed_rows=match_summary.auto_fixed_rows,
            pending_ai_rows=match_summary.pending_ai_rows,
            pending_human_rows=match_summary.pending_human_rows,
        )

    def _generate_task_id(self, content: object) -> str:
        return generate_task_id(content)

    def _validate_file_size(self, upload_file: UploadFile, content_length: int) -> None:
        validate_file_size(upload_file, content_length)

    def _read_dataframe(self, content: bytes, file_label: str) -> pd.DataFrame:
        return read_dataframe(content, file_label)

    def _build_match_results(
        self,
        bank_df: pd.DataFrame,
        clear_df: pd.DataFrame,
        *,
        scenario_type: str = "BANK_ENTERPRISE",
    ) -> list[ReconciliationMatchResult]:
        return build_match_results(bank_df, clear_df, scenario_type=scenario_type)

    def _to_match_result(self, result: BranchResult) -> ReconciliationMatchResult:
        return to_match_result(result)

    def _summarize_match_results(
        self,
        results: list[ReconciliationMatchResult],
    ) -> ReconciliationMatchSummary:
        return summarize_match_results(results)

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
            task_id=task_id,
            status=task.status,
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
            items.append(
                ReconciliationExceptionItem(
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
                )
            )

        return ReconciliationExceptionListResponse(
            task_id=task_id,
            total=len(items),
            items=items,
        )

    def _format_optional_decimal(self, value: Decimal | None) -> str | None:
        return format_optional_decimal(value)

    def _evidence_from_rag_source(
        self,
        rag_source: str | None,
        *,
        scenario_type: str = "BANK_ENTERPRISE",
    ) -> list[ReconciliationRagEvidence]:
        return evidence_from_rag_source(rag_source, scenario_type=scenario_type)

    def _to_reconciliation_audit_decision(
        self,
        decision: AuditDecision,
    ) -> ReconciliationAuditDecision:
        return to_reconciliation_audit_decision(decision)

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
            queue_rows.append(
                {
                    "task_id": task_id,
                    "flow_id": result.flow_id,
                    "bank_transaction_id": None,
                    "clear_transaction_id": None,
                    "error_type": result.error_type or "",
                    "exception_branch": result.exception_branch,
                    "status": result.status,
                    "risk_level": "MEDIUM",
                    "retry_count": 0,
                }
            )
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
        persist_write_bundle(
            engine=self._engine,
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            queue_rows=queue_rows,
            write_bundle=write_bundle,
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
        return build_write_bundle(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            results=results,
            build_flow=self._build_flow_bundle,
            emitter=emitter,
        )

    @staticmethod
    def _merge_flow_bundles(
        flow_bundles: list[ReconciliationFlowBundle],
    ) -> ReconciliationWriteBundle:
        return merge_flow_bundles(flow_bundles)

    def _build_flow_bundle(
        self,
        result: ReconciliationMatchResult,
        *,
        user_id: str,
        task_id: str,
        scenario_type: str,
        emitter: StreamEmitter | None,
        stream_seq_start: int,
    ) -> ReconciliationFlowBundle:
        return build_flow_bundle(
            result,
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            run_workflow=self._run_workflow_for_result,
            emitter=emitter,
            stream_seq_start=stream_seq_start,
        )

    def _finalize_recorder(
        self,
        recorder: TraceRecorder | NoOpRecorder,
        audit_decision: AuditDecision,
    ) -> list[TraceSpan]:
        return finalize_recorder(recorder, audit_decision)

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
        recorder: TraceRecorder | NoOpRecorder | None = None,
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
            "fuzzy_candidate": result.fuzzy_candidate,
        }
        if recorder is not None:
            state["recorder"] = recorder
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
        recorder: TraceRecorder | NoOpRecorder | None = None,
    ) -> ReconciliationState:
        del recorder
        return agent_error_workflow_state(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            result=result,
            error=error,
        )

reconciliation_service = ReconciliationService()

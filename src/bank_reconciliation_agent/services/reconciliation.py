from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import NamedTuple

import pandas as pd
from fastapi import HTTPException, UploadFile

from bank_reconciliation_agent.agents.audit_agent import AuditDecision, audit_agent
from bank_reconciliation_agent.rag.retriever import rule_retriever
from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchRequest
from bank_reconciliation_agent.schemas.ledger import LedgerRow
from bank_reconciliation_agent.schemas.reconciliation import (
    ReconciliationAuditDecision,
    ReconciliationExceptionItem,
    ReconciliationExceptionListResponse,
    ReconciliationRagEvidence,
    ReconciliationStartResponse,
    ReconciliationStatusResponse,
    ReconciliationUploadResponse,
)
from bank_reconciliation_agent.services.ledger import ledger_service


# MVP-0 上传契约：这些字段与生成的模拟对账单保持一致。
BANK_REQUIRED_COLUMNS = [
    "flow_id",
    "bank_serial_no",
    "accounting_date",
    "accounting_time",
    "value_date",
    "self_account_no_masked",
    "self_account_name_masked",
    "self_bank_name",
    "currency",
    "transaction_type",
    "transaction_direction",
    "amount",
    "debit_amount",
    "credit_amount",
    "fee_amount",
    "balance_after",
    "trade_time",
    "account_no_masked",
    "customer_name_masked",
    "counterparty_account_no_masked",
    "counterparty_name_masked",
    "counterparty_bank_name",
    "channel",
    "summary",
    "purpose",
    "posting_status",
    "branch_no",
    "teller_id",
    "transaction_code",
    "source_system",
    "remark",
]

CLEAR_REQUIRED_COLUMNS = [
    "flow_id",
    "clearing_serial_no",
    "merchant_id",
    "merchant_name",
    "store_name",
    "terminal_id",
    "channel",
    "transaction_type",
    "trade_date",
    "trade_time",
    "settlement_date",
    "amount",
    "transaction_amount",
    "fee_amount",
    "net_amount",
    "currency",
    "status",
    "summary",
    "batch_no",
    "voucher_no",
    "reference_no",
    "merchant_order_no",
    "payer_account_no_masked",
    "payer_name_masked",
    "payee_account_no_masked",
    "payee_name_masked",
    "order_description",
    "remark",
]


class ReconciliationMatchSummary(NamedTuple):
    auto_fixed_rows: int
    pending_ai_rows: int
    pending_human_rows: int


class ReconciliationMatchResult(NamedTuple):
    flow_id: str
    status: str
    error_type: str | None
    bank_amount: Decimal | None
    clear_amount: Decimal | None
    amount_diff: Decimal | None


class ReconciliationTaskRecord(NamedTuple):
    task_id: str
    status: str
    total_bank_rows: int
    total_clear_rows: int
    results: list[ReconciliationMatchResult]


class ReconciliationService:
    """对账任务服务，负责上传解析、任务启动和状态查询等业务编排。"""

    def __init__(self) -> None:
        self._tasks: dict[str, ReconciliationTaskRecord] = {}

    async def upload(
        self,
        bank_file: UploadFile,
        clear_file: UploadFile,
    ) -> ReconciliationUploadResponse:
        """读取双端 Excel，校验字段完整性，并返回上传阶段的基础统计。"""
        bank_df = await self._read_excel(bank_file, "bank_file")
        clear_df = await self._read_excel(clear_file, "clear_file")
        self._validate_columns(bank_df, BANK_REQUIRED_COLUMNS, "bank_file")
        self._validate_columns(clear_df, CLEAR_REQUIRED_COLUMNS, "clear_file")
        match_results = self._build_match_results(bank_df, clear_df)
        match_summary = self._summarize_match_results(match_results)

        task_id = f"TASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._tasks[task_id] = ReconciliationTaskRecord(
            task_id=task_id,
            status="UPLOADED",
            total_bank_rows=len(bank_df),
            total_clear_rows=len(clear_df),
            results=match_results,
        )
        self._write_ledger_entries(task_id, match_results)
        return ReconciliationUploadResponse(
            task_id=task_id,
            total_bank_rows=len(bank_df),
            total_clear_rows=len(clear_df),
            auto_fixed_rows=match_summary.auto_fixed_rows,
            pending_ai_rows=match_summary.pending_ai_rows,
            pending_human_rows=match_summary.pending_human_rows,
        )

    async def _read_excel(self, upload_file: UploadFile, file_label: str) -> pd.DataFrame:
        """把上传文件解析为 DataFrame；文件不可读时转换为 400 业务错误。"""
        # FastAPI 提供异步文件对象；pandas 需要可 seek 的内存字节流。
        contents = await upload_file.read()
        try:
            return pd.read_excel(BytesIO(contents))
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"{file_label} must be a readable Excel file",
            ) from exc

    def _validate_columns(
        self,
        dataframe: pd.DataFrame,
        required_columns: list[str],
        file_label: str,
    ) -> None:
        """检查 DataFrame 是否包含指定文件类型要求的全部字段。"""
        missing_columns = [column for column in required_columns if column not in dataframe.columns]
        if missing_columns:
            raise HTTPException(
                status_code=400,
                detail=f"{file_label} missing required columns: {', '.join(missing_columns)}",
            )

    def _match_transactions(
        self,
        bank_df: pd.DataFrame,
        clear_df: pd.DataFrame,
    ) -> ReconciliationMatchSummary:
        """执行 MVP-0 基础匹配：精确平账、金额差错、单边缺失。"""
        results = self._build_match_results(bank_df, clear_df)
        return self._summarize_match_results(results)

    def _summarize_match_results(
        self,
        results: list[ReconciliationMatchResult],
    ) -> ReconciliationMatchSummary:
        """从结构化对账结果聚合上传和任务状态统计。"""
        return ReconciliationMatchSummary(
            auto_fixed_rows=sum(result.status == "AUTO_FIXED" for result in results),
            pending_ai_rows=sum(result.status == "PENDING_AI" for result in results),
            pending_human_rows=sum(result.status == "PENDING_HUMAN" for result in results),
        )

    def _build_match_results(
        self,
        bank_df: pd.DataFrame,
        clear_df: pd.DataFrame,
    ) -> list[ReconciliationMatchResult]:
        """生成基础对账结果明细，供后续差错队列、RAG 和台账复用。"""
        bank_by_flow_id = self._amounts_by_flow_id(bank_df)
        clear_by_flow_id = self._amounts_by_flow_id(clear_df)
        results: list[ReconciliationMatchResult] = []

        for flow_id in sorted(bank_by_flow_id.keys() | clear_by_flow_id.keys()):
            bank_amount = bank_by_flow_id.get(flow_id)
            clear_amount = clear_by_flow_id.get(flow_id)

            if bank_amount is None or clear_amount is None:
                results.append(
                    ReconciliationMatchResult(
                        flow_id=flow_id,
                        status="PENDING_HUMAN",
                        error_type="SINGLE_SIDE_MISSING",
                        bank_amount=bank_amount,
                        clear_amount=clear_amount,
                        amount_diff=None,
                    )
                )
            elif bank_amount == clear_amount:
                results.append(
                    ReconciliationMatchResult(
                        flow_id=flow_id,
                        status="AUTO_FIXED",
                        error_type=None,
                        bank_amount=bank_amount,
                        clear_amount=clear_amount,
                        amount_diff=Decimal("0.00"),
                    )
                )
            else:
                results.append(
                    ReconciliationMatchResult(
                        flow_id=flow_id,
                        status="PENDING_AI",
                        error_type="AMOUNT_MISMATCH",
                        bank_amount=bank_amount,
                        clear_amount=clear_amount,
                        amount_diff=bank_amount - clear_amount,
                    )
                )

        return results

    def _amounts_by_flow_id(self, dataframe: pd.DataFrame) -> dict[str, Decimal]:
        """按流水号提取标准金额，使用 Decimal 避免浮点比较误差。"""
        return {
            str(row.flow_id): Decimal(str(row.amount)).quantize(Decimal("0.01"))
            for row in dataframe[["flow_id", "amount"]].itertuples(index=False)
        }

    def start(self, task_id: str) -> ReconciliationStartResponse:
        """启动对账工作流；当前 MVP-0 骨架先返回固定运行状态。"""
        return ReconciliationStartResponse(task_id=task_id, status="AI_RUNNING")

    def get_status(self, task_id: str) -> ReconciliationStatusResponse:
        """查询任务状态和基础对账统计。"""
        task = self._get_task(task_id)
        summary = self._summarize_match_results(task.results)
        return ReconciliationStatusResponse(
            task_id=task_id,
            status=task.status,
            auto_fixed_rows=summary.auto_fixed_rows,
            pending_ai_rows=summary.pending_ai_rows,
            ai_processed_rows=0,
            pending_human_rows=summary.pending_human_rows,
            unresolved_rows=summary.pending_ai_rows + summary.pending_human_rows,
        )

    def get_exceptions(self, task_id: str) -> ReconciliationExceptionListResponse:
        """查询待 AI 审计和待人工复核的异常明细。"""
        task = self._get_task(task_id)
        items: list[ReconciliationExceptionItem] = []
        for result in task.results:
            if result.status == "AUTO_FIXED":
                continue

            rag_items = self._retrieve_rag_items(result)
            rag_evidence = [self._to_reconciliation_evidence(item) for item in rag_items]
            audit_decision = audit_agent.decide(
                flow_id=result.flow_id,
                error_type=result.error_type or "",
                bank_amount=self._format_optional_decimal(result.bank_amount),
                clear_amount=self._format_optional_decimal(result.clear_amount),
                amount_diff=self._format_optional_decimal(result.amount_diff),
                evidence=rag_items,
            )
            items.append(
                ReconciliationExceptionItem(
                    flow_id=result.flow_id,
                    status=result.status,
                    error_type=result.error_type or "",
                    bank_amount=self._format_optional_decimal(result.bank_amount),
                    clear_amount=self._format_optional_decimal(result.clear_amount),
                    amount_diff=self._format_optional_decimal(result.amount_diff),
                    rag_evidence=rag_evidence,
                    audit_decision=self._to_reconciliation_audit_decision(audit_decision),
                )
            )

        return ReconciliationExceptionListResponse(
            task_id=task_id,
            total=len(items),
            items=items,
        )

    def _get_task(self, task_id: str) -> ReconciliationTaskRecord:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="reconciliation task not found") from exc

    def _format_optional_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return f"{value:.2f}"

    def _retrieve_rag_items(
        self,
        result: ReconciliationMatchResult,
    ) -> list[RagSearchItem]:
        query = self._build_rag_query(result)
        response = rule_retriever.search(RagSearchRequest(query=query, top_k=2))
        return response.items

    def _build_rag_query(self, result: ReconciliationMatchResult) -> str:
        if result.error_type == "AMOUNT_MISMATCH":
            return (
                "AMOUNT_MISMATCH amount_mismatch 金额差异 对账不平 "
                f"bank_amount={self._format_optional_decimal(result.bank_amount)} "
                f"clear_amount={self._format_optional_decimal(result.clear_amount)} "
                f"amount_diff={self._format_optional_decimal(result.amount_diff)}"
            )
        if result.error_type == "SINGLE_SIDE_MISSING":
            missing_side = "clear" if result.clear_amount is None else "bank"
            return (
                "SINGLE_SIDE_MISSING single_side_missing 单边缺失 查询查复 "
                f"missing_side={missing_side} "
                f"bank_amount={self._format_optional_decimal(result.bank_amount)} "
                f"clear_amount={self._format_optional_decimal(result.clear_amount)}"
            )
        return f"{result.error_type or ''} reconciliation exception"

    def _to_reconciliation_evidence(
        self,
        item: RagSearchItem,
    ) -> ReconciliationRagEvidence:
        return ReconciliationRagEvidence(
            chunk_id=item.chunk_id,
            source=item.source,
            source_name=item.source_name,
            source_url=item.source_url,
            source_file=item.source_file,
            section_title=item.section_title,
            element_type=item.element_type,
            business_tags=item.business_tags,
            score=item.score,
            content=item.content,
        )

    def _to_reconciliation_audit_decision(
        self,
        decision: AuditDecision,
    ) -> ReconciliationAuditDecision:
        return ReconciliationAuditDecision(
            flow_id=decision.flow_id,
            decision=decision.decision,
            risk_level=decision.risk_level,
            reason=decision.reason,
            evidence=[self._to_reconciliation_evidence(item) for item in decision.evidence],
            confidence=decision.confidence,
        )

    def _write_ledger_entries(
        self,
        task_id: str,
        results: list[ReconciliationMatchResult],
    ) -> None:
        rows: list[LedgerRow] = []
        for result in results:
            if result.status == "AUTO_FIXED":
                continue

            rag_items = self._retrieve_rag_items(result)
            audit_decision = audit_agent.decide(
                flow_id=result.flow_id,
                error_type=result.error_type or "",
                bank_amount=self._format_optional_decimal(result.bank_amount),
                clear_amount=self._format_optional_decimal(result.clear_amount),
                amount_diff=self._format_optional_decimal(result.amount_diff),
                evidence=rag_items,
            )
            rows.append(
                LedgerRow(
                    id=0,
                    task_id=task_id,
                    flow_id=result.flow_id,
                    error_type=result.error_type or "",
                    bank_amount=result.bank_amount,
                    clear_amount=result.clear_amount,
                    discrepancy_amount=self._ledger_discrepancy_amount(result),
                    ai_audit_opinion=audit_decision.reason,
                    ai_confidence=Decimal(str(audit_decision.confidence)).quantize(
                        Decimal("0.0001")
                    ),
                    rag_source=", ".join(item.chunk_id for item in rag_items) or None,
                    handle_status=audit_decision.decision,
                )
            )

        ledger_service.replace_task_rows(task_id, rows)

    def _ledger_discrepancy_amount(self, result: ReconciliationMatchResult) -> Decimal:
        if result.amount_diff is not None:
            return abs(result.amount_diff)
        if result.bank_amount is not None:
            return result.bank_amount
        if result.clear_amount is not None:
            return result.clear_amount
        return Decimal("0.00")


reconciliation_service = ReconciliationService()

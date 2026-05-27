from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import NamedTuple

import pandas as pd
from fastapi import HTTPException, UploadFile

from bank_reconciliation_agent.schemas.reconciliation import (
    ReconciliationStartResponse,
    ReconciliationStatusResponse,
    ReconciliationUploadResponse,
)


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


class ReconciliationService:
    """对账任务服务，负责上传解析、任务启动和状态查询等业务编排。"""

    async def upload(
        self,
        bank_file: UploadFile,
        clear_file: UploadFile,
    ) -> ReconciliationUploadResponse:
        """读取双端 Excel，校验字段完整性，并返回上传阶段的基础统计。"""
        # 当前上传阶段只做解析和字段校验；具体对账匹配放到下一步实现。
        bank_df = await self._read_excel(bank_file, "bank_file")
        clear_df = await self._read_excel(clear_file, "clear_file")
        self._validate_columns(bank_df, BANK_REQUIRED_COLUMNS, "bank_file")
        self._validate_columns(clear_df, CLEAR_REQUIRED_COLUMNS, "clear_file")
        match_summary = self._match_transactions(bank_df, clear_df)

        task_id = f"TASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
        bank_by_flow_id = self._amounts_by_flow_id(bank_df)
        clear_by_flow_id = self._amounts_by_flow_id(clear_df)
        shared_flow_ids = bank_by_flow_id.keys() & clear_by_flow_id.keys()

        auto_fixed_rows = 0
        pending_ai_rows = 0
        for flow_id in shared_flow_ids:
            if bank_by_flow_id[flow_id] == clear_by_flow_id[flow_id]:
                auto_fixed_rows += 1
            else:
                pending_ai_rows += 1

        bank_only_rows = len(bank_by_flow_id.keys() - clear_by_flow_id.keys())
        clear_only_rows = len(clear_by_flow_id.keys() - bank_by_flow_id.keys())
        return ReconciliationMatchSummary(
            auto_fixed_rows=auto_fixed_rows,
            pending_ai_rows=pending_ai_rows,
            pending_human_rows=bank_only_rows + clear_only_rows,
        )

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
        """查询任务状态；当前 MVP-0 骨架先返回固定统计结果。"""
        return ReconciliationStatusResponse(
            task_id=task_id,
            status="UPLOADED",
            auto_fixed_rows=0,
            ai_processed_rows=0,
            pending_human_rows=0,
            unresolved_rows=0,
        )


reconciliation_service = ReconciliationService()

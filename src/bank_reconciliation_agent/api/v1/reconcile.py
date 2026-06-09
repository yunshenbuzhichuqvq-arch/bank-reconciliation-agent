from fastapi import APIRouter, Form, HTTPException, UploadFile

from bank_reconciliation_agent.api.dependencies import CurrentUserId
from bank_reconciliation_agent.schemas.common import ApiResponse
from bank_reconciliation_agent.schemas.reconciliation import (
    ReconciliationExceptionListResponse,
    ReconciliationStartResponse,
    ReconciliationStatusResponse,
    ReconciliationUploadResponse,
)
from bank_reconciliation_agent.services.reconciliation import reconciliation_service


router = APIRouter()

VALID_SCENARIO_TYPES = {"BANK_ENTERPRISE", "BANK_CLEARING"}


@router.post("/upload", response_model=ApiResponse[ReconciliationUploadResponse])
async def upload_reconciliation_files(
    bank_file: UploadFile,
    clear_file: UploadFile,
    user_id: CurrentUserId,
    scenario_type: str = Form("BANK_ENTERPRISE"),
) -> ApiResponse[ReconciliationUploadResponse]:
    """上传银行端和清算端 Excel，对文件进行解析和字段校验。"""
    if scenario_type not in VALID_SCENARIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail="scenario_type must be one of: BANK_ENTERPRISE, BANK_CLEARING",
        )
    result = await reconciliation_service.upload(
        user_id=user_id,
        scenario_type=scenario_type,
        bank_file=bank_file,
        clear_file=clear_file,
    )
    return ApiResponse(message="upload success", data=result)


@router.post("/{task_id}/start", response_model=ApiResponse[ReconciliationStartResponse])
async def start_reconciliation(
    task_id: str,
    user_id: CurrentUserId,
) -> ApiResponse[ReconciliationStartResponse]:
    """启动指定对账任务的后续处理流程。"""
    result = reconciliation_service.start(user_id=user_id, task_id=task_id)
    return ApiResponse(message="workflow started", data=result)


@router.get("/{task_id}/status", response_model=ApiResponse[ReconciliationStatusResponse])
async def get_reconciliation_status(
    task_id: str,
    user_id: CurrentUserId,
) -> ApiResponse[ReconciliationStatusResponse]:
    """查询指定对账任务的当前状态和统计结果。"""
    result = reconciliation_service.get_status(user_id=user_id, task_id=task_id)
    return ApiResponse(data=result)


@router.get("/{task_id}/exceptions", response_model=ApiResponse[ReconciliationExceptionListResponse])
async def list_reconciliation_exceptions(
    task_id: str,
    user_id: CurrentUserId,
) -> ApiResponse[ReconciliationExceptionListResponse]:
    """查询指定对账任务的基础异常明细。"""
    result = reconciliation_service.get_exceptions(user_id=user_id, task_id=task_id)
    return ApiResponse(data=result)

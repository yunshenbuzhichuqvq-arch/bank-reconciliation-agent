from fastapi import APIRouter, UploadFile

from bank_reconciliation_agent.schemas.common import ApiResponse
from bank_reconciliation_agent.schemas.reconciliation import (
    ReconciliationStartResponse,
    ReconciliationStatusResponse,
    ReconciliationUploadResponse,
)
from bank_reconciliation_agent.services.reconciliation import reconciliation_service


router = APIRouter()


@router.post("/upload", response_model=ApiResponse[ReconciliationUploadResponse])
async def upload_reconciliation_files(
    bank_file: UploadFile,
    clear_file: UploadFile,
) -> ApiResponse[ReconciliationUploadResponse]:
    result = await reconciliation_service.upload(bank_file=bank_file, clear_file=clear_file)
    return ApiResponse(message="upload success", data=result)


@router.post("/{task_id}/start", response_model=ApiResponse[ReconciliationStartResponse])
async def start_reconciliation(task_id: str) -> ApiResponse[ReconciliationStartResponse]:
    result = reconciliation_service.start(task_id=task_id)
    return ApiResponse(message="workflow started", data=result)


@router.get("/{task_id}/status", response_model=ApiResponse[ReconciliationStatusResponse])
async def get_reconciliation_status(task_id: str) -> ApiResponse[ReconciliationStatusResponse]:
    result = reconciliation_service.get_status(task_id=task_id)
    return ApiResponse(data=result)


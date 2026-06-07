from fastapi import APIRouter

from bank_reconciliation_agent.api.dependencies import CurrentUserId
from bank_reconciliation_agent.schemas.common import ApiResponse
from bank_reconciliation_agent.schemas.review import (
    PendingReviewListResponse,
    ReviewActionRequest,
    ReviewResultResponse,
)
from bank_reconciliation_agent.services.review import review_service


router = APIRouter()


@router.get("/pending", response_model=ApiResponse[PendingReviewListResponse])
async def list_pending_reviews(
    user_id: CurrentUserId,
    task_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ApiResponse[PendingReviewListResponse]:
    result = review_service.list_pending(
        user_id=user_id,
        task_id=task_id,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(data=result)


@router.post("/{queue_id}/approve", response_model=ApiResponse[ReviewResultResponse])
async def approve_review_item(
    queue_id: int,
    request: ReviewActionRequest,
    user_id: CurrentUserId,
) -> ApiResponse[ReviewResultResponse]:
    result = review_service.approve(
        user_id=user_id,
        queue_id=queue_id,
        action=request.action,
        handler_username=request.handler_username,
        remark=request.remark,
    )
    return ApiResponse(data=result)

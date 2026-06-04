from fastapi import APIRouter, Depends

from bank_reconciliation_agent.api.dependencies import require_demo_user
from bank_reconciliation_agent.schemas.common import ApiResponse, Page
from bank_reconciliation_agent.schemas.ledger import LedgerQuery, LedgerRow
from bank_reconciliation_agent.services.ledger import ledger_service


router = APIRouter()


@router.get("", response_model=ApiResponse[Page[LedgerRow]])
async def list_error_ledger(
    task_id: str | None = None,
    scenario_type: str | None = None,
    error_type: str | None = None,
    handle_status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 20,
    user_id: str = Depends(require_demo_user),
) -> ApiResponse[Page[LedgerRow]]:
    """按条件分页查询差错台账；MVP-0 阶段先保留接口契约。"""
    query = LedgerQuery(
        user_id=user_id,
        task_id=task_id,
        scenario_type=scenario_type,
        error_type=error_type,
        handle_status=handle_status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(data=ledger_service.list(query))

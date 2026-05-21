from fastapi import APIRouter

from bank_reconciliation_agent.schemas.common import ApiResponse, Page
from bank_reconciliation_agent.schemas.ledger import LedgerQuery, LedgerRow
from bank_reconciliation_agent.services.ledger import ledger_service


router = APIRouter()


@router.get("", response_model=ApiResponse[Page[LedgerRow]])
async def list_error_ledger(
    task_id: str | None = None,
    error_type: str | None = None,
    handle_status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ApiResponse[Page[LedgerRow]]:
    query = LedgerQuery(
        task_id=task_id,
        error_type=error_type,
        handle_status=handle_status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(data=ledger_service.list(query))


from fastapi import APIRouter

from bank_reconciliation_agent.api.dependencies import CurrentUserId
from bank_reconciliation_agent.schemas.common import ApiResponse
from bank_reconciliation_agent.schemas.metrics import DashboardMetricsResponse
from bank_reconciliation_agent.services.metrics import metrics_service


router = APIRouter()


@router.get("/dashboard", response_model=ApiResponse[DashboardMetricsResponse])
def get_dashboard_metrics(user_id: CurrentUserId) -> ApiResponse[DashboardMetricsResponse]:
    result = metrics_service.get_dashboard(user_id=user_id)
    return ApiResponse(data=result)

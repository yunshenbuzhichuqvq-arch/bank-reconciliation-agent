from fastapi import APIRouter, HTTPException

from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.core.security import create_access_token
from bank_reconciliation_agent.schemas.auth import LoginRequest, TokenData
from bank_reconciliation_agent.schemas.common import ApiResponse
from bank_reconciliation_agent.services.auth import auth_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[TokenData])
def login(request: LoginRequest) -> ApiResponse[TokenData]:
    if not auth_service.authenticate(request.username, request.password):
        log.info("login_failed", username=request.username)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    log.info("login_succeeded", username=request.username)
    return ApiResponse(
        data=TokenData(
            access_token=create_access_token(request.username),
            username=request.username,
        )
    )

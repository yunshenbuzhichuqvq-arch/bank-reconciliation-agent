from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from jwt import InvalidTokenError

from bank_reconciliation_agent.core.security import decode_token


def verify_jwt(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if authorization is None:
        raise HTTPException(status_code=401, detail="Bearer token is required")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    try:
        sub = decode_token(token).get("sub")
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    if not isinstance(sub, str) or not sub:
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    request.state.user_id = sub
    return sub


def get_current_user_id(request: Request) -> str:
    return request.state.user_id


CurrentUserId = Annotated[str, Depends(get_current_user_id)]

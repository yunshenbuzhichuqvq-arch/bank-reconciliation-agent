from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request


DEMO_USER_ID = "demo_user"


def require_demo_user(
    request: Request,
    x_user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
) -> str:
    """MVP-0 演示鉴权：所有业务 API 必须携带固定演示用户。"""
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="X-User-ID header is required")
    if x_user_id != DEMO_USER_ID:
        raise HTTPException(status_code=403, detail="invalid X-User-ID")
    request.state.user_id = x_user_id
    return x_user_id


def get_current_user_id(request: Request) -> str:
    return request.state.user_id


CurrentUserId = Annotated[str, Depends(get_current_user_id)]

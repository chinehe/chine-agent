"""认证接口：登录、刷新令牌、注销、查询当前用户。"""

from typing import Any

from fastapi import APIRouter, status

from chine_agent.api.deps import AuthServiceDep, CurrentUser
from chine_agent.core.exceptions import ErrorResponse
from chine_agent.schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse
from chine_agent.schemas.user import UserResponse

router = APIRouter()

# 让接口文档里展示 401 的响应格式
_UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}
}


@router.post("/login", summary="登录", responses=_UNAUTHORIZED)
async def login(body: LoginRequest, auth: AuthServiceDep) -> TokenResponse:
    return await auth.login(body.username, body.password)


@router.post("/refresh", summary="刷新令牌", responses=_UNAUTHORIZED)
async def refresh(body: RefreshTokenRequest, auth: AuthServiceDep) -> TokenResponse:
    return await auth.refresh(body.refresh_token)


@router.post("/logout", summary="注销", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshTokenRequest, auth: AuthServiceDep) -> None:
    await auth.logout(body.refresh_token)


@router.get("/me", summary="当前登录用户", responses=_UNAUTHORIZED)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)

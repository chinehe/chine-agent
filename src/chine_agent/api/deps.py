"""路由层公共依赖。"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chine_agent.core.config import Settings, get_settings
from chine_agent.core.exceptions import UnauthorizedError
from chine_agent.models import User
from chine_agent.services.auth_service import AuthService


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """每个请求一个会话；请求结束时自动关闭，未提交的事务自动回滚。"""
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session


# 路由函数里这样用：async def handler(session: DbSession): ...
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


# ---------- 认证 ----------
def get_auth_service(
    session: DbSession, settings: Annotated[Settings, Depends(get_settings)]
) -> AuthService:
    return AuthService(session, settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

# auto_error=False：缺少令牌时不用框架默认的英文报错，由下面统一抛出 UnauthorizedError
_bearer_scheme = HTTPBearer(auto_error=False, description="登录接口返回的 access_token")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    auth: AuthServiceDep,
) -> User:
    """从请求头 Authorization: Bearer <access_token> 中解析出当前用户。"""
    if credentials is None:
        raise UnauthorizedError("未登录")
    return await auth.authenticate(credentials.credentials)


# 需要登录的接口加上这个参数即可：async def handler(user: CurrentUser): ...
CurrentUser = Annotated[User, Depends(get_current_user)]

"""路由层公共依赖。"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """每个请求一个会话；请求结束时自动关闭，未提交的事务自动回滚。"""
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session


# 路由函数里这样用：async def handler(session: DbSession): ...
DbSession = Annotated[AsyncSession, Depends(get_db_session)]

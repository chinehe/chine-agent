"""数据库引擎与会话工厂。

引擎(AsyncEngine)内部持有连接池，整个进程只创建一个，在 lifespan 中创建和释放。
会话(AsyncSession)是一次"工作单元"，每个请求单独创建一个，用完即关。
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from chine_agent.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.database_pool_size,  # 常驻连接数
        max_overflow=settings.database_max_overflow,  # 高峰期允许额外创建的连接数
        pool_pre_ping=True,  # 取出连接前先探活，避免拿到已被数据库断开的连接
        pool_recycle=1800,  # 连接最长使用 30 分钟后重建，避免被防火墙或代理静默断开
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False：commit 后对象属性仍可直接读取。
    # 异步模式下若为 True，commit 后访问属性会触发隐式查询并报错。
    return async_sessionmaker(engine, expire_on_commit=False)

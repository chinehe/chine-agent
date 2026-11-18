"""应用入口：创建 FastAPI 实例，挂载路由，管理启动与关闭。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from chine_agent import __version__
from chine_agent.api import health
from chine_agent.api.v1.router import api_router
from chine_agent.core.config import get_settings
from chine_agent.core.exceptions import register_exception_handlers
from chine_agent.core.logging import get_logger, setup_logging
from chine_agent.core.middleware import RequestContextMiddleware
from chine_agent.db.session import create_engine, create_session_factory

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()

    # 启动：创建数据库引擎（连接池）。这里不会立即建立连接，第一次使用时才连接
    engine = create_engine(settings)
    app.state.db_engine = engine
    app.state.session_factory = create_session_factory(engine)
    log.info("app_startup", env=settings.app_env, version=__version__)

    yield

    # 关闭：释放连接池中的所有连接
    await engine.dispose()
    log.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.app_debug,
        lifespan=lifespan,
        # 生产环境不暴露接口文档
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None if settings.is_prod else "/redoc",
        openapi_url=None if settings.is_prod else "/openapi.json",
    )

    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()

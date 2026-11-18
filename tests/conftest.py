"""测试公共配置。

- 使用独立的测试库（开发库名加 _test 后缀），测试开始前重建，并执行全部迁移
- 每个测试结束后清空所有表，测试之间互不影响
"""

import asyncio
import os
from collections.abc import AsyncGenerator

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from chine_agent.core.config import Settings, get_settings
from chine_agent.models import Base, User
from chine_agent.schemas.user import UserCreate
from chine_agent.services.user_service import UserService

# ---------- 测试环境配置：必须在创建 app 之前完成 ----------
# 环境变量优先级高于 .env，这里覆盖的值会生效
_dev_url = make_url(Settings().database_url.get_secret_value())
TEST_DATABASE_URL = _dev_url.set(database=f"{_dev_url.database}_test")

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL.render_as_string(hide_password=False)
os.environ["JWT_SECRET_KEY"] = "test-secret-key-only-for-tests-0123456789"
get_settings.cache_clear()

TEST_USERNAME = "Alice"
TEST_PASSWORD = "Passw0rd!"


async def _recreate_test_database() -> None:
    # CREATE DATABASE 不能在目标库里执行，所以先连到同一实例的 postgres 库
    conn = await asyncpg.connect(
        host=TEST_DATABASE_URL.host,
        port=TEST_DATABASE_URL.port,
        user=TEST_DATABASE_URL.username,
        password=TEST_DATABASE_URL.password,
        database="postgres",
    )
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DATABASE_URL.database}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{TEST_DATABASE_URL.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    """整个测试会话只执行一次：重建测试库，用 Alembic 迁移建表。

    用迁移而不是 Base.metadata.create_all 建表，顺便验证了迁移脚本本身。
    """
    asyncio.run(_recreate_test_database())
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
async def app() -> AsyncGenerator[FastAPI]:
    from chine_agent.main import create_app

    application = create_app()
    # 手动触发 lifespan：创建数据库连接池，测试结束后释放
    async with application.router.lifespan_context(application):
        yield application
        # 清空所有表，保证下一个测试从空库开始
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        async with application.state.db_engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def db_session(app: FastAPI) -> AsyncGenerator[AsyncSession]:
    async with app.state.session_factory() as session:
        yield session


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    """一个可以登录的测试用户。"""
    return await UserService(db_session).create_user(
        UserCreate(username=TEST_USERNAME, password=TEST_PASSWORD)
    )

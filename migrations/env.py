"""Alembic 迁移环境：数据库地址取自应用配置，表结构取自 ORM 模型。"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from chine_agent.core.config import get_settings
from chine_agent.models import Base

config = context.config

# 按 alembic.ini 中的 [loggers] 配置日志（只影响 alembic 命令本身，不影响应用）
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 会对比这份元数据和数据库的实际结构，生成差异。
# 所有模型都要在 chine_agent.models 包里导入，否则会被当成"不存在的表"。
target_metadata = Base.metadata

# 与应用使用同一份配置，不在 alembic.ini 里重复写数据库地址和密码
DATABASE_URL = get_settings().database_url.get_secret_value()

def run_migrations_offline() -> None:
    """离线模式：不连接数据库，只输出 SQL（alembic upgrade head --sql）。"""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_server_default=True,  # 列的数据库默认值变化也生成迁移
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    # 迁移是一次性任务，用 NullPool：不保留连接，跑完即断开
    engine = create_async_engine(DATABASE_URL, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

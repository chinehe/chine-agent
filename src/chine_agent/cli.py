"""管理命令。

用法：
  uv run chine-agent dev                     # 启动开发服务（默认 8888 端口，自动重载）
  uv run chine-agent create-user <用户名>
"""

import argparse
import asyncio
import getpass
import os
import sys

from pydantic import ValidationError

from chine_agent.core.config import get_settings
from chine_agent.core.exceptions import AppError
from chine_agent.db.session import create_engine, create_session_factory
from chine_agent.schemas.user import UserCreate
from chine_agent.services.user_service import UserService


async def _create_user(data: UserCreate) -> None:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            user = await UserService(session).create_user(data)
    finally:
        await engine.dispose()
    print(f"已创建用户：{user.username}（id={user.id}）")


def _cmd_create_user(username: str) -> None:
    password = getpass.getpass("密码：")
    if password != getpass.getpass("确认密码："):
        sys.exit("两次输入的密码不一致")
    try:
        data = UserCreate(username=username, password=password)
    except ValidationError as e:
        errors = "；".join(f"{err['loc'][0]}: {err['msg']}" for err in e.errors())
        sys.exit(f"参数不合法：{errors}")
    try:
        asyncio.run(_create_user(data))
    except AppError as e:
        sys.exit(e.message)


# 本地开发的默认端口。fastapi 命令没有读取端口的配置文件，所以统一从这里启动
DEFAULT_DEV_PORT = 8888


def _cmd_dev(host: str, port: int) -> None:
    """用当前解释器执行 fastapi dev，进程被替换，Ctrl+C 和热重载行为与直接运行 fastapi dev 一致。"""
    os.execv(  # noqa: S606  参数是固定列表，不经过 shell，没有注入风险
        sys.executable,
        [sys.executable, "-m", "fastapi", "dev", "--host", host, "--port", str(port)],
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="chine-agent", description="chine-agent 管理命令")
    commands = parser.add_subparsers(dest="command", required=True)
    create_user = commands.add_parser("create-user", help="创建用户（会提示输入密码）")
    create_user.add_argument("username")
    dev = commands.add_parser("dev", help=f"启动开发服务（默认端口 {DEFAULT_DEV_PORT}，自动重载）")
    dev.add_argument("--host", default="127.0.0.1")
    dev.add_argument("--port", type=int, default=DEFAULT_DEV_PORT)

    args = parser.parse_args()
    if args.command == "create-user":
        _cmd_create_user(args.username)
    elif args.command == "dev":
        _cmd_dev(args.host, args.port)

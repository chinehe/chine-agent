"""v1 版本的路由汇总：各业务模块的 router 在这里统一注册。"""

from fastapi import APIRouter

from chine_agent.api.v1 import auth

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

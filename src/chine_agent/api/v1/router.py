"""v1 版本的路由汇总：各业务模块的 router 在这里统一注册。"""

from fastapi import APIRouter

api_router = APIRouter()

# 第 9 步开始在这里注册业务路由，例如：
# api_router.include_router(users.router, prefix="/users", tags=["users"])

"""健康检查接口，供 K8s 探针、负载均衡器使用。

- /healthz: 存活探针(liveness),进程能响应就返回 200,不检查外部依赖
- /readyz: 就绪探针(readiness),依赖（数据库等）可用才返回 200
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/healthz", summary="存活检查")
async def helthz() -> HealthResponse:
    return HealthResponse()


@router.get("readyz", summary="就绪检查")
async def readyz() -> HealthResponse:
    # TODO 数据库检查
    return HealthResponse()

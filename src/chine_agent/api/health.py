"""健康检查接口,供 K8s 探针、负载均衡器使用。

- /healthz:存活探针（liveness）,进程能响应就返回 200,不检查外部依赖
- /readyz:就绪探针（readiness）,依赖（数据库等）可用才返回 200,否则 503
"""

import asyncio
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from chine_agent.core.logging import get_logger

router = APIRouter(tags=["health"])
log = get_logger(__name__)

READY_CHECK_TIMEOUT_SECONDS = 2


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"] = "ok"


@router.get("/healthz", summary="存活检查")
async def healthz() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/readyz",
    summary="就绪检查",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def readyz(request: Request, response: Response) -> HealthResponse:
    engine: AsyncEngine = request.app.state.db_engine
    try:
        # 加超时:数据库无响应时,探针要尽快得到结果,不能一直挂着
        async with asyncio.timeout(READY_CHECK_TIMEOUT_SECONDS), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        log.warning("readiness_check_failed", check="database", exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="unavailable")
    return HealthResponse()

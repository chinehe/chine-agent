"""统一异常与错误响应。

所有错误响应都是同一个格式，前端和调用方只需按一种结构解析：
{"code": "not_found", "message": "用户不存在", "request_id": "...", "details": null}
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorResponse(BaseModel):
    code: str  # 机器可读的错误码，调用方据此做分支判断
    message: str  # 人可读的错误描述
    request_id: str | None = None  # 排查问题时，用它在日志里搜索这次请求
    details: Any = None  # 补充信息，如参数校验失败的字段列表


# ---------- 业务异常 ----------
class AppError(Exception):
    """业务异常基类。在 service 层抛出，由全局处理器转成统一的错误响应。"""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


# ---------- 错误响应 ----------
def build_error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: Any = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        code=code,
        message=message,
        request_id=structlog.contextvars.get_contextvars().get("request_id"),
        details=details,
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


def _code_from_status(status_code: int) -> str:
    """404 -> "not_found"，405 -> "method_not_allowed"。"""
    try:
        return HTTPStatus(status_code).phrase.lower().replace(" ", "_")
    except ValueError:
        return "http_error"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return build_error_response(exc.status_code, exc.code, exc.message, details=exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # 框架抛出的 HTTP 错误，如路由不存在（404）、请求方法不允许（405）
        return build_error_response(
            exc.status_code,
            _code_from_status(exc.status_code),
            exc.detail,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 只返回字段位置、原因和类型，不回显用户提交的原始值（可能含密码等敏感信息）
        details = [
            {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
        ]
        return build_error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "请求参数校验失败",
            details=details,
        )

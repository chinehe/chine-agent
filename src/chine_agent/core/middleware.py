"""请求上下文中间件：分配 request_id、记录访问日志、兜底未处理异常。

用纯 ASGI 写法而不是 BaseHTTPMiddleware：后者对流式响应（如 SSE）支持不好，
且有已知的上下文变量传递问题。
"""

import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from chine_agent.core.exceptions import build_error_response
from chine_agent.core.logging import get_logger

log = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
# 只接受安全字符，防止调用方通过请求头往日志里注入换行等内容
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
# 探针每隔几秒请求一次，记录访问日志只会刷屏
_SKIP_ACCESS_LOG_PATHS = frozenset({"/healthz", "/readyz"})


def _get_or_create_request_id(scope: Scope) -> str:
    """优先沿用上游（网关、前端）传来的 X-Request-ID，便于跨服务追踪。"""
    for name, value in scope["headers"]:
        if name == b"x-request-id":
            candidate: str = value.decode("latin-1")
            if _VALID_REQUEST_ID.fullmatch(candidate):
                return candidate
            break
    return uuid.uuid4().hex


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _get_or_create_request_id(scope)
        status_code = 500
        response_started = False
        start = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        # 绑定后，这个请求内的所有日志都会自动带上 request_id
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception:
                log.exception("unhandled_exception")
                if response_started:
                    raise  # 响应已开始发送，无法再改成 500，交给服务器断开连接
                # 不把异常细节返回给调用方，细节只记在日志里
                response = build_error_response(500, "internal_error", "服务器内部错误")
                await response(scope, receive, send_with_request_id)
            finally:
                if scope["path"] not in _SKIP_ACCESS_LOG_PATHS:
                    log.info(
                        "http_request",
                        method=scope["method"],
                        path=scope["path"],
                        status=status_code,
                        duration_ms=round((time.perf_counter() - start) * 1000, 2),
                    )

"""日志配置： structlog 与标准库 logging 统一输出格式.

- dev/test: 彩色易读的控制台可视
- prod: 每行一条JSON,便于日志平台采集检索
"""

import logging
import sys

import structlog
from structlog.tracebacks import ExceptionDictTransformer
from structlog.types import EventDict, Processor, WrappedLogger

from chine_agent.core.config import Settings


def _drop_color_message(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """uvicorn 会在 extra 里附带一份带颜色控制符的 color_message，与 event 重复，去掉。"""
    event_dict.pop("color_message", None)
    return event_dict


def setup_logging(setting: Settings) -> None:
    # structlog 日志与第三方库（univorn、sqlalchemy等）的标准库日志公用的处理链
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,  # 合并上下文变量，如request_id
        structlog.stdlib.add_log_level,  # 增加level字段
        structlog.stdlib.add_logger_name,  # 增加logger_name字段
        structlog.stdlib.ExtraAdder(),  # 支持标准库的logger.info("...",extra={...})
        _drop_color_message,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    renderer: list[Processor]
    if setting.is_prod:
        renderer = [
            # 异常堆栈转成 JSON；不输出局部变量，避免密码、token 写进日志
            structlog.processors.ExceptionRenderer(ExceptionDictTransformer(show_locals=False)),
            structlog.processors.JSONRenderer(),
        ]
    else:
        renderer = [structlog.dev.ConsoleRenderer()]

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *renderer],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(setting.log_level)

    # uvicorn 自带 handler，清掉后交给 root 统一输出，避免格式不一致或重复打印
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    # 访问日志改由 RequestContextMiddleware 输出（带 request_id 和耗时），
    # 关掉 uvicorn 自带的，避免重复
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)

# syntax=docker/dockerfile:1

# ============ 构建阶段：安装依赖，生成虚拟环境 ============
FROM ghcr.io/astral-sh/uv:0.11-python3.12-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# 先只装第三方依赖：只要 pyproject.toml 和 uv.lock 不变，这一层就走缓存，改业务代码不会重装依赖
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# 再装项目本身。--no-editable：代码直接装进虚拟环境，运行阶段不需要 src 目录
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ============ 运行阶段：只包含运行所需的文件 ============
FROM python:3.12-slim-trixie

# 用非 root 用户运行：即使应用被攻破，攻击者也拿不到容器内的 root 权限
RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
# 数据库迁移需要的文件（迁移作为单独的任务执行，见 docker-compose.yml）
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8888

# 运行阶段没有 pyproject.toml，读不到 [tool.fastapi] entrypoint，所以这里显式指定
CMD ["fastapi", "run", "--entrypoint", "chine_agent.main:app", "--host", "0.0.0.0", "--port", "8888"]

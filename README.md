# chine-agent

ChineHe Agent 后端服务，基于 FastAPI + PostgreSQL 构建。

| 类别 | 选型 |
|---|---|
| 语言 / 包管理 | Python 3.12 / [uv](https://docs.astral.sh/uv/) |
| Web 框架 | FastAPI（Uvicorn） |
| 数据库 | PostgreSQL 17、SQLAlchemy 2.0（异步，asyncpg 驱动）、Alembic 迁移 |
| 配置 | pydantic-settings（环境变量 / `.env`） |
| 日志 | structlog（开发环境彩色输出，生产环境 JSON） |
| 认证 | JWT access token + 存库的 refresh token（Argon2id 密码哈希） |
| 质量 | ruff（lint + 格式化）、mypy（strict）、pytest、pre-commit |
| 交付 | Docker 多阶段构建、docker compose |

## 目录

- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [配置项](#配置项)
- [常用命令](#常用命令)
- [接口说明](#接口说明)
- [认证机制](#认证机制)
- [数据库迁移](#数据库迁移)
- [测试](#测试)
- [代码规范与 pre-commit](#代码规范与-pre-commit)
- [日志与请求追踪](#日志与请求追踪)
- [Docker 与部署](#docker-与部署)
- [开发一个新功能](#开发一个新功能)
- [常见问题](#常见问题)

---

## 快速开始

### 1. 准备环境

| 工具 | 用途 | 安装 |
|---|---|---|
| uv | 管理 Python 版本、依赖和虚拟环境 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker Desktop | 运行本地 PostgreSQL | <https://www.docker.com/products/docker-desktop/> |

Python 本身不需要单独安装，uv 会按 `.python-version` 自动下载 3.12。

### 2. 安装依赖

```bash
git clone <仓库地址> chine-agent
cd chine-agent

uv sync                         # 创建 .venv 并安装全部依赖（含开发依赖）
uv run pre-commit install       # 安装提交前检查的 git 钩子（每次克隆后执行一次）
```

### 3. 准备配置文件

```bash
cp .env.example .env

# 生成 JWT 签名密钥并写入 .env
uv run python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

把输出的字符串填到 `.env` 的 `JWT_SECRET_KEY=` 后面。其余配置保持默认即可，含义见 [配置项](#配置项)。

> `.env` 已被 `.gitignore` 和 `.dockerignore` 排除，不会提交到仓库，也不会打进镜像。

### 4. 启动数据库并建表

```bash
docker compose up -d            # 只启动 PostgreSQL
docker compose ps               # 等待 STATUS 显示 (healthy)

uv run alembic upgrade head     # 执行全部迁移，创建表结构
```

### 5. 创建用户

项目不开放注册接口，用户由管理员通过命令行创建：

```bash
uv run chine-agent create-user <用户名>
```

按提示输入两次密码（至少 8 位，输入时不显示）。用户名区分大小写，只允许字母、数字和 `_ . -`，长度 3 到 50。

### 6. 启动服务

```bash
uv run chine-agent dev
```

| 地址 | 说明 |
|---|---|
| <http://127.0.0.1:8888/docs> | Swagger 接口文档，可以直接调试接口 |
| <http://127.0.0.1:8888/healthz> | 存活检查 |
| <http://127.0.0.1:8888/readyz> | 就绪检查（会检查数据库连接） |

默认端口 8888，代码改动后自动重启；需要换端口时用 `uv run chine-agent dev --port <端口>`。不要直接运行 `uv run fastapi dev`，它没有读取端口的配置，会用默认的 8000。在 Swagger 里调试需要登录的接口时：先调用 `POST /api/v1/auth/login`，把返回的 `access_token` 填到页面右上角的 **Authorize** 里。

---

## 项目结构

```
chine-agent/
├── src/chine_agent/
│   ├── main.py                 # 应用入口：create_app()、lifespan（连接池的创建与释放）
│   ├── cli.py                  # 管理命令：chine-agent create-user
│   ├── api/                    # 接口层：参数解析、调用 service、返回响应
│   │   ├── deps.py             #   公共依赖：DbSession、AuthServiceDep、CurrentUser
│   │   ├── health.py           #   /healthz、/readyz
│   │   └── v1/
│   │       ├── router.py       #   v1 路由汇总，新模块在这里注册
│   │       └── auth.py         #   /api/v1/auth/*
│   ├── services/               # 业务逻辑层：业务规则、事务提交
│   ├── repositories/           # 数据访问层：只执行 SQL
│   ├── models/                 # ORM 模型（对应数据库表）
│   ├── schemas/                # Pydantic 模型（接口的输入输出）
│   ├── db/session.py           # 数据库引擎与会话工厂
│   └── core/                   # 基础设施
│       ├── config.py           #   配置（Settings）
│       ├── logging.py          #   日志
│       ├── exceptions.py       #   业务异常与统一错误响应
│       ├── middleware.py       #   request_id、访问日志、未处理异常兜底
│       └── security.py         #   密码哈希、JWT、refresh token
├── migrations/                 # Alembic 迁移脚本
├── tests/                      # 测试
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml              # 依赖与工具配置（ruff、mypy、pytest、coverage）
└── .pre-commit-config.yaml
```

### 分层约定

一个请求依次经过下面几层，**只允许上层调用下层**：

```
api（接口层） → services（业务层） → repositories（数据访问层） → models（ORM 模型）
```

| 层 | 负责 | 不该做的事 |
|---|---|---|
| api | 解析参数、声明依赖、把 service 的结果转成响应 | 写业务判断、直接写 SQL |
| services | 业务规则、权限判断、**决定何时 `commit`**、抛出业务异常 | 依赖 `Request`、返回 HTTP 状态码 |
| repositories | 增删改查，最多 `flush`，**不 `commit`** | 包含业务规则 |
| models / schemas | 分别描述数据库表、接口数据结构 | 混用：不要把 ORM 对象直接作为响应返回 |

`schemas` 与 `models` 分开是有意的：例如 `UserResponse` 里没有 `password_hash`，避免敏感字段被意外返回。

---

## 配置项

配置定义在 `src/chine_agent/core/config.py`，启动时统一校验，缺少必填项或格式错误会直接启动失败。

**读取优先级：系统环境变量 > `.env` 文件 > 默认值。** 变量名不区分大小写。

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `APP_ENV` | | `dev` | 运行环境：`dev` / `test` / `prod`。`prod` 时日志输出 JSON，并关闭 `/docs` |
| `APP_DEBUG` | | `false` | FastAPI 调试模式 |
| `LOG_LEVEL` | | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `DATABASE_URL` | ✅ | | 必须是 PostgreSQL 地址，如 `postgresql+asyncpg://user:pass@host:5432/db` |
| `DATABASE_POOL_SIZE` | | `10` | 连接池常驻连接数 |
| `DATABASE_MAX_OVERFLOW` | | `20` | 高峰期允许额外创建的连接数 |
| `JWT_SECRET_KEY` | ✅ | | JWT 签名密钥，至少 32 个字符。泄露后任何人都能伪造令牌 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | | `15` | access token 有效期（分钟） |
| `REFRESH_TOKEN_EXPIRE_DAYS` | | `7` | refresh token 有效期（天） |

新增配置项时，同步更新 `Settings`、`.env.example` 和本表。

---

## 常用命令

| 命令 | 作用 |
|---|---|
| `uv run chine-agent dev` | 启动开发服务（默认 8888 端口，自动重载） |
| `uv run chine-agent create-user <用户名>` | 创建用户 |
| `uv run pytest` | 运行全部测试 |
| `uv run pytest --cov --cov-report=term-missing` | 运行测试并查看覆盖率 |
| `uv run ruff check --fix` | 代码检查并自动修复 |
| `uv run ruff format` | 格式化代码 |
| `uv run mypy src` | 类型检查 |
| `uv run pre-commit run --all-files` | 对所有文件执行提交前检查 |
| `uv run alembic upgrade head` | 执行迁移到最新版本 |
| `uv run alembic revision --autogenerate -m "说明"` | 根据模型变化生成迁移 |
| `docker compose up -d` | 启动本地数据库 |
| `docker compose --profile app up -d --build` | 以生产形态启动全套服务（数据库 + 迁移 + 应用） |
| `uv add <包名>` / `uv add --dev <包名>` | 添加运行依赖 / 开发依赖 |

---

## 接口说明

| 方法 | 路径 | 需要登录 | 说明 |
|---|---|---|---|
| GET | `/healthz` | | 存活检查，进程能响应就返回 200 |
| GET | `/readyz` | | 就绪检查，数据库可用返回 200，否则 503 |
| POST | `/api/v1/auth/login` | | 登录，返回 access token 和 refresh token |
| POST | `/api/v1/auth/refresh` | | 用 refresh token 换一组新令牌 |
| POST | `/api/v1/auth/logout` | | 注销，作废本次登录的 refresh token |
| GET | `/api/v1/auth/me` | ✅ | 当前登录用户信息 |

完整的请求和响应结构以 `/docs` 为准。

### 统一错误响应

所有错误（业务异常、参数校验失败、路由不存在、服务器内部错误）都返回同一种结构：

```json
{
  "code": "not_found",
  "message": "用户不存在",
  "request_id": "4b62b09387d840b0a2333bf53a6b5b6f",
  "details": null
}
```

| 字段 | 说明 |
|---|---|
| `code` | 机器可读的错误码，调用方据此做分支判断 |
| `message` | 给人看的描述 |
| `request_id` | 与响应头 `X-Request-ID` 一致，排查问题时用它在日志里搜索 |
| `details` | 补充信息，例如参数校验失败时的字段列表 |

常见错误码：

| HTTP 状态码 | `code` | 场景 |
|---|---|---|
| 400 | `bad_request` | 通用业务错误 |
| 401 | `unauthorized` | 未登录、令牌无效或过期、用户名或密码错误 |
| 404 | `not_found` | 资源或路由不存在 |
| 405 | `method_not_allowed` | 请求方法不允许 |
| 409 | `conflict` | 数据冲突，如用户名已存在 |
| 422 | `validation_error` | 请求参数校验失败 |
| 500 | `internal_error` | 服务器内部错误（细节只记录在日志中，不返回给调用方） |

---

## 认证机制

采用 **短期 access token + 长期 refresh token**：

| 令牌 | 格式 | 有效期 | 存储 | 用途 |
|---|---|---|---|---|
| access token | JWT（HS256） | 15 分钟 | 不存库 | 放在请求头 `Authorization: Bearer <token>` 中访问接口 |
| refresh token | 32 字节随机串 | 7 天 | 数据库只存 SHA-256 哈希 | 调用 `/auth/refresh` 换取新令牌 |

### 关键行为

- **刷新时轮换**：每次刷新都会作废旧的 refresh token，并返回一个新的。
- **复用检测**：已作废的 refresh token 如果再次被使用，说明它可能被盗用。此时会作废这次登录产生的全部令牌，双方都需要重新登录，并在日志中记录 `refresh_token_reuse_detected`。
- **注销**：作废本次登录的 refresh token，不影响该用户在其他设备上的登录。**已签发的 access token 无法撤回，最多还能使用 15 分钟。**
- **账号停用**：每次校验 access token 都会查询用户状态，账号停用后令牌立即失效。
- **防用户名探测**：用户不存在和密码错误返回相同的提示，耗时也相同。

### 前端接入要点

```mermaid
sequenceDiagram
    participant FE as 前端
    participant API as chine-agent
    FE->>API: POST /auth/login
    API-->>FE: access_token + refresh_token
    FE->>API: 业务请求（Bearer access_token）
    API-->>FE: 401（access token 过期）
    FE->>API: POST /auth/refresh（refresh_token）
    API-->>FE: 新的 access_token + refresh_token
    FE->>API: 用新 access_token 重试原请求
    Note over FE,API: refresh 也返回 401 时跳转登录页
```

1. 接口返回 401 时，调用一次 `/auth/refresh`，成功后用新的 access token 重试原请求；refresh 也返回 401 就跳转登录页。
2. 每次刷新后**必须保存新的 refresh token**，旧的已经作废。
3. **刷新请求必须串行**：同一时刻只发一个刷新请求，其他请求等待它完成后用新令牌重试。用同一个 refresh token 并发刷新会触发复用检测，导致整个登录失效。
4. 注销时调用 `/auth/logout` 并删除本地保存的两个令牌。注销只需要 refresh token，access token 过期了也能正常注销。

### 在接口中要求登录

```python
from chine_agent.api.deps import CurrentUser

@router.get("/something")
async def handler(user: CurrentUser) -> ...:
    # user 是当前登录的 User 对象；未登录时框架已自动返回 401
    ...
```

---

## 数据库迁移

表结构的每次变化都通过 Alembic 迁移脚本记录，脚本提交到仓库。迁移读取的是应用同一份配置（`DATABASE_URL`），不需要在 `alembic.ini` 里写数据库地址。

### 修改表结构的流程

```bash
# 1. 修改或新增 models/ 下的模型；新模型要在 models/__init__.py 中导入
# 2. 自动生成迁移脚本（文件名以时间开头，生成后自动格式化）
uv run alembic revision --autogenerate -m "add xxx table"

# 3. 打开 migrations/versions/ 下新生成的文件，人工检查
# 4. 执行迁移
uv run alembic upgrade head

# 5. 确认模型与数据库一致
uv run alembic check
```

### 规则

1. **自动生成的脚本必须人工检查后再提交。** autogenerate 识别不了"改名"，字段改名会被生成成"删除旧列 + 新增新列"，导致数据丢失。
2. **已提交、已在其他环境执行过的迁移文件不要修改**，需要调整就新建一个迁移。
3. 约束命名规则已在 `models/base.py` 中配置（如 `pk_users`、`uq_users_username`），不要手写约束名。

### 其他常用命令

| 命令 | 作用 |
|---|---|
| `uv run alembic current` | 查看数据库当前版本 |
| `uv run alembic history` | 查看迁移历史 |
| `uv run alembic downgrade -1` | 回退一个版本 |
| `uv run alembic upgrade head --sql` | 只输出 SQL 不执行（适合需要 DBA 审核的场景） |

---

## 测试

```bash
docker compose up -d            # 测试使用真实的 PostgreSQL，需要数据库在运行
uv run pytest
```

- **测试库独立**：自动使用 `<开发库名>_test`（默认 `chine_agent_test`），每次运行前重建，并通过 Alembic 迁移建表（迁移脚本本身也因此被测到）。开发库数据不受影响。
- **测试间隔离**：每个测试结束后清空所有表。
- **配置覆盖**：`tests/conftest.py` 会覆盖 `APP_ENV`、`DATABASE_URL`、`JWT_SECRET_KEY`，不会使用 `.env` 里的密钥。

### 可用的 fixture

| fixture | 说明 |
|---|---|
| `client` | `httpx.AsyncClient`，直接调用应用，无需启动服务 |
| `app` | FastAPI 应用实例（已执行 lifespan） |
| `db_session` | 数据库会话，用于在测试中准备或修改数据 |
| `user` | 一个已创建的测试用户，用户名 `TEST_USERNAME`，密码 `TEST_PASSWORD` |

示例：

```python
async def test_me(client: AsyncClient, user: User) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
```

测试函数写成 `async def` 即可，不需要额外的装饰器（已配置 `asyncio_mode = "auto"`）。

---

## 代码规范与 pre-commit

每次 `git commit` 前自动执行以下检查，不通过则提交失败：

| 检查 | 内容 |
|---|---|
| pre-commit-hooks | 行尾空格、文件末尾换行、YAML / TOML 语法、合并冲突标记、大文件、私钥 |
| ruff check | 代码规范与常见 bug（含安全规则），能自动修复的会自动修复 |
| ruff format | 代码格式 |
| mypy | 严格模式类型检查（`src` 目录） |

**提交失败时：**

- 提示 `files were modified by this hook`：问题已自动修复，重新 `git add` 后再提交。
- ruff 或 mypy 报具体错误：按提示修改，然后重新 `git add` 并提交。

**约定：**

- 行宽 100，import 顺序由 ruff 自动整理。
- 所有函数都要写类型注解（mypy strict）。
- 注释、文档字符串可以使用中文和全角标点。
- 推荐在编辑器中安装 Ruff 扩展，并开启保存时自动格式化。

---

## 日志与请求追踪

### 写日志

```python
from chine_agent.core.logging import get_logger

log = get_logger(__name__)

log.info("order_created", order_id=order.id, amount=100)   # ✅ 事件名 + 键值对
log.info(f"order {order.id} created")                       # ❌ 不要把变量拼进字符串
```

- 第一个参数是**事件名**，使用 snake_case；变量放在键值对里，便于按字段检索。
- 不要在日志里记录密码、令牌等敏感信息。
- 开发环境输出彩色可读格式，`APP_ENV=prod` 时每行一条 JSON。

### request_id

- 每个请求都会分配一个 `request_id`，通过响应头 `X-Request-ID` 返回。
- 如果请求头里带了合法的 `X-Request-ID`（字母、数字、`._-`，最长 64 位），会沿用上游传来的值，便于跨服务追踪。
- 该请求内输出的**所有日志都会自动带上 `request_id`**。用户反馈问题时，拿到响应里的 `request_id`，就能在日志里找到这次请求的全部记录。

### 访问日志

每个请求结束后输出一条 `http_request` 日志，包含 `method`、`path`、`status`、`duration_ms`。`/healthz` 和 `/readyz` 不记录访问日志，避免探针刷屏。

---

## Docker 与部署

### 本地以生产形态运行

```bash
docker compose --profile app up -d --build
docker compose --profile app ps -a
```

| 服务 | 说明 |
|---|---|
| `postgres` | 数据库，`docker compose up -d` 时也会启动 |
| `migrate` | 执行 `alembic upgrade head` 后退出，状态显示 `Exited (0)` 为正常 |
| `app` | 应用，迁移成功后才启动，映射到宿主机 **8080** 端口 |

- 加 `--profile app` 才会启动 `migrate` 和 `app`；日常开发的 `docker compose up -d` 只启动数据库。
- 容器使用 `APP_ENV=prod`：日志为 JSON，`/docs` 关闭。
- `JWT_SECRET_KEY` 从宿主机的 `.env` 或环境变量读取，未设置时 compose 会直接报错。
- 在容器中创建用户：`docker compose exec app chine-agent create-user <用户名>`
- 停止：`docker compose --profile app down`（**不要加 `-v`**，否则会删除数据库数据）

### 镜像说明

- 多阶段构建：构建阶段用 uv 安装依赖，运行阶段只包含虚拟环境、`alembic.ini` 和 `migrations/`。
- 以非 root 用户 `app` 运行。
- 依赖层单独缓存，只改业务代码时重新构建很快。
- `uv sync --locked`：`uv.lock` 与 `pyproject.toml` 不一致时构建失败，保证镜像中的依赖版本与本地一致。

### 部署到 Kubernetes 的要点

| 事项 | 做法 |
|---|---|
| 数据库迁移 | 部署前用 Job 或 initContainer 执行 `alembic upgrade head`，不要在应用启动时执行 |
| 密钥 | `JWT_SECRET_KEY`、`DATABASE_URL` 放在 Secret 中，以环境变量注入 |
| 存活探针 | `livenessProbe` → `GET /healthz` |
| 就绪探针 | `readinessProbe` → `GET /readyz`，`timeoutSeconds` 至少设为 3（接口内部数据库检查超时为 2 秒） |
| 扩容 | 每个 Pod 运行一个进程，通过增加副本数扩容 |
| 镜像标签 | 使用 git commit hash，便于回滚 |

---

## 开发一个新功能

以新增一个"会话（conversation）"模块为例：

1. **模型**：在 `models/` 下新建 `conversation.py`，继承 `Base`（需要创建、更新时间就同时继承 `TimestampMixin`），并在 `models/__init__.py` 中导入。
2. **迁移**：`uv run alembic revision --autogenerate -m "add conversations"`，检查后执行 `uv run alembic upgrade head`。
3. **数据访问**：在 `repositories/` 下新建 `conversation_repository.py`，只写查询和写入。
4. **接口数据结构**：在 `schemas/` 下定义请求和响应模型，响应模型用 `ConfigDict(from_attributes=True)` 从 ORM 对象构造。
5. **业务逻辑**：在 `services/` 下新建 `conversation_service.py`。在这里做业务判断、`commit`，出错时抛出 `NotFoundError`、`ConflictError` 等业务异常（定义在 `core/exceptions.py`）。
6. **接口**：在 `api/v1/` 下新建 `conversations.py`，需要登录的接口加上 `user: CurrentUser` 参数。
7. **注册路由**：在 `api/v1/router.py` 中加上 `api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])`。
8. **测试**：在 `tests/` 下新建 `test_conversations.py`。
9. **提交前**：`uv run pytest` 全部通过，然后提交（pre-commit 会自动检查格式和类型）。

需要新的错误类型时，继承 `AppError`，设置 `status_code` 和 `code` 即可，全局异常处理器会自动转换成统一的错误响应。

---

## 常见问题

**修改了 `.env` 但没有生效**

系统环境变量的优先级高于 `.env`。执行 `echo $DATABASE_URL` 检查当前终端是否已经存在同名变量（部分 IDE 会自动把 `.env` 注入终端）。如果存在，新开一个终端或用 `unset` 清除。

**`/readyz` 返回 503**

数据库连不上。查看服务日志里的 `readiness_check_failed`，后面的异常信息说明了具体原因：

| 异常信息 | 原因 |
|---|---|
| `Connection refused` | 数据库没启动，执行 `docker compose up -d` |
| `database "xxx" does not exist` | `DATABASE_URL` 中的库名与 `docker-compose.yml` 的 `POSTGRES_DB` 不一致 |
| `password authentication failed` | 用户名或密码错误 |

注意：`POSTGRES_DB` 只在数据卷首次初始化时生效。修改后需要 `docker compose down -v` 删除数据卷再重新启动（会清空数据）。

**启动时报 `jwt_secret_key Field required` 或 `at least 32 items`**

`.env` 中没有设置 `JWT_SECRET_KEY` 或长度不足 32 位，按 [快速开始](#3-准备配置文件) 生成一个。

**端口被占用（`address already in use`）**

8888 端口被其他进程占用，可以临时改用 `uv run chine-agent dev --port 8889`，或用 `lsof -i :8888` 找到并结束占用的进程。

**刷新令牌后马上又要求重新登录**

通常是前端用同一个 refresh token 并发发起了多次刷新，触发了复用检测。参见 [前端接入要点](#前端接入要点) 第 3 条。

**`alembic check` 提示有未生成的迁移**

模型和数据库结构不一致。确认新模型已在 `models/__init__.py` 中导入，然后生成并执行迁移。

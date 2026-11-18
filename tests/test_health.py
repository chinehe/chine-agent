"""健康检查与通用 HTTP 行为（错误格式、request_id）。"""

from fastapi import FastAPI
from httpx import AsyncClient


async def test_healthz(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz_checks_database(client: AsyncClient) -> None:
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_response_has_request_id(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert len(resp.headers["x-request-id"]) == 32


async def test_upstream_request_id_is_kept(client: AsyncClient) -> None:
    resp = await client.get("/healthz", headers={"X-Request-ID": "from-gateway-1"})
    assert resp.headers["x-request-id"] == "from-gateway-1"


async def test_unknown_route_uses_unified_error_format(client: AsyncClient) -> None:
    resp = await client.get("/not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "not_found"
    assert body["request_id"] == resp.headers["x-request-id"]


async def test_unhandled_exception_returns_500_without_details(
    app: FastAPI, client: AsyncClient
) -> None:
    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    resp = await client.get("/boom")
    assert resp.status_code == 500
    assert resp.json()["code"] == "internal_error"
    assert "secret internal detail" not in resp.text

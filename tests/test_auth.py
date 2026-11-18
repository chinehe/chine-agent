"""认证接口：登录、刷新、注销、当前用户。"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chine_agent.models import User
from tests.conftest import TEST_PASSWORD, TEST_USERNAME

AUTH = "/api/v1/auth"


async def _login(client: AsyncClient, username: str = TEST_USERNAME) -> dict[str, str]:
    resp = await client.post(
        f"{AUTH}/login", json={"username": username, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    tokens: dict[str, str] = resp.json()
    return tokens


def _bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


# ---------- 登录 ----------
async def test_login_success(client: AsyncClient, user: User) -> None:
    tokens = await _login(client)
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]


async def test_login_wrong_password(client: AsyncClient, user: User) -> None:
    resp = await client.post(f"{AUTH}/login", json={"username": TEST_USERNAME, "password": "wrong"})
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"
    assert resp.json()["message"] == "用户名或密码错误"


async def test_login_unknown_user_has_same_message(client: AsyncClient) -> None:
    resp = await client.post(
        f"{AUTH}/login", json={"username": "nobody", "password": TEST_PASSWORD}
    )
    assert resp.status_code == 401
    assert resp.json()["message"] == "用户名或密码错误"


async def test_username_is_case_sensitive(client: AsyncClient, user: User) -> None:
    resp = await client.post(
        f"{AUTH}/login", json={"username": TEST_USERNAME.lower(), "password": TEST_PASSWORD}
    )
    assert resp.status_code == 401


async def test_inactive_user_cannot_login(
    client: AsyncClient, user: User, db_session: AsyncSession
) -> None:
    user.is_active = False
    await db_session.commit()

    resp = await client.post(
        f"{AUTH}/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 401


# ---------- 当前用户 ----------
async def test_me_returns_current_user(client: AsyncClient, user: User) -> None:
    tokens = await _login(client)
    resp = await client.get(f"{AUTH}/me", headers=_bearer(tokens["access_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == TEST_USERNAME
    assert "password_hash" not in body


async def test_me_without_token(client: AsyncClient) -> None:
    resp = await client.get(f"{AUTH}/me")
    assert resp.status_code == 401
    assert resp.json()["message"] == "未登录"


async def test_me_with_refresh_token_is_rejected(client: AsyncClient, user: User) -> None:
    tokens = await _login(client)
    resp = await client.get(f"{AUTH}/me", headers=_bearer(tokens["refresh_token"]))
    assert resp.status_code == 401


async def test_deactivated_user_access_token_is_rejected(
    client: AsyncClient, user: User, db_session: AsyncSession
) -> None:
    tokens = await _login(client)
    user.is_active = False
    await db_session.commit()

    resp = await client.get(f"{AUTH}/me", headers=_bearer(tokens["access_token"]))
    assert resp.status_code == 401


# ---------- 刷新 ----------
async def test_refresh_rotates_tokens(client: AsyncClient, user: User) -> None:
    old = await _login(client)
    resp = await client.post(f"{AUTH}/refresh", json={"refresh_token": old["refresh_token"]})
    assert resp.status_code == 200
    new = resp.json()
    assert new["refresh_token"] != old["refresh_token"]

    me = await client.get(f"{AUTH}/me", headers=_bearer(new["access_token"]))
    assert me.status_code == 200


async def test_reused_refresh_token_revokes_whole_family(client: AsyncClient, user: User) -> None:
    first = await _login(client)
    second = (
        await client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})
    ).json()

    # 旧令牌被再次使用（模拟被盗用）
    reuse = await client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401

    # 同一家族里最新的令牌也一并失效
    latest = await client.post(f"{AUTH}/refresh", json={"refresh_token": second["refresh_token"]})
    assert latest.status_code == 401


async def test_refresh_with_invalid_token(client: AsyncClient) -> None:
    resp = await client.post(f"{AUTH}/refresh", json={"refresh_token": "garbage"})
    assert resp.status_code == 401


# ---------- 注销 ----------
async def test_logout_revokes_refresh_token(client: AsyncClient, user: User) -> None:
    tokens = await _login(client)
    resp = await client.post(f"{AUTH}/logout", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 204

    after = await client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert after.status_code == 401


async def test_logout_only_affects_current_session(client: AsyncClient, user: User) -> None:
    session_a = await _login(client)
    session_b = await _login(client)
    await client.post(f"{AUTH}/logout", json={"refresh_token": session_a["refresh_token"]})

    resp = await client.post(f"{AUTH}/refresh", json={"refresh_token": session_b["refresh_token"]})
    assert resp.status_code == 200


async def test_logout_is_idempotent(client: AsyncClient) -> None:
    resp = await client.post(f"{AUTH}/logout", json={"refresh_token": "garbage"})
    assert resp.status_code == 204

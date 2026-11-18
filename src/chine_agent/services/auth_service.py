"""认证相关的业务逻辑：登录、刷新、注销、校验 access token。"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from chine_agent.core.config import Settings
from chine_agent.core.exceptions import UnauthorizedError
from chine_agent.core.logging import get_logger
from chine_agent.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from chine_agent.models import RefreshToken, User
from chine_agent.repositories.refresh_token_repository import RefreshTokenRepository
from chine_agent.repositories.user_repository import UserRepository
from chine_agent.schemas.auth import TokenResponse

log = get_logger(__name__)

# 用户不存在时也做一次密码校验，让"用户不存在"和"密码错误"耗时相同，
# 防止攻击者通过响应时间判断某个用户名是否存在
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing")


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)

    async def login(self, username: str, password: str) -> TokenResponse:
        user = await self.users.get_by_username(username)
        if user is None:
            verify_password(_DUMMY_PASSWORD_HASH, password)
            raise UnauthorizedError("用户名或密码错误")
        # 账号停用也返回同样的提示，不向外透露账号状态
        if not verify_password(user.password_hash, password) or not user.is_active:
            raise UnauthorizedError("用户名或密码错误")

        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        # 每次登录开启一个新的令牌家族（一个登录会话）
        return await self._issue_tokens(user.id, family_id=uuid.uuid4())

    async def refresh(self, refresh_token: str) -> TokenResponse:
        now = datetime.now(UTC)
        stored = await self.refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
        if stored is None or stored.expires_at <= now:
            raise UnauthorizedError("登录已失效，请重新登录")

        if stored.revoked_at is not None:
            # 已作废的令牌又被拿来用：说明令牌可能已被盗用（正常客户端只会用最新的那个）。
            # 作废整个家族，攻击者和真实用户都要重新登录
            await self.refresh_tokens.revoke_family(stored.family_id, now)
            await self.session.commit()
            log.warning(
                "refresh_token_reuse_detected",
                user_id=str(stored.user_id),
                family_id=str(stored.family_id),
            )
            raise UnauthorizedError("登录已失效，请重新登录")

        user = await self.users.get_by_id(stored.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("登录已失效，请重新登录")

        # 轮换：作废旧令牌，在同一家族内签发新令牌
        stored.revoked_at = now
        return await self._issue_tokens(user.id, family_id=stored.family_id)

    async def logout(self, refresh_token: str) -> None:
        """作废这次登录的所有 refresh token。令牌无效也视为成功（幂等）。

        已签发的 access token 无法撤回，会在有效期（默认 15 分钟）结束后自然失效。
        """
        stored = await self.refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
        if stored is not None:
            await self.refresh_tokens.revoke_family(stored.family_id, datetime.now(UTC))
            await self.session.commit()

    async def authenticate(self, access_token: str) -> User:
        user_id = decode_access_token(access_token, self.settings.jwt_secret_key.get_secret_value())
        if user_id is None:
            raise UnauthorizedError("登录已失效，请重新登录")
        # 查一次用户：账号被停用或删除后，即使 access token 未过期也立即拒绝
        user = await self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("登录已失效，请重新登录")
        return user

    async def _issue_tokens(self, user_id: uuid.UUID, family_id: uuid.UUID) -> TokenResponse:
        access_token, access_expires_at = create_access_token(
            user_id,
            self.settings.jwt_secret_key.get_secret_value(),
            timedelta(minutes=self.settings.access_token_expire_minutes),
        )
        refresh_token = generate_refresh_token()
        refresh_expires_at = datetime.now(UTC) + timedelta(
            days=self.settings.refresh_token_expire_days
        )
        await self.refresh_tokens.add(
            RefreshToken(
                user_id=user_id,
                family_id=family_id,
                token_hash=hash_refresh_token(refresh_token),
                expires_at=refresh_expires_at,
            )
        )
        await self.session.commit()
        return TokenResponse(
            access_token=access_token,
            access_token_expires_at=access_expires_at,
            refresh_token=refresh_token,
            refresh_token_expires_at=refresh_expires_at,
        )

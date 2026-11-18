"""密码哈希与令牌工具。"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# ---------- 密码 ----------
# Argon2id 是目前推荐的密码哈希算法；参数使用库的默认推荐值
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """哈希参数升级后，旧密码在用户下次登录时用新参数重新哈希。"""
    return _password_hasher.check_needs_rehash(password_hash)


# ---------- Access Token（JWT） ----------
JWT_ALGORITHM = "HS256"
_ACCESS_TOKEN_TYPE = "access"  # noqa: S105  误报：这是令牌类型，不是密码


def create_access_token(
    user_id: uuid.UUID, secret_key: str, expires_in: timedelta
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + expires_in
    payload = {
        "sub": str(user_id),  # 令牌主体：用户 ID
        "type": _ACCESS_TOKEN_TYPE,  # 防止别的用途的 JWT 被当成 access token 使用
        "iat": now,  # 签发时间
        "exp": expires_at,  # 过期时间，过期后 jwt.decode 会直接拒绝
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM), expires_at


def decode_access_token(token: str, secret_key: str) -> uuid.UUID | None:
    """校验签名、过期时间和类型，成功时返回用户 ID，任何一项不通过都返回 None。"""
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[JWT_ALGORITHM],  # 必须显式指定，防止"alg=none"等算法替换攻击
            options={"require": ["sub", "type", "iat", "exp"]},
        )
        if payload["type"] != _ACCESS_TOKEN_TYPE:
            return None
        return uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        return None


# ---------- Refresh Token（随机串，存库） ----------
def generate_refresh_token() -> str:
    """32 字节密码学安全随机数，无法猜测。"""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """数据库只存哈希。即使数据库泄露，也拿不到可用的 refresh token。

    令牌本身是高强度随机数，用 SHA-256 即可，不需要密码那样的慢哈希。
    """
    return hashlib.sha256(token.encode()).hexdigest()

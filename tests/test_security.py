"""密码哈希与 JWT 工具的单元测试（不需要数据库）。"""

import uuid
from datetime import timedelta

import jwt

from chine_agent.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SECRET = "x" * 40


def test_password_hash_and_verify() -> None:
    hashed = hash_password("Passw0rd!")
    assert hashed.startswith("$argon2id$")
    assert hashed != "Passw0rd!"
    assert verify_password(hashed, "Passw0rd!")
    assert not verify_password(hashed, "wrong")


def test_verify_password_with_invalid_hash_returns_false() -> None:
    assert not verify_password("not-a-hash", "Passw0rd!")


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token, _ = create_access_token(user_id, SECRET, timedelta(minutes=5))
    assert decode_access_token(token, SECRET) == user_id


def test_expired_access_token_is_rejected() -> None:
    token, _ = create_access_token(uuid.uuid4(), SECRET, timedelta(seconds=-1))
    assert decode_access_token(token, SECRET) is None


def test_access_token_signed_with_other_key_is_rejected() -> None:
    token, _ = create_access_token(uuid.uuid4(), "y" * 40, timedelta(minutes=5))
    assert decode_access_token(token, SECRET) is None


def test_unsigned_token_is_rejected() -> None:
    # alg=none 攻击：不带签名的令牌必须被拒绝
    token = jwt.encode({"sub": str(uuid.uuid4()), "type": "access"}, None, algorithm="none")
    assert decode_access_token(token, SECRET) is None


def test_token_with_wrong_type_is_rejected() -> None:
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "refresh", "iat": 0, "exp": 2**31},
        SECRET,
        algorithm="HS256",
    )
    assert decode_access_token(token, SECRET) is None

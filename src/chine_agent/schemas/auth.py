from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # 登录时不校验用户名格式：格式不对的用户名本来就不存在，统一返回"用户名或密码错误"
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  误报：这是令牌类型，不是密码
    access_token_expires_at: datetime
    refresh_token: str
    refresh_token_expires_at: datetime

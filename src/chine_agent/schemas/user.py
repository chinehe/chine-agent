import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    # 只允许字母、数字和 _ . -，避免奇怪字符带来的显示和安全问题
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    # 允许直接从 ORM 对象构造：UserResponse.model_validate(user)
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    is_active: bool
    created_at: datetime

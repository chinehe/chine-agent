"""应用配置：从环境变量和 .env文件加载，启动时统一校验"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # 应用
    app_name: str = "chine-agent"
    app_env: Literal["dev","test","prod"] = "dev"
    app_debug: bool = False

    # 日志
    log_level: Literal["DEBUG","INFO","WARNING","ERROR"] = "INFO"

    # 数据库
    # 用 SecretStr 包装：打印配置或写日志时密码会显示为 **********
    database_url: SecretStr
    database_pool_size: int = Field(default=10,ge=1)
    database_max_overflow: int = Field(default=20,ge=0)

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls,v:SecretStr) -> SecretStr:
        PostgresDsn(v.get_secret_value())
        return v

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

@lru_cache
def get_settings() -> Settings:
    return Settings()

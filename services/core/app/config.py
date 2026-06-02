"""Core service settings (pydantic-settings).

Real values come from the environment (.env / Vault later, AI-1.3). The defaults
here are format placeholders only — no real secret is embedded.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,  # allow Settings(database_url=...) in tests/app factory
    )

    app_name: str = Field(default="posnet-core", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    environment: str = Field(default="local", alias="ENVIRONMENT")

    # NOTE: password-less default; real DATABASE_URL is supplied via env.
    database_url: str = Field(
        default="postgresql+psycopg://posnet@localhost:5432/posnet_core",
        alias="DATABASE_URL",
    )
    db_pool_size: int = Field(default=20, alias="DATABASE_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")
    db_pool_recycle: int = Field(default=3600, alias="DATABASE_POOL_RECYCLE")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()

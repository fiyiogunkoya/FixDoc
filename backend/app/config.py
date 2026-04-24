"""Pydantic Settings — loads env vars prefixed with FIXDOC_."""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FIXDOC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    debug: bool = False

    database_url: str = "postgresql+psycopg2://fixdoc:fixdoc@localhost:5432/fixdoc"

    clerk_secret_key: str = ""
    clerk_publishable_key: str = ""
    clerk_jwks_url: str = ""
    clerk_webhook_secret: str = ""

    github_app_id: str = ""
    github_app_private_key: str = ""
    github_app_slug: str = ""  # public slug, used in install URL
    github_webhook_secret: str = ""

    cors_origins: List[str] = ["http://localhost:3000"]

    api_key_prefix: str = "fd_live_"


@lru_cache
def get_settings() -> Settings:
    return Settings()

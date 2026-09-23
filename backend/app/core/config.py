from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "personalos-dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "PersonalOS API"
    app_version: str = "1.2.0"
    debug: bool = True

    secret_key: str = _DEV_SECRET
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    database_url: str = "sqlite+aiosqlite:///./personalos.db"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "personalos"
    s3_secret_key: str = "personalos123"
    s3_bucket: str = "personalos"

    llm_provider: str = "mock"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None

    embedding_provider: str = "mock"
    embedding_model: str = "text-embedding-3-small"

    frontend_origin: str = "http://localhost:3000"

    seed_demo_user: bool = True

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Settings:
        """Fail-safe defaults: outside debug mode the dev conveniences
        (default JWT secret, auto-seeded demo login) must be explicitly
        disabled or replaced, otherwise startup aborts."""
        if not self.debug:
            if self.secret_key == _DEV_SECRET:
                raise ValueError(
                    "SECRET_KEY must be set in non-debug environments "
                    "(the built-in development secret is not allowed)."
                )
            if self.seed_demo_user:
                raise ValueError(
                    "SEED_DEMO_USER must be false in non-debug environments "
                    "(it exposes an unauthenticated token endpoint)."
                )
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

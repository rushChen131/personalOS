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
    # Point the OpenAI-protocol gateway at any compatible endpoint — a company
    # LiteLLM proxy, vLLM, Azure, ... Left unset the SDK uses its own default.
    # The value is a *base*: the SDK appends `/chat/completions` itself, so an
    # endpoint published as `.../v1/chat/completions` is configured as `.../v1`.
    openai_base_url: str | None = None
    # The gateway speaks the OpenAI *protocol*, but the endpoint may only serve
    # model ids that are not OpenAI's. Keeping the ids in settings is what lets
    # a company deployment swap in e.g. DeepSeek without touching code.
    openai_chat_model: str = "gpt-4o-mini"
    openai_heavy_model: str = "gpt-4o"
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None

    embedding_provider: str = "mock"
    # Embeddings are configured separately from chat: the endpoint that serves
    # them is often a different service with its own credentials (the company
    # LiteLLM gateway exposes no embedding model at all).
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str | None = None
    # Same "base" convention as `openai_base_url` above.
    embedding_base_url: str | None = None
    # NIM-served models (e.g. nvidia/nemotron-3-embed-1b) require `input_type`
    # and reject over-long inputs unless `truncate` is set. Opt-in because they
    # are not part of the OpenAI embeddings schema.
    embedding_input_type: str | None = None
    embedding_truncate: str | None = None

    frontend_origin: str = "http://localhost:3000"

    seed_demo_user: bool = True

    # Mirror log lines to a rotating file in addition to stdout. Unset (or
    # empty) disables it — the test bootstrap sets LOG_FILE="" so the suite
    # never litters the working tree with log files.
    log_file: str | None = None
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5

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

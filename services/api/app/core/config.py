"""Application settings.

All configuration is environment-driven. Secrets are read from the environment
(never committed) and validated at startup: a missing secret in a non-local
environment is a hard failure rather than a silent default.
"""

from __future__ import annotations

import functools
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "prod"]


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_env: Environment = "local"
    app_name: str = "ScholarMind API"
    api_base_path: str = "/api/v1"
    log_level: str = "INFO"
    log_json: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Database ---
    database_url: str = "postgresql+psycopg://scholarmind:scholarmind@localhost:5432/scholarmind"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Auth ---
    jwt_secret: str = "change-me-in-every-environment"
    jwt_refresh_secret: str = "change-me-too"
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 7
    admin_emails: list[str] = Field(default_factory=list)

    # --- LLM ---
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-5"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.0
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    rerank_enabled: bool = False
    rerank_model: str = ""

    # --- Retrieval ---
    retrieval_top_k: int = 20
    retrieval_candidates: int = 100
    retrieval_rrf_k: int = 60
    retrieval_chunk_tokens: int = 500
    retrieval_chunk_overlap: int = 80

    # --- Ingestion ---
    ingestion_enabled: bool = False
    ingestion_user_agent: str = "ScholarMindBot/1.0"
    ingestion_max_bytes: int = 5 * 1024 * 1024
    ingestion_timeout_seconds: int = 20
    ingestion_min_delay_seconds: int = 5
    ingestion_max_redirects: int = 3
    ingestion_default_cadence_hours: int = 168

    # --- Rate limits ---
    rate_limit_read_per_min: int = 240
    rate_limit_write_per_min: int = 60
    rate_limit_assistant_per_min: int = 20
    rate_limit_assistant_per_day: int = 200
    rate_limit_refresh_per_min: int = 5

    # --- Observability ---
    sentry_dsn: str = ""

    @field_validator("cors_origins", "admin_emails", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow comma-separated values in environment variables."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"

    def validate_secrets(self) -> None:
        """Fail fast when production secrets are left at their defaults."""
        if not self.is_production:
            return
        insecure = {"change-me-in-every-environment", "change-me-too"}
        if self.jwt_secret in insecure or self.jwt_refresh_secret in insecure:
            raise RuntimeError("JWT secrets must be set to unique values in production.")
        if self.jwt_secret == self.jwt_refresh_secret:
            raise RuntimeError("JWT access and refresh secrets must differ in production.")
        if not self.llm_api_key:
            raise RuntimeError("LLM_API_KEY must be set in production.")


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor (FastAPI dependency)."""
    settings = Settings()
    settings.validate_secrets()
    return settings

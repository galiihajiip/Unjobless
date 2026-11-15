"""Environment configuration, validated at startup.

All settings come from environment variables prefixed ``UNJOBLESS_`` (plus
``DATABASE_URL``). Secrets are typed as ``SecretStr`` so they never appear in
reprs or logs.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UNJOBLESS_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = Field(
        default="postgresql+psycopg://unjobless:unjobless@127.0.0.1:5433/unjobless",
        validation_alias="DATABASE_URL",
    )

    # 32+ byte urlsafe-base64 secret. Encrypts stored AI keys. Must be backed up separately.
    master_key: SecretStr | None = None
    # Secret used to sign session/CSRF tokens.
    session_secret: SecretStr | None = None

    public_base_url: str = "http://localhost:5173"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    session_ttl_hours: int = 24 * 7
    session_idle_hours: int = 24 * 2

    files_dir: str = "./var/files"

    # Fetching / collection limits
    user_agent: str = "UnjoblessBot/0.1 (+personal self-hosted career research; respects robots.txt)"
    fetch_max_bytes: int = 5 * 1024 * 1024
    fetch_max_redirects: int = 5
    fetch_connect_timeout: float = 5.0
    fetch_read_timeout: float = 15.0
    fetch_total_timeout: float = 30.0
    fetch_allowed_ports: list[int] = Field(default_factory=lambda: [80, 443])
    max_urls_per_batch: int = 50
    max_upload_bytes: int = 10 * 1024 * 1024
    max_paste_chars: int = 200_000
    global_worker_concurrency: int = 4

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _production_requirements(self) -> Settings:
        if self.env == "production":
            missing = [
                name
                for name, val in (
                    ("UNJOBLESS_MASTER_KEY", self.master_key),
                    ("UNJOBLESS_SESSION_SECRET", self.session_secret),
                )
                if val is None or len(val.get_secret_value()) < 32
            ]
            if missing:
                raise ValueError(f"Missing or too-short secrets in production: {', '.join(missing)}")
        if self.master_key is not None:
            try:
                raw = base64.urlsafe_b64decode(self.master_key.get_secret_value() + "==")
            except Exception as exc:  # pragma: no cover - defensive
                raise ValueError("UNJOBLESS_MASTER_KEY must be urlsafe base64") from exc
            if len(raw) < 32:
                raise ValueError("UNJOBLESS_MASTER_KEY must decode to at least 32 bytes")
        return self

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

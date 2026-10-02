"""Runtime configuration, read once from the environment (and an optional .env)."""

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    school_timezone: str = "UTC"

    @field_validator("school_timezone")
    @classmethod
    def valid_school_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("SCHOOL_TIMEZONE must be a valid IANA timezone") from exc
        return value

    database_url: str = "sqlite:///./data/superteacher.db"
    anthropic_api_key: str | None = None
    # Chat + insights run on the same model by default; override per deployment.
    anthropic_model: str = "claude-sonnet-5-5"
    # Cheap, fast model for per-student insight cards.
    anthropic_insight_model: str = "claude-haiku-4-5-20251001"
    # Shared per-worker AI admission and total operation deadlines.
    ai_max_concurrent_requests: int = Field(default=8, ge=1, le=128)
    ai_chat_timeout_seconds: float = Field(default=90.0, gt=0, le=600)
    ai_insight_timeout_seconds: float = Field(default=45.0, gt=0, le=600)
    ai_parent_timeout_seconds: float = Field(default=45.0, gt=0, le=600)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:4000"])
    seed_demo_data: bool = True
    version: str = "dev"
    static_dir: str = "web/dist"

    # --- auth (see docs/DEPLOYMENT.md) ---
    # Single shared passcode. Required unless auth_disabled is explicitly true.
    auth_password: str | None = None
    # Explicit opt-out for local development / tests. Never the implicit default.
    auth_disabled: bool = False
    # HMAC key for session cookies. If unset, one is generated and persisted next to the SQLite file
    # (or kept in memory with a warning when the DB is not file based).
    session_secret: str | None = None
    session_ttl_hours: int = 12
    # None = auto (Secure when the request is https, incl. X-Forwarded-Proto). Set true/false to force.
    cookie_secure: bool | None = None
    # Interactive API docs are off by default (they would expose the schema without a login).
    enable_docs: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()

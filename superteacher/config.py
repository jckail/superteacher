"""Runtime configuration, read once from the environment (and an optional .env)."""

from functools import lru_cache
from typing import Literal
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
    # None = auto (Secure when the request is https, including trusted proxy headers). Set true/false to force.
    cookie_secure: bool | None = None

    # --- accounts (passwordless email sign-in; see docs/DEPLOYMENT.md and ADR 0002) ---
    # "passcode" (default): the shared passcode above, mapped to one implicit owner user. "accounts": email links.
    auth_mode: Literal["passcode", "accounts"] = "passcode"
    # Origin used to build the emailed link. NEVER derived from the Host header (host-header poisoning).
    # Falls back to the first CORS origin.
    public_base_url: str | None = None
    accounts_max_users: int = 500
    # Comma-separated domains allowed to sign up ("school.org,example.edu"); empty = anyone.
    accounts_email_allowlist_domains: str = ""
    # If set, the first sign-in with this email adopts the data of the pre-accounts "owner" user.
    accounts_owner_email: str | None = None
    login_token_ttl_minutes: int = 15
    accounts_session_idle_hours: int = 72
    accounts_session_absolute_hours: int = 720
    accounts_link_per_email_hour: int = 3
    accounts_link_per_ip_hour: int = 10
    accounts_link_global_hour: int = 300
    # Mail: sendgrid | console (logs a redacted notice) | file (full message into auth_email_outbox_dir; tests/e2e).
    auth_email_backend: Literal["sendgrid", "console", "file"] = "sendgrid"
    auth_email_from: str | None = None
    sendgrid_api_key: str | None = None
    auth_email_outbox_dir: str | None = None
    # console/file leak sign-in links, so they are refused when K_SERVICE is set (Cloud Run) unless forced.
    auth_email_allow_insecure_backend: bool = False
    # Per-user, per-UTC-day quotas for metered AI actions; global_daily_budget caps all users together (None = off).
    quota_chat_per_day: int = 100
    quota_insight_per_day: int = 60
    quota_parent_update_per_day: int = 20
    ai_global_daily_budget: int | None = None

    # Interactive API docs are off by default (they would expose the schema without a login).
    enable_docs: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()

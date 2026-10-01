"""Runtime configuration, read once from the environment (and an optional .env)."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/superteacher.db"
    anthropic_api_key: str | None = None
    # Chat + insights run on the same model by default; override per deployment.
    anthropic_model: str = "claude-sonnet-5-5"
    # Cheap, fast model for per-student insight cards.
    anthropic_insight_model: str = "claude-haiku-4-5-20251001"
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

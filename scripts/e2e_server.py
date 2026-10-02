"""Serve built UI against disposable storage; never use deployment configuration."""

from __future__ import annotations

import os
import secrets
import signal
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    # Uvicorn replays termination signals after draining. Convert SIGTERM to
    # SystemExit so Python finally blocks remove our database and directory.
    def terminate(_signal: int, _frame: object) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    root = Path(__file__).resolve().parents[1]
    static = root / "web" / "dist"
    if not (static / "index.html").is_file():
        raise SystemExit("Build the UI first: cd web && npm run build")
    port = int(os.environ.get("E2E_PORT", "8765"))
    if not 1024 <= port <= 65535:
        raise SystemExit("E2E_PORT must be between 1024 and 65535")
    sys.path.insert(0, str(root))
    from superteacher.config import Settings, get_settings

    # Ignore all inherited application settings, including future Settings fields.
    setting_names = {field.casefold() for field in Settings.model_fields}
    for env_name in tuple(os.environ):
        if env_name.casefold() in setting_names:
            os.environ.pop(env_name, None)
    with TemporaryDirectory(prefix="superteacher-e2e-") as temporary:
        # Import-time engine/config creation must also use our temporary database.
        os.environ.update(
            {
                "DATABASE_URL": f"sqlite:///{Path(temporary) / 'test.db'}",
                "AUTH_PASSWORD": "superteacher-browser-tests",
                "AUTH_DISABLED": "false",
                "SESSION_SECRET": secrets.token_urlsafe(48),
                "COOKIE_SECURE": "false",
                "SEED_DEMO_DATA": "false",
                "ANTHROPIC_API_KEY": "",
                "STATIC_DIR": str(static),
                "ENABLE_DOCS": "false",
                "CORS_ORIGINS": f'["http://127.0.0.1:{port}"]',
            }
        )
        os.environ.pop("K_SERVICE", None)
        # Avoid .env entirely, including keys/config added there in future.
        settings = Settings(_env_file=None)
        get_settings.cache_clear()
        # Settings' default .env lookup occurs in imported modules; changing cwd
        # to the empty temporary directory prevents any deployment .env loading.
        previous_cwd = Path.cwd()
        os.chdir(temporary)
        try:
            import uvicorn

            from superteacher.db import engine
            from superteacher.main import create_app

            try:
                uvicorn.run(create_app(settings=settings, seed=False), host="127.0.0.1", port=port)
            finally:
                engine.dispose()
        finally:
            os.chdir(previous_cwd)


if __name__ == "__main__":
    main()

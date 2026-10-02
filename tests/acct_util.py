"""Builders for the accounts-mode suites: an app using the ``file`` mailer, plus sign-in helpers (no real email ever)."""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from superteacher import db as database
from superteacher.config import Settings
from superteacher.main import create_app

H = {"X-Requested-With": "test"}


def build(tmp_path: Path, **kw) -> TestClient:
    """Accounts-mode app on in-memory SQLite. Use as a context manager (it runs the lifespan)."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sf = sessionmaker(bind=eng, expire_on_commit=False)
    opts = {
        "auth_mode": "accounts",
        "auth_disabled": False,
        "session_secret": "s" * 32,
        "cors_origins": ["http://localhost:4000"],
        "public_base_url": "http://testserver",
        "auth_email_backend": "file",
        "auth_email_outbox_dir": str(tmp_path / "outbox"),
        "static_dir": "/nonexistent-static-dir",
        "anthropic_api_key": None,
        "accounts_link_per_ip_hour": 10_000,  # tests sign many users in from one address; limit tests override
        "accounts_link_global_hour": 10_000,
        **kw,
    }
    app = create_app(session_factory=sf, engine=eng, seed=False, settings=Settings(**opts))

    def override():
        with sf() as db:
            yield db

    app.dependency_overrides[database.get_db] = override
    return TestClient(app, base_url="http://testserver")


def outbox(tmp_path: Path) -> list[dict]:
    d = tmp_path / "outbox"
    return (
        [json.loads(f.read_text()) for f in sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime_ns)]
        if d.exists()
        else []
    )


def token_from(msg: dict) -> str:
    m = re.search(r"/auth/verify#token=([A-Za-z0-9_-]+)", msg["text"])
    assert m, msg["text"]
    return m.group(1)


def request_link(c: TestClient, email: str, **headers):
    return c.post("/api/auth/request-link", json={"email": email}, headers={**H, **headers})


def verify(c: TestClient, token: str, **headers):
    return c.post("/api/auth/verify", json={"token": token}, headers={**H, **headers})


def sign_in(c: TestClient, tmp_path: Path, email: str) -> dict:
    """Full flow with this client's cookie jar. Returns the verify response body."""
    before = len(outbox(tmp_path))
    assert request_link(c, email).status_code == 202
    sent = outbox(tmp_path)
    assert len(sent) == before + 1, "expected exactly one new email"
    r = verify(c, token_from(sent[-1]))
    assert r.status_code == 200, r.text
    return r.json()


def second_client(c: TestClient) -> TestClient:
    """Another browser (own cookie jar) against the same app instance."""
    return TestClient(c.app, base_url="http://testserver")

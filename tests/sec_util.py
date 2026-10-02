"""Shared builders for the tests/test_security_*.py suites (an authenticated-by-passcode app, like production)."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from superteacher import db as database
from superteacher.config import Settings
from superteacher.main import create_app

PW = "correct horse"
H = {"X-Requested-With": "test"}


def build(static_dir: Path | None = None, raise_server_exceptions: bool = True, **kw) -> TestClient:
    """A passcode-protected app on in-memory SQLite. Use as a context manager (it runs the lifespan)."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sf = sessionmaker(bind=eng, expire_on_commit=False)
    opts = {
        "auth_password": PW,
        "auth_disabled": False,
        "session_secret": "s" * 32,
        "cors_origins": ["http://localhost:4000"],
        "static_dir": str(static_dir) if static_dir else "/nonexistent-static-dir",
        **kw,
    }
    app = create_app(session_factory=sf, engine=eng, seed=False, settings=Settings(**opts))

    def override():
        with sf() as db:
            yield db

    app.dependency_overrides[database.get_db] = override
    return TestClient(app, base_url="http://testserver", raise_server_exceptions=raise_server_exceptions)


def login(c: TestClient, pw: str = PW, **headers):
    return c.post("/api/auth/login", json={"password": pw}, headers={**H, **headers})


def behind_proxy(c: TestClient, trusted: bool) -> TestClient:
    """The app as Cloud Run presents it. trusted=True mirrors the image's FORWARDED_ALLOW_IPS=*."""
    app = ProxyHeadersMiddleware(c.app, trusted_hosts="*") if trusted else c.app
    return TestClient(app, base_url="http://testserver")


def seed_class(c: TestClient, course="Algebra", section="P1", students=("Ada Lovelace",)) -> dict:
    """Create course/section/students through the API (client must be logged in). Returns ids."""
    cid = c.post("/api/courses", json={"name": course}, headers=H).json()["id"]
    sid = c.post("/api/sections", json={"course_id": cid, "name": section}, headers=H).json()["id"]
    studs = [
        c.post("/api/students", json={"name": n, "grade_level": 9, "section_id": sid}, headers=H).json()["id"]
        for n in students
    ]
    return {"course": cid, "section": sid, "students": studs}


def flatten_routes(routes) -> list[tuple[str, str]]:
    """(METHOD | "WS" | "MOUNT", full path) for every route, whether FastAPI keeps included routers lazily
    (``_IncludedRouter``, newer releases) or flattened into ``app.routes`` (older ones)."""
    out: list[tuple[str, str]] = []
    for r in routes:
        if hasattr(r, "effective_candidates"):  # lazily included router: recurse
            out += flatten_routes(r.effective_candidates())
            continue
        sr = getattr(r, "starlette_route", None)
        if sr is not None:  # effective context wrapping a websocket / mount / plain route
            out += flatten_routes([sr])
            continue
        kind = type(r).__name__
        path = getattr(r, "path", "")
        if getattr(r, "methods", None) and path:
            out += [(m, path) for m in sorted(r.methods - {"HEAD", "OPTIONS"})]
        elif "WebSocket" in kind:
            out.append(("WS", path))
        elif kind == "Mount":
            out.append(("MOUNT", path))
        else:
            out.append((kind, path))
    return out

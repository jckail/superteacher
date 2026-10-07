"""Public demo gate and durable anonymous cost limits."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from starlette.requests import HTTPConnection

from superteacher import accounts, demo
from superteacher.auth import AuthState, current_user
from superteacher.auth import router as auth_router
from superteacher.config import Settings
from superteacher.db import Base, get_db, make_engine, run_migrations
from superteacher.models import OWNER_ID, AiBudget, DemoUsageCounter

SECRET = "public-demo-tests-stable-secret"


def settings(**kwargs):
    return Settings(_env_file=None, public_demo=True, auth_disabled=False, session_secret=SECRET, **kwargs)


@pytest.fixture
def factory(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def make_client(factory, config=None):
    app = FastAPI()
    app.state.auth = AuthState(config or settings())
    app.state.session_factory = factory
    app.include_router(auth_router, prefix="/api")
    app.include_router(demo.router, prefix="/api")

    def database():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database

    @app.post("/write")
    async def write(user=Depends(current_user)):
        return {"owner": user.id}

    return TestClient(app)


def cookie(st):
    return st.demo_serializer.dumps({"v": 1, "nonce": accounts.new_secret()})


def test_public_owner_requires_no_passcode_but_preserves_csrf_and_origin(factory):
    with make_client(factory) as c:
        assert c.get("/api/auth/me").json()["auth_required"] is False
        assert c.get("/api/auth/config").json()["auth_mode"] == "public_demo"
        assert c.post("/write").status_code == 403
        assert c.post("/write", headers={"X-Requested-With": "fetch"}).json() == {"owner": OWNER_ID}
        assert c.post("/write", headers={"X-Requested-With": "fetch", "Origin": "https://evil.test"}).status_code == 403
        assert c.get("/api/demo/status").status_code == 401
        assert c.post("/api/demo/session").status_code == 403
        r = c.post("/api/demo/session", headers={"X-Requested-With": "fetch"})
        assert r.json()["remaining"] == 5
        assert "httponly" in r.headers["set-cookie"].lower()
        assert "samesite=lax" in r.headers["set-cookie"].lower()
        assert c.get("/api/demo/status").json()["remaining"] == 5
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DemoUsageCounter)) == 0


def test_cookie_signed_independent_of_password_and_invalid_cookie_rejected():
    a = AuthState(settings(auth_password="old"))
    b = AuthState(settings(auth_password="new"))
    token = cookie(a)
    assert demo.visitor_subject(a, token) == demo.visitor_subject(b, token)
    assert demo.visitor_subject(a, token + "tampered") is None
    assert demo.visitor_subject(a, "browser-supplied-id") is None
    assert demo.visitor_subject(a, None) is None


def test_public_mode_explicit_and_conflicting_auth_modes_rejected():
    with pytest.raises(RuntimeError, match="AUTH_PASSWORD"):
        AuthState(Settings(_env_file=None, auth_disabled=False))
    with pytest.raises(RuntimeError, match="PUBLIC_DEMO"):
        AuthState(settings(auth_mode="accounts"))
    with pytest.raises(RuntimeError, match="PUBLIC_DEMO"):
        AuthState(Settings(_env_file=None, public_demo=True, auth_disabled=True))


def test_five_turns_persist_and_new_cookie_does_not_reset_network(factory):
    st = AuthState(settings())
    visitor = demo.visitor_subject(st, cookie(st))
    network = "a" * 64
    for i in range(5):
        with factory() as db:
            assert demo.consume_chat(db, st.settings, visitor, network)["remaining"] == 4 - i
    with factory() as db, pytest.raises(accounts.QuotaExceeded):
        demo.consume_chat(db, st.settings, visitor, network)
    new_visitor = demo.visitor_subject(st, cookie(st))
    with factory() as db:
        assert demo.quota_status(db, st.settings, new_visitor, network)["remaining"] == 0
        with pytest.raises(accounts.QuotaExceeded):
            demo.consume_chat(db, st.settings, new_visitor, network)
        assert db.scalar(select(AiBudget.count)) == 5
        assert db.scalar(select(func.count()).select_from(DemoUsageCounter)) == 2


def test_budget_rejection_rolls_back_both_counters(factory):
    config = settings(ai_global_daily_budget=1)
    with factory() as db:
        demo.consume_chat(db, config, "a" * 64, "b" * 64)
    with factory() as db:
        with pytest.raises(accounts.QuotaExceeded) as e:
            demo.consume_chat(db, config, "c" * 64, "d" * 64)
        assert e.value.scope == "global"
        assert db.scalar(select(func.count()).select_from(DemoUsageCounter)) == 2
        assert db.scalar(select(AiBudget.count)) == 1


def test_parallel_reservations_cannot_overspend(factory):
    config = settings()

    def submit(_):
        with factory() as db:
            try:
                demo.consume_chat(db, config, "a" * 64, "b" * 64)
                return True
            except accounts.QuotaExceeded:
                return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(submit, range(12))) == 5
    with factory() as db:
        assert db.scalar(select(AiBudget.count)) == 5
        assert list(db.scalars(select(DemoUsageCounter.count))) == [5, 5]


def test_utc_day_rollover(factory, monkeypatch):
    config = settings()
    now = datetime(2026, 10, 7, 23, 59, tzinfo=UTC)
    monkeypatch.setattr(accounts, "now", lambda: now)
    with factory() as db:
        demo.consume_chat(db, config, "a" * 64, "b" * 64)
        assert demo.quota_status(db, config, "a" * 64, "b" * 64)["used"] == 1
    now += timedelta(minutes=2)
    with factory() as db:
        assert demo.quota_status(db, config, "a" * 64, "b" * 64)["remaining"] == 5


def test_network_identity_ignores_untrusted_forwarded_header():
    st = AuthState(settings())

    def conn(value):
        return HTTPConnection(
            {
                "type": "http",
                "client": ("192.0.2.10", 123),
                "headers": [(b"x-forwarded-for", value.encode())],
            }
        )

    assert demo.network_subject(conn("192.0.2.111"), st) == demo.network_subject(conn("198.51.100.1"), st)


def test_demo_migration_preserves_existing_schema(tmp_path):
    from sqlalchemy import inspect

    engine = make_engine(f"sqlite:///{tmp_path / 'migrated.db'}")
    run_migrations(engine, target_revision="0004")
    with engine.begin() as conn:
        conn.execute(AiBudget.__table__.insert().values(day=datetime.now(UTC).date(), count=3))
    run_migrations(engine)
    assert "demo_usage_counters" in inspect(engine).get_table_names()
    with engine.connect() as conn:
        assert conn.scalar(select(AiBudget.count)) == 3
    engine.dispose()


def test_verified_suffix_survives_uvicorn_proxy_headers():
    import asyncio

    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    st = AuthState(settings(auth_forwarded_for_trusted_hops=1))
    identities = []

    async def application(scope, receive, send):
        identities.append(demo.network_subject(HTTPConnection(scope), st))

    middleware = ProxyHeadersMiddleware(application, trusted_hosts="*")

    async def check():
        for prefix in ("", "198.51.100.7, ", "not-an-ip, 203.0.113.7, "):
            await middleware(
                {
                    "type": "http",
                    "client": ("127.0.0.1", 1234),
                    "headers": [(b"x-forwarded-for", (prefix + "192.0.2.25").encode())],
                },
                None,
                None,
            )

    asyncio.run(check())
    assert len(set(identities)) == 1

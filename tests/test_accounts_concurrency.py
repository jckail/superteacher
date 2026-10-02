"""Authentication and quota invariants with independent SQLite connections."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from superteacher import accounts
from superteacher.config import Settings
from superteacher.db import Base
from superteacher.models import OWNER_ID, AiBudget, Course, UsageCounter, User


@pytest.fixture
def store(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'accounts.db'}", connect_args={"timeout": 30})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def parallel(factory, call, attempts=8):
    def work(i):
        with factory() as db:
            return call(db, i)

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(work, range(attempts)))


def test_owner_bootstrap_is_idempotent_across_connections(store):
    assert parallel(store, lambda db, _: accounts.ensure_owner(db)) == [OWNER_ID] * 8
    with store() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_concurrent_signups_cannot_exceed_user_cap(store):
    settings = Settings(accounts_max_users=1)
    results = parallel(store, lambda db, i: accounts.get_or_create_user(db, settings, f"u{i}@example.com"))
    assert sum(result is not None for result in results) == 1
    with store() as db:
        assert accounts.count_users(db) == 1
        assert db.scalar(select(func.count()).select_from(Course)) == 2


def test_same_email_signup_is_seeded_once(store):
    results = parallel(store, lambda db, _: accounts.get_or_create_user(db, Settings(), "same@example.com"))
    assert sum(created for _, created in results) == 1
    assert len({user.id for user, _ in results}) == 1
    with store() as db:
        assert db.scalar(select(func.count()).select_from(Course)) == 2


def test_login_token_has_only_one_concurrent_consumer(store):
    with store() as db:
        raw = accounts.issue_login_token(db, Settings(), "one@example.com", None)
        db.commit()
    results = parallel(store, lambda db, _: accounts.consume_login_token(db, raw))
    assert results.count("one@example.com") == 1
    assert results.count(None) == 7


def test_quota_updates_respect_global_cap_and_rollback_rejected_user_counts(store):
    settings = Settings(quota_chat_per_day=3, ai_global_daily_budget=4)
    with store() as db:
        db.add_all([User(id="a", email="a@example.com"), User(id="b", email="b@example.com")])
        db.commit()

    def spend(db, i):
        try:
            accounts.consume_quota(db, settings, "a" if i % 2 else "b", "chat")
            return True
        except accounts.QuotaExceeded:
            return False

    assert sum(parallel(store, spend, attempts=16)) == 4
    with store() as db:
        counts = db.scalars(select(UsageCounter.count)).all()
        assert sum(counts) == 4 and max(counts) <= 3
        assert db.scalar(select(AiBudget.count)) == 4


def test_limiter_bounds_active_keys_and_reclaims_expired_keys():
    tick = [0.0]
    limiter = accounts.SlidingWindow(2, window=10, max_keys=2, clock=lambda: tick[0])
    assert limiter.allow("a") and limiter.allow("b")
    assert not limiter.allow("c")
    assert limiter.allow("a")
    tick[0] = 10.0
    assert limiter.allow("c")


def test_per_email_link_limit_is_atomic_across_connections(store):
    settings = Settings(accounts_link_per_email_hour=3)

    def request(db, _):
        accounts.reserve_link_request(db)
        allowed = accounts.recent_token_count(db, "limited@example.com") < settings.accounts_link_per_email_hour
        accounts.issue_login_token(db, settings, "limited@example.com", None)
        if allowed:
            db.commit()
        else:
            db.rollback()
        return allowed

    assert sum(parallel(store, request, attempts=12)) == 3
    with store() as db:
        assert accounts.recent_token_count(db, "limited@example.com") == 3

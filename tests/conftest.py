import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from superteacher import db as database
from superteacher.config import get_settings
from superteacher.main import create_app


@pytest.fixture
def engine():
    # StaticPool keeps a single in-memory DB alive across connections/threads.
    return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def _client(engine, session_factory, seed):
    app = create_app(session_factory=session_factory, engine=engine, seed=seed)

    def override():
        with session_factory() as s:
            yield s

    app.dependency_overrides[database.get_db] = override
    return TestClient(app)


@pytest.fixture
def client(engine, session_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    with _client(engine, session_factory, seed=False) as c:
        yield c


@pytest.fixture
def seeded(engine, session_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    with _client(engine, session_factory, seed=True) as c:
        yield c

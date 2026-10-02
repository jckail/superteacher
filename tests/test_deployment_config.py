import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from superteacher.config import Settings
from superteacher.main import create_app


def test_cloud_run_refuses_ephemeral_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("K_SERVICE", "synthetic-review-service")
    path = tmp_path / "ephemeral.db"
    engine = create_engine(f"sqlite:///{path}")
    try:
        with pytest.raises(RuntimeError, match="durable server database"):
            create_app(engine=engine, session_factory=sessionmaker(bind=engine), settings=Settings(auth_disabled=True))
        assert not path.exists()
    finally:
        engine.dispose()


def test_local_persistent_sqlite_remains_supported(monkeypatch, tmp_path):
    monkeypatch.delenv("K_SERVICE", raising=False)
    engine = create_engine(f"sqlite:///{tmp_path / 'local.db'}")
    try:
        app = create_app(
            engine=engine, session_factory=sessionmaker(bind=engine), settings=Settings(auth_disabled=True)
        )
        assert app.state.session_factory.kw["bind"] is engine
    finally:
        engine.dispose()

"""Database engine, sessions, and migration helpers."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from perceptshift_api.config import Settings
from perceptshift_api.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def create_db_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Ensure parent directory exists for file-backed SQLite.
        if database_url.startswith(("sqlite///", "sqlite:///")):
            raw = database_url.removeprefix("sqlite:///")
            if raw and raw != ":memory:" and not raw.startswith("file:"):
                Path(raw).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url, future=True, connect_args=connect_args)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
            _ = connection_record
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def init_database(settings: Settings) -> Engine:
    global _engine, _SessionLocal
    url = settings.resolved_database_url()
    _engine = create_db_engine(url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    # Prefer Alembic when migrations exist; fall back to metadata create for tests.
    migrations_dir = _package_root() / "migrations"
    alembic_ini = _package_root() / "alembic.ini"
    if alembic_ini.is_file() and (migrations_dir / "versions").is_dir():
        cfg = Config(str(alembic_ini))
        cfg.set_main_option("sqlalchemy.url", url)
        cfg.set_main_option("script_location", str(migrations_dir))
        command.upgrade(cfg, "head")
    else:
        Base.metadata.create_all(_engine)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database has not been initialized")
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        raise RuntimeError("Database has not been initialized")
    return _SessionLocal


def session_scope() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_database_state() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def ping_database() -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True

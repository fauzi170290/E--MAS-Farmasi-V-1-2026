from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
from threading import RLock
from typing import Iterator

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from emss.config.settings import AppSettings


class DatabaseManager:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.engine = self._create_engine()
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
        )
        # One local transaction at a time keeps the append-only audit chain
        # linear when background monitoring and UI actions occur together.
        self._session_lock = RLock()

    def _create_engine(self) -> Engine:
        engine = create_engine(
            self.settings.database_url,
            future=True,
            pool_pre_ping=True,
        )
        busy_timeout = self.settings.sqlite_busy_timeout_ms

        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={busy_timeout}")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
            finally:
                cursor.close()

        return engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._session_lock:
            db_session = self.session_factory()
            try:
                yield db_session
            except Exception:
                db_session.rollback()
                raise
            finally:
                db_session.close()

    def migrate(self, revision: str = "head") -> None:
        config = self._alembic_config()
        command.upgrade(config, revision)

    def current_revision(self) -> str | None:
        with self.engine.connect() as connection:
            exists = connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='schema_version'"
                )
            ).scalar_one_or_none()
            if not exists:
                return None
            return connection.execute(
                text("SELECT version_num FROM schema_version LIMIT 1")
            ).scalar_one_or_none()

    def dispose(self) -> None:
        self.engine.dispose()

    def _alembic_config(self) -> Config:
        package_root = (
            Path(sys._MEIPASS)  # type: ignore[attr-defined]
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[3]
        )
        config = Config(str(package_root / "alembic.ini"))
        config.set_main_option(
            "script_location", str(package_root / "migrations")
        )
        config.set_main_option("sqlalchemy.url", self.settings.database_url)
        return config

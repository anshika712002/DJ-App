import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from music_backend import auth, database
from music_backend.schemas import UserLogin
from scripts import start_backend


class _Connection:
    def __init__(self, engine):
        self.engine = engine

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement):
        assert str(statement) == "SELECT 1"
        self.engine.attempts += 1
        if self.engine.failures:
            self.engine.failures -= 1
            raise self.engine.error_type("synthetic database connection failure")


class _Engine:
    def __init__(self, failures=0, error_type=SQLAlchemyError):
        self.failures = failures
        self.error_type = error_type
        self.attempts = 0

    def connect(self):
        return _Connection(self)


class _BrokenSession:
    def __init__(self, error=None):
        self.error = error or SQLAlchemyError("synthetic database connection failure")

    async def execute(self, _statement):
        raise self.error


def test_wait_for_database_retries_then_verifies_connection(monkeypatch):
    engine = _Engine(failures=2)
    monkeypatch.setattr(database, "async_engine", engine)

    asyncio.run(
        database.wait_for_database(
            max_attempts=3,
            initial_delay_seconds=0,
            max_delay_seconds=0,
        )
    )

    assert engine.attempts == 3


def test_wait_for_database_retries_connection_refused(monkeypatch):
    engine = _Engine(failures=2, error_type=ConnectionRefusedError)
    monkeypatch.setattr(database, "async_engine", engine)

    asyncio.run(
        database.wait_for_database(
            max_attempts=3,
            initial_delay_seconds=0,
            max_delay_seconds=0,
        )
    )

    assert engine.attempts == 3


def test_wait_for_database_fails_after_bounded_retries(monkeypatch, caplog):
    engine = _Engine(failures=10)
    monkeypatch.setattr(database, "async_engine", engine)

    with pytest.raises(
        database.DatabaseUnavailableError,
        match="Database unavailable after 2 connection attempts.",
    ):
        asyncio.run(
            database.wait_for_database(
                max_attempts=2,
                initial_delay_seconds=0,
                max_delay_seconds=0,
            )
        )

    assert engine.attempts == 2
    assert "synthetic database connection failure" not in caplog.text


def test_database_dependency_maps_unavailable_database_to_503(monkeypatch):
    class Session(_BrokenSession):
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def rollback(self):
            return None

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: Session())

    async def run_dependency():
        generator = database.get_db()
        await anext(generator)
        await generator.athrow(SQLAlchemyError("synthetic database failure"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(run_dependency())

    assert exc.value.status_code == 503
    assert exc.value.detail == "Database unavailable. Please try again shortly."


def test_login_maps_database_error_to_503_without_success_log(caplog):
    caplog.set_level("INFO", logger=auth.__name__)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth.login(
                UserLogin(identifier="offline-test@example.invalid", password="not-used"),
                _BrokenSession(),
            )
        )

    assert exc.value.status_code == 503
    assert "Login successful" not in caplog.text
    assert "synthetic database connection failure" not in caplog.text


def test_login_maps_connection_refused_to_503_without_success_log(caplog):
    caplog.set_level("INFO", logger=auth.__name__)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth.login(
                UserLogin(
                    identifier="offline-test@example.invalid",
                    password="synthetic-probe-only",
                ),
                _BrokenSession(ConnectionRefusedError("synthetic connection refusal")),
            )
        )

    assert exc.value.status_code == 503
    assert "Login successful" not in caplog.text
    assert "synthetic connection refusal" not in caplog.text


def test_launcher_refuses_to_take_over_a_different_postgres_cluster(monkeypatch):
    monkeypatch.setattr(start_backend, "listener_process_ids", lambda _port: {1234})
    monkeypatch.setattr(
        start_backend,
        "process_data_directory",
        lambda _process_id: r"C:\ProgramData\pgsql17\data",
    )

    with pytest.raises(
        start_backend.StartupError,
        match="belongs to another PostgreSQL data directory",
    ):
        start_backend.assert_port_belongs_to_cluster(5432)


def test_launcher_rejects_database_url_for_a_different_database(monkeypatch):
    monkeypatch.setattr(
        start_backend.database,
        "DATABASE_URL",
        "postgresql+asyncpg://private-user:private-password@127.0.0.1:5432/other_db",
    )

    with pytest.raises(start_backend.StartupError) as exc:
        start_backend.validate_database_target()

    assert "other_db" not in str(exc.value)
    assert "private-password" not in str(exc.value)

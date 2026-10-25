import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from music_backend import main as main_module


class _Session:
    def __init__(self, error=None):
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, _statement):
        if self.error:
            raise self.error


def test_health_live_returns_ok():
    assert asyncio.run(main_module.health_live()) == {"status": "ok"}


def test_health_ready_checks_database(monkeypatch):
    monkeypatch.setattr(main_module, "AsyncSessionLocal", lambda: _Session())

    assert asyncio.run(main_module.health_ready()) == {
        "status": "ok",
        "database": "ok",
    }


def test_health_ready_returns_503_when_database_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "AsyncSessionLocal",
        lambda: _Session(SQLAlchemyError("unavailable")),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main_module.health_ready())

    assert exc.value.status_code == 503


def test_health_ready_returns_503_when_connection_is_refused(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "AsyncSessionLocal",
        lambda: _Session(ConnectionRefusedError("synthetic refusal")),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main_module.health_ready())

    assert exc.value.status_code == 503

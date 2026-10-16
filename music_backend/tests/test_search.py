"""Regression tests for the search + suggestions fixes.

Covers the root causes of:
  * Bug A - the previous search reappearing when the app is reopened
    (`/requests/suggestedSongs` must not read the user's search history).
  * Bug B - blank/one-character queries silently returning unrelated provider
    results, and the new genuine search-history endpoint.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from music_backend import song_requests as request_module


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def fetchall(self):
        return self._rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDb:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.committed = False

    async def execute(self, _statement):
        return _FakeResult(self.rows)

    async def commit(self):
        self.committed = True

    async def refresh(self, _value):
        return None

    def add(self, _value):
        return None


def _app(monkeypatch, db, payload=None):
    app = FastAPI()
    app.include_router(request_module.song_request_router, prefix="/requests")
    app.dependency_overrides[request_module.oauth2_scheme] = lambda: "test-token"

    async def get_fake_db():
        return db

    app.dependency_overrides[request_module.get_db] = get_fake_db
    monkeypatch.setattr(
        request_module,
        "decode_access_token",
        lambda _token: payload
        or {"sub": "test-user", "role": "user", "userId": 42},
    )
    return app


def test_search_rejects_blank_query_without_calling_provider(monkeypatch):
    called = []

    async def fake_search(query, limit=10):
        called.append(query)
        return []

    monkeypatch.setattr(request_module, "search_youtube_videos", fake_search)
    app = _app(monkeypatch, _FakeDb())

    response = TestClient(app).get("/requests/searchSong", params={"q": "   "})

    assert response.status_code == 400, response.text
    assert "at least" in response.json()["detail"].lower()
    assert called == []


def test_search_rejects_one_character_query(monkeypatch):
    async def fake_search(query, limit=10):
        return []

    monkeypatch.setattr(request_module, "search_youtube_videos", fake_search)
    app = _app(monkeypatch, _FakeDb())

    response = TestClient(app).get("/requests/searchSong", params={"q": "n"})

    assert response.status_code == 400, response.text


def test_search_trims_query_and_returns_echoed_query(monkeypatch):
    captured = []

    async def fake_search(query, limit=10):
        captured.append(query)
        return [{"trackId": "abc", "title": "Nightcall", "sourceType": "youtube"}]

    monkeypatch.setattr(request_module, "search_youtube_videos", fake_search)
    db = _FakeDb()
    app = _app(monkeypatch, db)

    response = TestClient(app).get(
        "/requests/searchSong", params={"q": "  night  "}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert captured == ["night"]
    assert body["query"] == "night"
    assert body["results"][0]["title"] == "Nightcall"
    assert db.committed is True


def test_suggestions_never_use_search_history(monkeypatch):
    captured_seed = []

    async def fake_search(query, limit=10):
        captured_seed.append(query)
        return [{"trackId": "xyz", "title": "Trending", "sourceType": "youtube"}]

    async def fake_user(_db, _user_name):
        return SimpleNamespace(id=7, roleObj=None)

    monkeypatch.setattr(request_module, "search_youtube_videos", fake_search)
    monkeypatch.setattr(request_module, "_get_user", fake_user)
    app = _app(monkeypatch, _FakeDb(rows=[("a-previous-search",)]))

    response = TestClient(app).get("/requests/suggestedSongs")

    assert response.status_code == 200, response.text
    assert captured_seed and captured_seed[0] in request_module.SUGGESTED_SEEDS
    assert "a-previous-search" not in captured_seed
    assert response.json()["results"][0]["title"] == "Trending"


def test_search_history_returns_distinct_recent_queries(monkeypatch):
    async def fake_user(_db, _user_name):
        return SimpleNamespace(id=7, roleObj=None)

    monkeypatch.setattr(request_module, "_get_user", fake_user)
    db = _FakeDb(rows=[("nightcall",), ("funk",), ("disco",)])
    app = _app(monkeypatch, db)

    response = TestClient(app).get("/requests/searchHistory")

    assert response.status_code == 200, response.text
    assert response.json()["queries"] == ["nightcall", "funk", "disco"]


def test_search_history_requires_valid_token(monkeypatch):
    app = _app(monkeypatch, _FakeDb(), payload=None)
    monkeypatch.setattr(request_module, "decode_access_token", lambda _token: None)

    response = TestClient(app).get("/requests/searchHistory")

    assert response.status_code == 401, response.text

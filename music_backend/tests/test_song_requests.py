import io
import math
import struct
import sys
import wave
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from music_backend import audio_assets as assets_module
from music_backend import song_requests as request_module
from music_backend.song_requests import (
    require_authorized_youtube_tracks,
    resolve_audio_asset_path,
)


class _DbResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeDb:
    def __init__(self, assets=()):
        self.assets = list(assets)
        self.pending = None

    async def execute(self, _statement):
        return _DbResult(self.assets)

    def add(self, value):
        self.pending = value

    async def commit(self):
        self.pending.id = 321

    async def refresh(self, _value):
        return None


def _request_app(monkeypatch, fake_db):
    app = FastAPI()
    app.include_router(request_module.song_request_router, prefix="/requests")
    app.dependency_overrides[request_module.oauth2_scheme] = lambda: "test-token"

    async def get_fake_db():
        return fake_db

    async def get_test_user(_db, _user_name, _role_name):
        return SimpleNamespace(id=42, roleObj=None)

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(request_module, "decode_access_token", lambda _token: {
        "sub": "test-user", "role": "user", "userId": 42
    })
    monkeypatch.setattr(request_module, "_get_user", get_test_user)
    monkeypatch.setattr(request_module, "broadcast_song_request", no_op)
    monkeypatch.setattr(request_module, "_process_mixing_async", no_op)
    app.dependency_overrides[request_module.get_db] = get_fake_db
    return app


def _test_wav():
    output = io.BytesIO()
    sample_rate = 16000
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        frames = (
            struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / sample_rate)))
            for i in range(sample_rate // 4)
        )
        audio.writeframes(b"".join(frames))
    return output.getvalue()


def test_playback_only_youtube_track_is_rejected_from_mixing():
    video_id = "abcdefghijk"
    videos = {video_id: {"snippet": {"channelId": "UC-not-authorized"}}}

    with pytest.raises(HTTPException) as exc:
        require_authorized_youtube_tracks(
            [video_id], videos, {"UC-authorized"}
        )

    assert exc.value.status_code == 403
    assert "playback-only" in exc.value.detail
    assert "cannot be mixed" in exc.value.detail


def test_authorized_youtube_track_remains_eligible_for_existing_path():
    video_id = "abcdefghijk"
    videos = {video_id: {"snippet": {"channelId": "UC-authorized"}}}

    require_authorized_youtube_tracks([video_id], videos, {"UC-authorized"})


def test_audio_asset_path_is_server_resolved_and_owner_scoped(tmp_path, monkeypatch):
    import music_backend.song_requests as requests

    monkeypatch.setattr(requests, "ASSET_DIR", tmp_path)
    audio_file = tmp_path / "licensed.wav"
    audio_file.write_bytes(b"audio")
    asset = SimpleNamespace(
        sourceType="local", ownerId=42, filePath=str(audio_file)
    )

    assert resolve_audio_asset_path(asset, "local", 42) == str(audio_file)
    with pytest.raises(HTTPException) as exc:
        resolve_audio_asset_path(asset, "local", 99)
    assert exc.value.status_code == 403


def test_audio_asset_path_rejects_client_path_and_source_mismatch(tmp_path, monkeypatch):
    import music_backend.song_requests as requests

    monkeypatch.setattr(requests, "ASSET_DIR", tmp_path)
    outside_file = tmp_path.parent / "outside.wav"
    outside_file.write_bytes(b"audio")
    asset = SimpleNamespace(
        sourceType="licensed", ownerId=42, filePath=str(outside_file)
    )

    with pytest.raises(HTTPException) as outside_exc:
        resolve_audio_asset_path(asset, "licensed", 42)
    assert outside_exc.value.status_code == 404
    with pytest.raises(HTTPException) as mismatch_exc:
        resolve_audio_asset_path(asset, "public_domain", 42)
    assert mismatch_exc.value.status_code == 400
    outside_file.unlink()


def test_request_endpoint_rejects_playback_only_youtube_track(monkeypatch, caplog):
    video_id = "abcdefghijk"

    async def video_details(_ids):
        return {video_id: {"snippet": {"channelId": "UC-other"}}}

    def unexpected_download(*_args, **_kwargs):
        pytest.fail("yt-dlp must not run for an unauthorized channel")

    monkeypatch.setattr(request_module, "get_youtube_video_details", video_details)
    monkeypatch.setattr(request_module, "authorized_channel_ids", lambda: {"UC-owned"})
    monkeypatch.setattr(
        request_module, "download_authorized_youtube_audio", unexpected_download
    )
    app = _request_app(monkeypatch, _FakeDb())

    response = TestClient(app).post(
        "/requests/requestSong",
        json={"tracks": [{"trackId": video_id, "sourceType": "youtube"}]},
    )

    assert response.status_code == 403
    assert "YOUTUBE_ALLOWED_CHANNEL_IDS" in response.json()["detail"]
    assert "UC-other" in caplog.text
    assert "UC-owned" in caplog.text


def test_request_endpoint_downloads_authorized_youtube_track(monkeypatch):
    video_id = "abcdefghijk"
    downloaded = []

    async def video_details(_ids):
        return {
            video_id: {
                "snippet": {
                    "channelId": "UC-owned",
                    "title": "Authorized video",
                    "channelTitle": "My channel",
                    "thumbnails": {},
                },
                "contentDetails": {"duration": "PT2M"},
            }
        }

    def download(track_id, _folder):
        downloaded.append(track_id)
        return f"{track_id}.mp3"

    monkeypatch.setattr(request_module, "get_youtube_video_details", video_details)
    monkeypatch.setattr(request_module, "authorized_channel_ids", lambda: {"UC-owned"})
    monkeypatch.setattr(
        request_module, "download_authorized_youtube_audio", download
    )
    app = _request_app(monkeypatch, _FakeDb())

    response = TestClient(app).post(
        "/requests/requestSong",
        json={"tracks": [{"trackId": video_id, "sourceType": "youtube"}]},
    )

    assert response.status_code == 200, response.text
    assert downloaded == [video_id]


def test_request_endpoint_accepts_server_resolved_licensed_asset(tmp_path, monkeypatch):
    asset_path = tmp_path / "licensed.wav"
    asset_path.write_bytes(b"audio data")
    asset = SimpleNamespace(
        id=17,
        ownerId=8,
        sourceType="licensed",
        title="Licensed loop",
        artist="Composer",
        artwork=None,
        duration=8,
        filePath=str(asset_path),
        license="CC BY 4.0",
        attribution="Composer",
    )
    monkeypatch.setattr(request_module, "ASSET_DIR", tmp_path)
    app = _request_app(monkeypatch, _FakeDb([asset]))

    response = TestClient(app).post(
        "/requests/requestSong",
        json={
            "tracks": [{"trackId": "asset:17", "sourceType": "licensed"}],
            "mixer": "overlay",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["tracks"][0]["trackId"] == "asset:17"
    assert response.json()["tracks"][0]["mixEligible"] is True


def test_local_audio_upload_uses_generated_server_path_and_metadata(tmp_path, monkeypatch):
    fake_db = _FakeDb()
    app = FastAPI()
    app.include_router(assets_module.audio_asset_router)
    app.dependency_overrides[assets_module.oauth2_scheme] = lambda: "test-token"

    async def get_fake_db():
        return fake_db

    monkeypatch.setattr(assets_module, "ASSET_DIR", tmp_path)
    monkeypatch.setattr(assets_module, "decode_access_token", lambda _token: {
        "tokenType": "access", "userId": 42
    })
    app.dependency_overrides[assets_module.get_db] = get_fake_db

    response = TestClient(app).post(
        "/tracks/assets",
        data={
            "title": "Authorized loop",
            "artist": "Uploader",
            "source_type": "licensed",
            "license": "CC BY 4.0",
            "attribution": "Uploader",
            "rights_confirmed": "true",
        },
        files={"file": ("loop.wav", _test_wav(), "audio/wav")},
    )

    assert response.status_code == 200, response.text
    track = response.json()
    assert track["trackId"] == "asset:321"
    assert track["sourceType"] == "licensed"
    assert track["mixEligible"] is True
    assert track["license"] == "CC BY 4.0"
    assert track["playbackUrl"] == "/tracks/assets/321/audio"
    stored_files = list(tmp_path.iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].name != "loop.wav"
    assert stored_files[0].suffix == ".wav"


def test_local_audio_mixer_exports_non_mp3_input_as_mp3(tmp_path):
    source = tmp_path / "loop.wav"
    output = tmp_path / "mixed.mp3"
    source.write_bytes(_test_wav())

    request_module.mix_tracks("without-mixing", [str(source)], str(output))

    assert output.is_file()
    assert output.read_bytes()[:3] == b"ID3"

import asyncio
from pathlib import Path

import pytest
import yt_dlp

from music_backend import youtube_api


def test_duration_seconds_parses_youtube_iso_duration():
    assert youtube_api._duration_seconds("PT2M34S") == 154
    assert youtube_api._duration_seconds("PT1H2M3S") == 3723
    assert youtube_api._duration_seconds(None) is None
    assert youtube_api._duration_seconds("unknown") is None


def test_authorized_channel_ids_accepts_singular_env_name(monkeypatch):
    monkeypatch.delenv("YOUTUBE_ALLOWED_CHANNEL_IDS", raising=False)
    monkeypatch.setenv("YOUTUBE_ALLOWED_CHANNEL_ID", "UC-authorized")

    assert youtube_api.authorized_channel_ids() == {"UC-authorized"}


def test_search_returns_youtube_order_and_marks_authorized_channels(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setenv("YOUTUBE_ALLOWED_CHANNEL_IDS", "UC-authorized")

    async def fake_api_get(_client, resource, params):
        if resource == "search":
            assert params["q"] == "dhol jageero da"
            assert params["order"] == "relevance"
            return {
                "items": [
                    {"id": {"videoId": "abcdefghijk"}},
                    {"id": {"videoId": "lmnopqrstuv"}},
                ]
            }
        assert resource == "videos"
        return {
            "items": [
                {
                    "id": "lmnopqrstuv",
                    "snippet": {
                        "title": "Unauthorized result",
                        "channelTitle": "Other channel",
                        "channelId": "UC-other",
                        "thumbnails": {},
                    },
                    "contentDetails": {"duration": "PT3M"},
                },
                {
                    "id": "abcdefghijk",
                    "snippet": {
                        "title": "Official result",
                        "channelTitle": "Authorized channel",
                        "channelId": "UC-authorized",
                        "thumbnails": {
                            "medium": {"url": "https://example.test/thumb.jpg"}
                        },
                    },
                    "contentDetails": {"duration": "PT2M34S"},
                },
            ]
        }

    monkeypatch.setattr(youtube_api, "_youtube_api_get", fake_api_get)
    results = asyncio.run(youtube_api.search_youtube_videos("dhol jageero da"))

    assert [item["trackId"] for item in results] == [
        "abcdefghijk",
        "lmnopqrstuv",
    ]
    assert results[0]["title"] == "Official result"
    assert results[0]["duration"] == 154
    assert results[0]["sourceType"] == "youtube"
    assert results[0]["mixEligible"] is True
    assert results[1]["mixEligible"] is False
    assert results[0]["playbackUrl"] == "https://www.youtube.com/watch?v=abcdefghijk"
    assert not any("download" in key.lower() for key in results[0])


def test_audio_download_refuses_channels_outside_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_ALLOWED_CHANNEL_IDS", "UC-authorized")
    downloaded = False

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download):
            assert download is False
            return {"channel_id": "UC-other"}

        def download(self, _urls):
            nonlocal downloaded
            downloaded = True

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    with pytest.raises(PermissionError, match="not in YOUTUBE_ALLOWED_CHANNEL_IDS"):
        youtube_api.download_authorized_youtube_audio(
            "abcdefghijk", str(tmp_path)
        )

    assert downloaded is False
    assert not Path(tmp_path, "abcdefghijk.mp3").exists()


def test_audio_download_only_runs_for_authorized_channel(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_ALLOWED_CHANNEL_IDS", "UC-authorized")

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download):
            assert download is False
            return {"channel_id": "UC-authorized"}

        def download(self, urls):
            assert urls == ["https://www.youtube.com/watch?v=abcdefghijk"]
            Path(tmp_path, "abcdefghijk.mp3").write_bytes(b"authorized audio")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    result = youtube_api.download_authorized_youtube_audio(
        "abcdefghijk", str(tmp_path)
    )

    assert result == str(Path(tmp_path, "abcdefghijk.mp3"))
    assert Path(result).read_bytes() == b"authorized audio"

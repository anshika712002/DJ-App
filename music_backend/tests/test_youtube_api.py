import asyncio
import http.cookiejar
from pathlib import Path

import pytest
import yt_dlp
from yt_dlp.cookies import CookieLoadError

from music_backend import youtube_api


def _netscape_cookie_file(count=1, newline="\n"):
    lines = ["# Netscape HTTP Cookie File"]
    lines.extend(
        f".example{index}.test\tTRUE\t/\tTRUE\t0\tSYNTHETIC_NAME_{index}"
        "\tSYNTHETIC_VALUE"
        for index in range(count)
    )
    return newline.join(lines) + newline


def test_duration_seconds_parses_youtube_iso_duration():
    assert youtube_api._duration_seconds("PT2M34S") == 154
    assert youtube_api._duration_seconds("PT1H2M3S") == 3723
    assert youtube_api._duration_seconds(None) is None
    assert youtube_api._duration_seconds("unknown") is None


def test_authorized_channel_ids_accepts_singular_env_name(monkeypatch):
    monkeypatch.delenv("YOUTUBE_ALLOWED_CHANNEL_IDS", raising=False)
    monkeypatch.setenv("YOUTUBE_ALLOWED_CHANNEL_ID", "UC-authorized")

    assert youtube_api.authorized_channel_ids() == {"UC-authorized"}


def test_search_returns_youtube_order_and_marks_all_tracks_mixable(monkeypatch):
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
    assert results[1]["mixEligible"] is True
    assert results[0]["playbackUrl"] == "https://www.youtube.com/watch?v=abcdefghijk"
    assert not any("download" in key.lower() for key in results[0])


def test_audio_download_runs_for_any_channel(monkeypatch, tmp_path):
    monkeypatch.delenv("YTDLP_COOKIE_FILE", raising=False)
    monkeypatch.setattr(
        youtube_api, "_default_ytdlp_cookie_file", lambda: tmp_path / "missing.txt"
    )

    class FakeYoutubeDL:
        def __init__(self, _options):
            assert "cookiefile" not in _options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, urls):
            assert urls == ["https://www.youtube.com/watch?v=abcdefghijk"]
            Path(tmp_path, "abcdefghijk.mp3").write_bytes(b"downloaded audio")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    result = youtube_api.download_authorized_youtube_audio(
        "abcdefghijk", str(tmp_path)
    )

    assert result == str(Path(tmp_path, "abcdefghijk.mp3"))
    assert Path(result).read_bytes() == b"downloaded audio"


def test_audio_download_passes_configured_cookie_file(monkeypatch, tmp_path, caplog):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_bytes(_netscape_cookie_file(22, "\r\n").encode("utf-8"))
    monkeypatch.setenv("YTDLP_COOKIE_FILE", str(cookie_file))
    caplog.set_level("INFO", logger=youtube_api.__name__)
    captured_options = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured_options.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _urls):
            Path(tmp_path, "abcdefghijk.mp3").write_bytes(b"downloaded audio")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    result = youtube_api.download_authorized_youtube_audio(
        "abcdefghijk", str(tmp_path)
    )

    assert result == str(Path(tmp_path, "abcdefghijk.mp3"))
    assert captured_options["cookiefile"] == str(cookie_file)
    assert "yt-dlp cookie file configured: yes; readable: yes" in caplog.text
    assert "validation passed: header_valid=yes; record_count=22" in caplog.text
    assert "SYNTHETIC_VALUE" not in caplog.text


def test_netscape_fixture_is_accepted_by_installed_ytdlp_parser(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_bytes(_netscape_cookie_file(22, "\r\n").encode("utf-8"))

    cookie_jar = yt_dlp.cookies.YoutubeDLCookieJar(str(cookie_file))
    cookie_jar.load()

    assert len(cookie_jar) == 22


@pytest.mark.parametrize(
    ("content", "header_valid", "failure_reason"),
    [
        (
            "# Not a Netscape file\n"
            ".example.test\tTRUE\t/\tTRUE\t0\tSYNTHETIC_NAME\tSYNTHETIC_VALUE\n",
            "no",
            "invalid_header",
        ),
        (
            "# Netscape HTTP Cookie File\n"
            ".example.test\tTRUE\t/\tTRUE\t0\tSYNTHETIC_NAME\n",
            "yes",
            "invalid_field_count",
        ),
        (
            "# Netscape HTTP Cookie File\n"
            ".example.test\tTRUE\t/\tTRUE\tinvalid\tSYNTHETIC_NAME\tSYNTHETIC_VALUE\n",
            "yes",
            "invalid_expiry",
        ),
        (
            "# Netscape HTTP Cookie File\n"
            ".example.test\tTRUE\t/\tTRUE\t123.5\tSYNTHETIC_NAME\tSYNTHETIC_VALUE\n",
            "yes",
            "invalid_expiry",
        ),
        (
            "# Netscape HTTP Cookie File\n"
            ".example.test\tFALSE\t/\tTRUE\t0\tSYNTHETIC_NAME\tSYNTHETIC_VALUE\n",
            "yes",
            "invalid_domain_flag",
        ),
        (
            "\ufeff# Netscape HTTP Cookie File\n"
            ".example.test\tTRUE\t/\tTRUE\t0\tSYNTHETIC_NAME\tSYNTHETIC_VALUE\n",
            "no",
            "utf8_bom",
        ),
        (
            b"# Netscape HTTP Cookie File\n"
            b".example.test\tTRUE\t/\tTRUE\t0\tSYNTHETIC_NAME\t\xff\n",
            "yes",
            "invalid_utf8",
        ),
    ],
)
def test_invalid_cookie_file_logs_sanitized_diagnostics(
    monkeypatch, tmp_path, caplog, content, header_valid, failure_reason
):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_bytes(
        content if isinstance(content, bytes) else content.encode("utf-8")
    )
    monkeypatch.setenv("YTDLP_COOKIE_FILE", str(cookie_file))
    caplog.set_level("INFO", logger=youtube_api.__name__)

    with pytest.raises(
        youtube_api.CookieFileError,
        match="Configured yt-dlp cookie file is invalid.",
    ):
        youtube_api._ytdlp_cookie_file()

    assert f"header_valid={header_valid}" in caplog.text
    assert "record_count=1" in caplog.text
    assert f"failure_reason={failure_reason}" in caplog.text
    assert "SYNTHETIC_NAME" not in caplog.text
    assert "SYNTHETIC_VALUE" not in caplog.text


def test_configured_missing_cookie_file_fails_without_logging_path(
    monkeypatch, tmp_path, caplog
):
    missing_file = tmp_path / "private-cookie-path.txt"
    monkeypatch.setenv("YTDLP_COOKIE_FILE", str(missing_file))

    with pytest.raises(
        youtube_api.CookieFileError,
        match="Configured yt-dlp cookie file is unavailable.",
    ):
        youtube_api.download_authorized_youtube_audio(
            "abcdefghijk", str(tmp_path / "downloads")
        )

    assert "configured: yes; readable: no" in caplog.text
    assert str(missing_file) not in caplog.text


@pytest.mark.parametrize(
    "cookie_load_error", [CookieLoadError, http.cookiejar.LoadError]
)
def test_invalid_cookie_download_error_is_sanitized(
    monkeypatch, tmp_path, caplog, cookie_load_error
):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(_netscape_cookie_file(), encoding="utf-8")
    monkeypatch.setenv("YTDLP_COOKIE_FILE", str(cookie_file))

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _urls):
            raise cookie_load_error("failed to load cookies: synthetic-cookie-secret")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    with pytest.raises(
        youtube_api.CookieFileError,
        match="Provide a valid Netscape cookies.txt file.",
    ):
        youtube_api.download_authorized_youtube_audio(
            "abcdefghijk", str(tmp_path / "downloads")
        )

    assert "accepted: no" in caplog.text
    assert "synthetic-cookie-secret" not in caplog.text
    assert str(cookie_file) not in caplog.text


def test_unrelated_error_mentioning_cookies_is_not_mislabeled(
    monkeypatch, tmp_path, caplog
):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(_netscape_cookie_file(), encoding="utf-8")
    monkeypatch.setenv("YTDLP_COOKIE_FILE", str(cookie_file))

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _urls):
            raise RuntimeError("unrelated downloader issue mentioning cookies")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    with pytest.raises(
        RuntimeError, match="unrelated downloader issue mentioning cookies"
    ):
        youtube_api.download_authorized_youtube_audio(
            "abcdefghijk", str(tmp_path / "downloads")
        )

    assert "accepted: no" not in caplog.text

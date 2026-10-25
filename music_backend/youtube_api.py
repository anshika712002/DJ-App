import http.cookiejar
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
YOUTUBE_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YTDLP_COOKIE_EXPIRY = re.compile(rb"[0-9]+\Z")
logger = logging.getLogger(__name__)

# HTTPX's INFO request log includes the full URL, including the YouTube API key.
logging.getLogger("httpx").setLevel(logging.WARNING)


class CookieFileError(RuntimeError):
    """A configured yt-dlp cookie file is unavailable or invalid."""


class _QuietYtDlpLogger:
    def debug(self, _message: str) -> None:
        pass

    def warning(self, _message: str) -> None:
        pass

    def error(self, _message: str) -> None:
        pass


def _default_ytdlp_cookie_file() -> Path:
    if os.name == "nt":
        return Path(__file__).resolve().parents[1] / "cookies.txt"
    return Path("/etc/secrets/cookies.txt")


def _ytdlp_cookie_file_diagnostics(
    cookie_path: Path,
) -> tuple[bool, int, str | None]:
    try:
        content = cookie_path.read_bytes()
    except OSError:
        return False, 0, "read_error"

    lines = content.splitlines()
    header = lines[0] if lines else b""
    has_utf8_bom = header.startswith(b"\xef\xbb\xbf")
    failure_reason = "utf8_bom" if has_utf8_bom else None

    try:
        header_text = header.decode("utf-8")
    except UnicodeDecodeError:
        header_valid = False
        failure_reason = failure_reason or "invalid_utf8"
    else:
        header_valid = bool(http.cookiejar.NETSCAPE_MAGIC_RGX.match(header_text))
        if not header_valid:
            failure_reason = failure_reason or "invalid_header"

    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        failure_reason = failure_reason or "invalid_utf8"

    record_count = 0
    for line in lines[1:]:
        if line.startswith(b"#HttpOnly_"):
            line = line[len(b"#HttpOnly_"):]
        elif line.startswith(b"#") or not line.strip():
            continue

        if not line.strip():
            continue
        record_count += 1
        fields = line.split(b"\t")
        if len(fields) != 7:
            failure_reason = failure_reason or "invalid_field_count"
        elif fields[4] and not YTDLP_COOKIE_EXPIRY.fullmatch(fields[4]):
            failure_reason = failure_reason or "invalid_expiry"
        elif (fields[1] == b"TRUE") != fields[0].startswith(b"."):
            failure_reason = failure_reason or "invalid_domain_flag"

    return header_valid, record_count, failure_reason


def _ytdlp_cookie_file() -> Path | None:
    configured_path = os.getenv("YTDLP_COOKIE_FILE")
    cookie_path = (
        Path(configured_path).expanduser()
        if configured_path
        else _default_ytdlp_cookie_file()
    )

    try:
        with cookie_path.open("rb"):
            pass
    except FileNotFoundError:
        if configured_path:
            logger.error("yt-dlp cookie file configured: yes; readable: no")
            raise CookieFileError(
                "Configured yt-dlp cookie file is unavailable."
            ) from None
        logger.info("yt-dlp cookie file configured: no; readable: no")
        return None
    except OSError:
        logger.error("yt-dlp cookie file configured: yes; readable: no")
        raise CookieFileError(
            "Configured yt-dlp cookie file is not readable."
        ) from None

    logger.info("yt-dlp cookie file configured: yes; readable: yes")
    header_valid, record_count, failure_reason = _ytdlp_cookie_file_diagnostics(
        cookie_path
    )
    if failure_reason is not None:
        logger.error(
            "yt-dlp cookie file validation failed: header_valid=%s; "
            "record_count=%d; failure_reason=%s",
            "yes" if header_valid else "no",
            record_count,
            failure_reason,
        )
        raise CookieFileError("Configured yt-dlp cookie file is invalid.")
    logger.info(
        "yt-dlp cookie file validation passed: header_valid=%s; record_count=%d",
        "yes" if header_valid else "no",
        record_count,
    )
    return cookie_path


def authorized_channel_ids() -> set[str]:
    configured_ids = (
        os.getenv("YOUTUBE_ALLOWED_CHANNEL_IDS")
        or os.getenv("YOUTUBE_ALLOWED_CHANNEL_ID", "")
    )
    return {
        channel_id.strip()
        for channel_id in configured_ids.split(",")
        if channel_id.strip()
    }


def _duration_seconds(value: str | None) -> int | None:
    if not value:
        return None
    match = re.fullmatch(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value
    )
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes or 0) * 60 + int(
        float(seconds or 0)
    )


async def _youtube_api_get(
    client: httpx.AsyncClient, resource: str, params: dict[str, Any]
) -> dict[str, Any]:
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="YouTube search is not configured; set YOUTUBE_API_KEY.",
        )

    try:
        response = await client.get(
            f"{YOUTUBE_API_BASE}/{resource}",
            params={**params, "key": api_key},
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        logger.error("YouTube Data API returned HTTP %s", exc.response.status_code)
        raise HTTPException(
            status_code=502,
            detail=(
                "YouTube search failed. Check the API key, YouTube Data API v3 "
                "access, and API quota."
            ),
        ) from exc
    except (httpx.RequestError, ValueError) as exc:
        logger.error("YouTube Data API request failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502, detail="Could not retrieve results from YouTube."
        ) from exc


async def get_youtube_video_details(
    video_ids: list[str],
) -> dict[str, dict[str, Any]]:
    if not video_ids:
        return {}
    if any(not YOUTUBE_VIDEO_ID.fullmatch(video_id) for video_id in video_ids):
        raise HTTPException(status_code=400, detail="Invalid YouTube video ID.")

    videos: dict[str, dict[str, Any]] = {}
    async with httpx.AsyncClient(timeout=15) as client:
        for index in range(0, len(video_ids), 50):
            batch = video_ids[index : index + 50]
            payload = await _youtube_api_get(
                client,
                "videos",
                {
                    "part": "snippet,contentDetails,status",
                    "id": ",".join(batch),
                    "maxResults": str(len(batch)),
                },
            )
            videos.update(
                {
                    item["id"]: item
                    for item in payload.get("items", [])
                    if item.get("id") and item.get("snippet")
                }
            )
    return videos


def song_from_youtube_video(
    video_id: str,
    video: dict[str, Any],
    allowed_channels: set[str],
) -> dict[str, Any]:
    snippet = video["snippet"]
    thumbnails = snippet.get("thumbnails", {})
    thumbnail = (
        thumbnails.get("medium")
        or thumbnails.get("default")
        or thumbnails.get("high")
        or {}
    ).get("url", "")

    return {
        "trackId": video_id,
        "sourceType": "youtube",
        "title": snippet.get("title"),
        "artist": snippet.get("channelTitle", ""),
        "artwork": thumbnail,
        "duration": _duration_seconds(
            video.get("contentDetails", {}).get("duration")
        ),
        "playbackUrl": f"https://www.youtube.com/watch?v={video_id}",
        "mixEligible": True,
        "license": snippet.get("license", "YouTube"),
        "attribution": snippet.get("channelTitle", ""),
    }


async def search_youtube_videos(query: str, limit: int = 10) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15) as client:
        search_payload = await _youtube_api_get(
            client,
            "search",
            {
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "relevance",
                "maxResults": "50",
            },
        )

        ordered_ids = [
            item["id"]["videoId"]
            for item in search_payload.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        videos_payload = await _youtube_api_get(
            client,
            "videos",
            {
                "part": "snippet,contentDetails,status",
                "id": ",".join(ordered_ids),
                "maxResults": str(min(len(ordered_ids), 50)),
            },
        ) if ordered_ids else {"items": []}

    videos = {
        item["id"]: item
        for item in videos_payload.get("items", [])
        if item.get("id") and item.get("snippet")
    }
    allowed_channels = authorized_channel_ids()
    return [
        song_from_youtube_video(video_id, videos[video_id], allowed_channels)
        for video_id in ordered_ids
        if video_id in videos
    ][:limit]


def download_authorized_youtube_audio(
    video_id: str, download_folder: str
) -> str:
    from yt_dlp import YoutubeDL
    from yt_dlp import cookies as yt_dlp_cookies

    cookie_load_errors = (http.cookiejar.LoadError,)
    cookie_load_error = getattr(yt_dlp_cookies, "CookieLoadError", None)
    if isinstance(cookie_load_error, type) and issubclass(
        cookie_load_error, BaseException
    ):
        cookie_load_errors += (cookie_load_error,)

    if not YOUTUBE_VIDEO_ID.fullmatch(video_id):
        raise ValueError("Invalid YouTube video ID.")

    os.makedirs(download_folder, exist_ok=True)
    output_path = os.path.join(download_folder, f"{video_id}.mp3")
    url = f"https://www.youtube.com/watch?v={video_id}"
    if os.path.isfile(output_path):
        return output_path

    cookie_file = _ytdlp_cookie_file()
    options = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(download_folder, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "logger": _QuietYtDlpLogger(),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    if cookie_file is not None:
        options["cookiefile"] = str(cookie_file)

    try:
        with YoutubeDL(options) as downloader:
            downloader.download([url])
    except cookie_load_errors:
        if cookie_file is not None:
            header_valid, record_count, _ = _ytdlp_cookie_file_diagnostics(
                cookie_file
            )
            logger.error(
                "yt-dlp cookie file configured: yes; readable: yes; "
                "accepted: no; header_valid=%s; record_count=%d; "
                "failure_reason=yt_dlp_parser_rejected",
                "yes" if header_valid else "no",
                record_count,
            )
            raise CookieFileError(
                "Configured yt-dlp cookie file was rejected. "
                "Provide a valid Netscape cookies.txt file."
            ) from None
        raise

    if not os.path.isfile(output_path):
        raise RuntimeError(f"yt-dlp did not create the audio file for {video_id}.")
    return output_path

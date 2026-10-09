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
logger = logging.getLogger(__name__)


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
    channel_id = snippet.get("channelId", "")

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
        "mixEligible": channel_id in allowed_channels,
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

    if not YOUTUBE_VIDEO_ID.fullmatch(video_id):
        raise ValueError("Invalid YouTube video ID.")

    allowed_channels = authorized_channel_ids()
    if not allowed_channels:
        raise PermissionError(
            "Set YOUTUBE_ALLOWED_CHANNEL_IDS to channels authorized for audio processing."
        )

    os.makedirs(download_folder, exist_ok=True)
    output_path = os.path.join(download_folder, f"{video_id}.mp3")
    url = f"https://www.youtube.com/watch?v={video_id}"
    options = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(download_folder, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=False)
        channel_id = (info or {}).get("channel_id")
        if channel_id not in allowed_channels:
            raise PermissionError(
                "This video's channel is not in YOUTUBE_ALLOWED_CHANNEL_IDS."
            )
        if os.path.isfile(output_path):
            return output_path
        downloader.download([url])

    if not os.path.isfile(output_path):
        raise RuntimeError(f"yt-dlp did not create the audio file for {video_id}.")
    return output_path

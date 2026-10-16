import logging, os, asyncio, re, emoji, time, random
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Query,
    BackgroundTasks
)
from audio_assets import ASSET_DIR
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import (
    select,
    desc,
    func
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from models import (
    AudioAsset,
    SongRequest,
    RequestStatus,
    User,
    UserSearchHistory,
)
from database import get_db, AsyncSessionLocal
from auth_utils import decode_access_token
from typing import Optional, List
from fastapi.security import OAuth2PasswordBearer
from starlette.concurrency import run_in_threadpool
from process_audio import (
    mashup_tracks,
    overlay_tracks,
    crossfade_tracks,
    change_pitch,
    change_tempo,
    mix_audio,
    overlay_beat,
    beat_background,
    YOUTUBE_DOWNLOADS_FOLDER,
    MIXED_AUDIO_FOLDER,
    copy_audio_as_mp3,
)
from youtube_api import (
    YOUTUBE_VIDEO_ID,
    authorized_channel_ids,
    download_authorized_youtube_audio,
    get_youtube_video_details,
    search_youtube_videos,
    song_from_youtube_video,
)

from schemas import (
    SongMixRequest,
    Track,
    AllSongResponseWrapper,
    SongRequestSimplifiedResponse,
)

from dotenv import load_dotenv

load_dotenv()

ORIGINAL_AUDIO_FOLDER = YOUTUBE_DOWNLOADS_FOLDER

PUBLIC_API_BASE = os.getenv("PUBLIC_API_BASE", "")

song_request_router = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

VALID_MIXERS = {
    "alternate",
    "overlay",
    "crossfade",
    "tempo-sync",
    "pitch-shift",
    "beat-overlay",
    "beat-background",
    "without-mixing"
}

# Minimum characters before the YouTube provider is queried (see search_song).
MIN_SEARCH_LENGTH = 2

# Neutral seeds for the home "Recommended" rail. These deliberately do NOT use
# the user's search history, so a previous search can never reappear as a fresh
# result when the app is reopened.
SUGGESTED_SEEDS = (
    "trending music",
    "top hits",
    "popular songs",
    "new music friday",
)

async def _get_user(db: AsyncSession, userName: str):
    stmt = (
        select(User)
        .options(joinedload(User.roleObj))
        .where(User.userName == userName)
        .order_by(User.id.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().first()

def sanitize_filename(title: str) -> str:
    title = emoji.replace_emoji(title, replace='')
    title = re.sub(r'#\S+', '', title)
    words = re.findall(r'\b\w+\b', title)
    return "_".join(words[:3]).lower()

def mix_tracks(mixing_mode, valid_tracks, final_path):
    start_time = time.time()

    if mixing_mode == "alternate":
        mashup_tracks(valid_tracks[0], valid_tracks[1], final_path)

    elif mixing_mode == "overlay":
        overlay_tracks(valid_tracks[0], valid_tracks[1], final_path)

    elif mixing_mode == "crossfade":
        crossfade_tracks(valid_tracks[0], valid_tracks[1], final_path)

    elif mixing_mode == "tempo-sync":
        temp_path = final_path.replace(".mp3", "_tempo_temp.mp3")
        change_tempo(valid_tracks[1], temp_path, speed=1.1)
        mix_audio(valid_tracks[0], temp_path, final_path)
        os.remove(temp_path)

    elif mixing_mode == "pitch-shift":
        temp_path = final_path.replace(".mp3", "_pitch_temp.mp3")
        change_pitch(valid_tracks[1], temp_path, semitones=2)
        mix_audio(valid_tracks[0], temp_path, final_path)
        os.remove(temp_path)

    elif mixing_mode == "beat-overlay":
        overlay_beat(valid_tracks[0], valid_tracks[1], final_path)

    elif mixing_mode == "beat-background":
        beat_background(valid_tracks[0], valid_tracks[1], final_path)

    elif mixing_mode == "without-mixing":
        copy_audio_as_mp3(valid_tracks[0], final_path)

    else:
        raise ValueError("Invalid mixing mode")

    logger.info(f"Mix '{mixing_mode}' completed in {time.time() - start_time:.2f}s")


def resolve_audio_asset_path(
    asset: AudioAsset, source_type: str, requester_id: int
) -> str:
    if asset.sourceType != source_type:
        raise HTTPException(status_code=400, detail="Audio asset source type mismatch.")
    if asset.sourceType == "local" and asset.ownerId != requester_id:
        raise HTTPException(
            status_code=403, detail="This local audio asset belongs to another user."
        )
    path = Path(asset.filePath).resolve()
    if path.parent != ASSET_DIR or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio asset file is unavailable.")
    return str(path)


@song_request_router.post("/requestSong")
async def download_and_mix(
    background_tasks: BackgroundTasks,
    request_data: SongMixRequest,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    start_time = time.time()
    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(401, "Invalid token")

    user = await _get_user(db, user_data["sub"])
    if not user:
        raise HTTPException(404, "User not found")

    tracks = request_data.tracks
    if not 1 <= len(tracks) <= 2 or len({(t.sourceType, t.trackId) for t in tracks}) != len(tracks):
        raise HTTPException(
            status_code=400, detail="Select one or two different tracks."
        )
    youtube_tracks = [track for track in tracks if track.sourceType == "youtube"]
    assets_by_id = {}
    asset_refs = [track for track in tracks if track.sourceType != "youtube"]
    if any(not track.trackId.startswith("asset:") for track in asset_refs):
        raise HTTPException(status_code=400, detail="Invalid audio asset reference.")
    try:
        asset_ids = [int(track.trackId.split(":", 1)[1]) for track in asset_refs]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid audio asset reference.") from exc
    if asset_ids:
        result = await db.execute(select(AudioAsset).where(AudioAsset.id.in_(asset_ids)))
        assets_by_id = {asset.id: asset for asset in result.scalars().all()}
        if len(assets_by_id) != len(set(asset_ids)):
            raise HTTPException(status_code=404, detail="One or more audio assets were not found.")

    allowed_channels = authorized_channel_ids()
    youtube_ids = [track.trackId for track in youtube_tracks]
    if any(not YOUTUBE_VIDEO_ID.fullmatch(track_id) for track_id in youtube_ids):
        raise HTTPException(status_code=400, detail="Invalid YouTube video ID.")
    videos = await get_youtube_video_details(youtube_ids)
    if any(track_id not in videos for track_id in youtube_ids):
        raise HTTPException(status_code=404, detail="One or more YouTube videos are unavailable.")

    song_infos = []
    audio_paths = []
    youtube_song_infos = {
        track_id: song_from_youtube_video(track_id, videos[track_id], allowed_channels)
        for track_id in youtube_ids
    }
    for track in tracks:
        if track.sourceType == "youtube":
            song = youtube_song_infos[track.trackId]
            song_infos.append(song)
            audio_paths.append(os.path.join(ORIGINAL_AUDIO_FOLDER, track.trackId + ".mp3"))
        else:
            asset_id = int(track.trackId.split(":", 1)[1])
            asset = assets_by_id[asset_id]
            path = resolve_audio_asset_path(asset, track.sourceType, user.id)
            song = {
                "trackId": track.trackId,
                "sourceType": asset.sourceType,
                "title": asset.title,
                "artist": asset.artist,
                "artwork": asset.artwork,
                "duration": asset.duration,
                "playbackUrl": f"/tracks/assets/{asset.id}/audio",
                "mixEligible": True,
                "license": asset.license,
                "attribution": asset.attribution,
            }
            song_infos.append(song)
            audio_paths.append(path)

    if youtube_ids:
        download_results = await asyncio.gather(
            *[
                run_in_threadpool(
                    download_authorized_youtube_audio,
                    track_id,
                    ORIGINAL_AUDIO_FOLDER,
                )
                for track_id in youtube_ids
            ],
            return_exceptions=True,
        )
        failed_tracks = [
            tid for tid, res in zip(youtube_ids, download_results)
            if isinstance(res, BaseException)
        ]
        if failed_tracks:
            logger.error("Authorized YouTube audio download failed for video IDs: %s", failed_tracks)
            raise HTTPException(
                status_code=502,
                detail="Could not process audio for authorized YouTube content. Confirm availability and FFmpeg installation.",
            )

    selected_mixer = request_data.mixer if request_data.mixer in VALID_MIXERS else "overlay"
    if len(tracks) == 1:
        selected_mixer = "without-mixing"
    track_metadata = [
        {
            key: song.get(key)
            for key in ("trackId", "sourceType", "title", "artist", "artwork", "duration", "license", "attribution")
        }
        for song in song_infos
    ]

    new_req = SongRequest(
        requesterId=user.id,
        status=RequestStatus.PENDING,
        videoIds=",".join(track.trackId for track in tracks),
        trackMetadata=track_metadata,
        songName=song_infos[0]["title"] if len(song_infos) > 0 else None,
        songName2=song_infos[1]["title"] if len(song_infos) > 1 else None,
        tipAmount=request_data.tipAmount,
        mixer=selected_mixer,
        videoTitle1=song_infos[0]["title"] if len(song_infos) > 0 else None,
        videoThumbnail1=song_infos[0]["artwork"] if len(song_infos) > 0 else None,
        videoArtist1=song_infos[0]["artist"] if len(song_infos) > 0 else None,
        videoTitle2=song_infos[1]["title"] if len(song_infos) > 1 else None,
        videoThumbnail2=song_infos[1]["artwork"] if len(song_infos) > 1 else None,
        videoArtist2=song_infos[1]["artist"] if len(song_infos) > 1 else None,
    )

    db.add(new_req)
    await db.commit()
    await db.refresh(new_req)

    final_filename = f"request_{new_req.id}_{selected_mixer}.mp3"
    final_path = os.path.join(MIXED_AUDIO_FOLDER, final_filename)

    # Mixing (download/ffmpeg) is slow, so run it in the background. The request
    # is returned immediately as "pending"; the client polls /allSongs until the
    # status becomes "completed" (or "failed").
    background_tasks.add_task(
        _process_mixing_async, new_req.id, selected_mixer, audio_paths, final_path
    )

    return {
        "requestId": new_req.id,
        "message": f"Mix queued with '{selected_mixer}' mode.",
        "status": RequestStatus.PENDING.value,
        "mixedAudioUrl": f"{PUBLIC_API_BASE}/requests/audio/byRequestId/{new_req.id}",
        "tracks": song_infos

    }
    
async def _process_mixing_async(request_id, mixer, audio_paths, final_path):
    try:
        valid_tracks = audio_paths
        start_time = time.time() 
        await run_in_threadpool(mix_tracks, mixer, valid_tracks, final_path)

        if not os.path.exists(final_path):
            raise Exception("Final mixed file not created")

        async with AsyncSessionLocal() as session:
            stmt = select(SongRequest).where(SongRequest.id == request_id)
            result = await session.execute(stmt)
            req = result.scalar_one_or_none()

            if not req:
                raise Exception("SongRequest not found during mixing")

            with open(final_path, "rb") as f:
                req.mixedAudioData = f.read()

            req.mixedAudioPath = os.path.basename(final_path)
            req.status = RequestStatus.COMPLETED

            await session.flush()
            await session.commit()
            await session.refresh(req)

        logger.info(f"Mix saved for request {request_id}")
        logger.info(f"ðŸš€ /mixed Audio takes {time.time() - start_time:.2f}s")

    except Exception as e:
        logger.error(f"Mixing failed: {e}")
        async with AsyncSessionLocal() as session:
            stmt = select(SongRequest).where(SongRequest.id == request_id)
            r = await session.execute(stmt)
            req = r.scalar_one_or_none()
            if req:
                req.status = RequestStatus.FAILED
                await session.commit()

def _authorize_media_request(request: Request, token: Optional[str]) -> int:
    """Return the authenticated userId, or raise 401."""
    candidate = (
        token
        or request.headers.get("Authorization", "").replace("Bearer ", "")
        or request.query_params.get("token")
    )
    payload = decode_access_token(candidate) if candidate else None
    if not payload or not payload.get("userId"):
        raise HTTPException(401, "Unauthorized")
    return payload["userId"]


@song_request_router.get("/audio/byRequestId/{request_id}")
async def download_mixed_audio_by_request(
    request_id: int,
    request: Request,
    token: Optional[str] = Query(
        None, description="JWT access token (alternative to the Authorization header)"
    ),
    db: AsyncSession = Depends(get_db),
):
    user_id = _authorize_media_request(request, token)

    result = await db.execute(select(SongRequest).where(SongRequest.id == request_id))
    song_request = result.scalar_one_or_none()
    if not song_request or not song_request.mixedAudioPath:
        raise HTTPException(404, "Mixed audio is not ready yet")
    if song_request.requesterId != user_id:
        raise HTTPException(403, "You can only play your own mixes")

    safe_name = os.path.basename(song_request.mixedAudioPath)
    folder = os.path.abspath(MIXED_AUDIO_FOLDER)
    file_path = os.path.abspath(os.path.join(folder, safe_name))
    if not file_path.startswith(folder + os.sep) or not os.path.isfile(file_path):
        raise HTTPException(404, "File not found")
    if not file_path.lower().endswith(".mp3"):
        raise HTTPException(404, "File not found")

    return FileResponse(
        path=file_path, media_type="audio/mpeg", filename=safe_name
    )


@song_request_router.get("/audio/{filename}")
async def download_mixed_audio(
    filename: str,
    request: Request,
    token: Optional[str] = Query(
        None, description="JWT access token (alternative to the Authorization header)"
    ),
    db: AsyncSession = Depends(get_db),
):
    user_id = _authorize_media_request(request, token)

    # Reject anything that escapes the mixed-audio folder (path traversal)
    safe_name = os.path.basename(filename)
    folder = os.path.abspath(MIXED_AUDIO_FOLDER)
    file_path = os.path.abspath(os.path.join(folder, safe_name))

    if (
        not file_path.startswith(folder + os.sep)
        or not file_path.lower().endswith(".mp3")
        or not os.path.isfile(file_path)
    ):
        raise HTTPException(404, "File not found")

    # Enforce ownership: the filename encodes the request id (request_<id>_...).
    match = re.match(r"request_(\d+)_", safe_name)
    if match:
        owner = await db.execute(
            select(SongRequest.requesterId).where(SongRequest.id == int(match.group(1)))
        )
        owner_id = owner.scalar_one_or_none()
        if owner_id is not None and owner_id != user_id:
            raise HTTPException(403, "You can only play your own mixes")

    return FileResponse(
        path=file_path, media_type="audio/mpeg", filename=safe_name
    )

@song_request_router.get("/searchSong")
async def search_song(
    q: str = Query(...),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):

    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(401, "Invalid token")

    # A blank or one-character query makes the YouTube provider fall back to an
    # arbitrary popular list, which looks like stale/incorrect results. Reject
    # it explicitly so the client can distinguish "too short" from "no results".
    query = (q or "").strip()
    if len(query) < MIN_SEARCH_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Enter at least {MIN_SEARCH_LENGTH} characters to search.",
        )

    results = await search_youtube_videos(query, limit=10)
    await db.execute(
        insert(UserSearchHistory).values(
            userId=user_data["userId"],
            queryText=query,
        )
    )
    await db.commit()
    return {"query": query, "results": results}


@song_request_router.get("/searchHistory")
async def get_search_history(
    limit: int = Query(10, ge=1, le=50),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    """The authenticated user's genuine recent searches, newest first.

    Powers the clearly-labelled "Recent searches" section only; it is never
    used to seed the home/suggestions list.
    """
    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(401, "Invalid or expired token")

    user = await _get_user(db, user_data["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    latest = func.max(UserSearchHistory.timestamp).label("latest")
    result = await db.execute(
        select(UserSearchHistory.queryText, latest)
        .where(UserSearchHistory.userId == user.id)
        .group_by(UserSearchHistory.queryText)
        .order_by(desc(latest))
        .limit(limit)
    )
    queries = [row[0] for row in result.fetchall() if row and row[0]]
    return {"queries": queries}

def clean_and_shorten(title: str, word_limit: int = 2) -> str:
    title = emoji.replace_emoji(title, replace="")
    title = re.sub(r'#\S+', '', title)
    title = re.sub(r'[|@().\-]', '', title)
    return " ".join(title.strip().split()[:word_limit])


@song_request_router.get("/allSongs", response_model=AllSongResponseWrapper)
async def get_all_song_requests(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    start_time = time.time()

    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(401, "Invalid or expired token")

    user = await _get_user(db, user_data["sub"])
    if not user:
        raise HTTPException(404, "User not found")

    # Single-role app: a user may only ever see their own requests.
    query = (
        select(SongRequest)
        .options(joinedload(SongRequest.requester))
        .where(SongRequest.requesterId == user.id)
        .order_by(desc(SongRequest.createdAt))
    )

    result = await db.execute(query)
    song_requests = result.scalars().all()
 
    final_responses = []

    for req in song_requests:

        video_ids = req.videoIds.split(",") if req.videoIds else []
        requested_songs = []
        if req.trackMetadata:
            requested_songs = [
                Track(
                    **metadata,
                    playbackUrl=(
                        f"https://www.youtube.com/watch?v={metadata['trackId']}"
                        if metadata.get("sourceType") == "youtube"
                        else f"/tracks/assets/{metadata['trackId'].split(':', 1)[1]}/audio"
                    ),
                    mixEligible=True,
                )
                for metadata in req.trackMetadata
            ]
        else:
            legacy_details = [
                (req.videoTitle1, req.videoThumbnail1, req.videoArtist1),
                (req.videoTitle2, req.videoThumbnail2, req.videoArtist2),
            ]
            requested_songs = [
                Track(
                    trackId=video_id,
                    sourceType="youtube",
                    title=legacy_details[index][0],
                    artist=legacy_details[index][2],
                    artwork=legacy_details[index][1],
                    playbackUrl=f"https://www.youtube.com/watch?v={video_id}",
                    mixEligible=True,
                    license="YouTube",
                )
                for index, video_id in enumerate(video_ids[:2])
            ]

        mixed_audio_url = (
            f"{PUBLIC_API_BASE}/requests/audio/byRequestId/{req.id}"
            if req.mixedAudioPath else None
        )

        mix_title = " & ".join([
            clean_and_shorten(s.title)
            for s in requested_songs
        ])

        final_responses.append(
            SongRequestSimplifiedResponse(
                songRequestId=req.id,
                songStatus=req.status,
                mixedAudioUrl=mixed_audio_url,
                tipAmount=float(req.tipAmount or 0),
                mixSongTitle=mix_title,
                mixerType=req.mixer or "overlay",
                requestedBy=req.requester.userName if req.requester else "Unknown",
                requestedAt=req.createdAt.strftime('%Y-%m-%d %H:%M:%S') if req.createdAt else "",
                playedAt=req.playedAt.strftime('%Y-%m-%d %H:%M:%S') if req.playedAt else None,
                requestedSongs=requested_songs,
            )
        )

    logger.info(f"ðŸš€ /allSongs responded in {time.time() - start_time:.2f}s")

    return AllSongResponseWrapper(data=final_responses)

@song_request_router.get("/videosInfo")
async def get_video_info_for_multiple_ids(
    videoIds: str = Query(..., description="Comma-separated YouTube video IDs"),
    token: str = Depends(oauth2_scheme)
):
    start_time = time.time()
    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Split IDs
    id_list = [vid.strip() for vid in videoIds.split(",") if vid.strip()]
    if not id_list:
        raise HTTPException(status_code=400, detail="No valid video IDs provided")

    videos = await get_youtube_video_details(id_list)
    allowed_channels = authorized_channel_ids()
    results = [
        song_from_youtube_video(track_id, videos[track_id], allowed_channels)
        for track_id in id_list
        if track_id in videos
    ]

    duration = time.time() - start_time
    logger.info(f"ðŸš€ /videosInfo completed in {duration:.2f} seconds")

    return {"results": results}

@song_request_router.get("/suggestedSongs")
async def get_suggested_songs(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await _get_user(db, user_data["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Intentionally independent of the user's search history: otherwise the last
    # search reappears as a "fresh" list every time the app restarts.
    keyword = random.choice(SUGGESTED_SEEDS)

    tracks = await search_youtube_videos(keyword, limit=10)
    return {"seed": keyword, "results": tracks}


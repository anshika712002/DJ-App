import logging, os, asyncio, re, emoji, time
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Body,
    Query,
    BackgroundTasks
)
from audio_assets import ASSET_DIR
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import (
    select,
    desc,
    case
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from models import (
    AudioAsset,
    SongRequest,
    RequestStatus,
    User,
    UserSearchHistory,
    RoleMaster,
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

from websocket_manager import broadcast_song_request, broadcast_message

from schemas import (
    SongMixRequest,
    Track,
    SongRequestResponse,
    AllSongResponseWrapper,
    SongRequestSimplifiedResponse,
    StatusUpdateSchema
)

from datetime import datetime, timezone
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

async def _notify_clients(message: dict):
    """Best-effort realtime push; never let a dead socket break an API call."""
    try:
        await broadcast_message(message)
    except Exception as e:
        logger.warning("WebSocket broadcast failed: %s", e)


async def _get_user(db: AsyncSession, userName: str, roleName: str):
    stmt = (
        select(User)
        .join(RoleMaster, User.roleId == RoleMaster.id)
        .options(joinedload(User.roleObj))
        .where(User.userName == userName, RoleMaster.roleName == roleName)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

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

    user = await _get_user(db, user_data["sub"], user_data["role"])
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

    try:
        await broadcast_song_request(new_req)
    except Exception as e:
        logger.warning("WebSocket broadcast failed: %s", e)

    final_filename = f"request_{new_req.id}_{selected_mixer}.mp3"
    final_path = os.path.join(MIXED_AUDIO_FOLDER, final_filename)

    await _process_mixing_async(new_req.id, selected_mixer, audio_paths, final_path)

    return {
        "requestId": new_req.id,
        "message": f"Mix completed with '{selected_mixer}' mode.",
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
            req.status = RequestStatus.PENDING

            await session.flush()
            await session.commit()
            await session.refresh(req)

        logger.info(f"Mix saved for request {request_id}")
        logger.info(f"🚀 /mixed Audio takes {time.time() - start_time:.2f}s")

    except Exception as e:
        logger.error(f"Mixing failed: {e}")
        async with AsyncSessionLocal() as session:
            stmt = select(SongRequest).where(SongRequest.id == request_id)
            r = await session.execute(stmt)
            req = r.scalar_one_or_none()
            if req:
                req.status = RequestStatus.REJECTED
                await session.commit()

def _authorize_media_request(request: Request, token: Optional[str]) -> None:
    candidate = (
        token
        or request.headers.get("Authorization", "").replace("Bearer ", "")
        or request.query_params.get("token")
    )
    if not candidate or not decode_access_token(candidate):
        raise HTTPException(401, "Unauthorized")


@song_request_router.get("/audio/byRequestId/{request_id}")
async def download_mixed_audio_by_request(
    request_id: int,
    request: Request,
    token: Optional[str] = Query(
        None, description="JWT access token (alternative to the Authorization header)"
    ),
    db: AsyncSession = Depends(get_db),
):
    _authorize_media_request(request, token)

    result = await db.execute(select(SongRequest).where(SongRequest.id == request_id))
    song_request = result.scalar_one_or_none()
    if not song_request or not song_request.mixedAudioPath:
        raise HTTPException(404, "Mixed audio is not ready yet")

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
):
    _authorize_media_request(request, token)

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

    results = await search_youtube_videos(q, limit=10)
    await db.execute(
        insert(UserSearchHistory).values(
            userId=user_data["userId"],
            queryText=q,
        )
    )
    await db.commit()
    return {"results": results}

def clean_and_shorten(title: str, word_limit: int = 2) -> str:
    title = emoji.replace_emoji(title, replace="")
    title = re.sub(r'#\S+', '', title)
    title = re.sub(r'[|@().\-]', '', title)
    return " ".join(title.strip().split()[:word_limit])


@song_request_router.get("/allSongs", response_model=AllSongResponseWrapper)
async def get_all_song_requests(
    mineOnly: bool = Query(False),
    status: Optional[str] = Query(None, description="Filter by status: pending, accepted, rejected, playing, played"),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    start_time = time.time()

    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(401, "Invalid or expired token")

    user = await _get_user(db, user_data["sub"], user_data["role"])
    if not user:
        raise HTTPException(404, "User not found")

    role_name = user.roleObj.roleName if user.roleObj else None

    query = select(SongRequest).options(joinedload(SongRequest.requester))

    status_priority = case(
        (SongRequest.status == RequestStatus.PENDING, 1),
        else_=0
    )

    if status and role_name == "dj":
        try:
            status_enum = RequestStatus(status.lower())
            query = query.where(SongRequest.status == status_enum)
        except ValueError:
            raise HTTPException(400, "Invalid status filter")

        if status_enum in [RequestStatus.PLAYED, RequestStatus.PLAYING]:
            query = query.order_by(
                status_priority.asc(),
                desc(SongRequest.tipAmount),
                desc(SongRequest.playedAt)
            )
        else:
            query = query.order_by(
                status_priority.asc(),
                desc(SongRequest.tipAmount),
                desc(SongRequest.createdAt)
            )
    else:
        query = query.order_by(
            status_priority.asc(),
            desc(SongRequest.tipAmount),
            desc(SongRequest.createdAt)
        )

    if mineOnly:
        query = query.where(SongRequest.requesterId == user.id)

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
            f"{PUBLIC_API_BASE}/requests/audio/{req.mixedAudioPath}"
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
                restaurantName=req.restaurantName or (req.requester.restaurantName if req.requester else None)
            )
        )

    logger.info(f"🚀 /allSongs responded in {time.time() - start_time:.2f}s")

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
    logger.info(f"🚀 /videosInfo completed in {duration:.2f} seconds")

    return {"results": results}

@song_request_router.get("/suggestedSongs")
async def get_suggested_songs(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await _get_user(db, user_data["sub"], user_data["role"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Collect past queries or requests
    search_result = await db.execute(
        select(UserSearchHistory.queryText).where(UserSearchHistory.userId == user.id)
    )
    search_terms = [r[0] for r in search_result.fetchall()]

    keyword = search_terms[-1] if search_terms else "trending music"

    tracks = await search_youtube_videos(keyword, limit=10)
    return {"results": tracks}


@song_request_router.put("/accept/{request_id}")
async def accept_song_request(
    request_id: int,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    user_data = decode_access_token(token)
    if not user_data or user_data["role"] not in ["dj", "admin"]:
        raise HTTPException(status_code=403, detail="Only DJ or Admin can accept song requests")

    result = await db.execute(select(SongRequest).where(SongRequest.id == request_id))
    request_obj = result.scalar_one_or_none()
    if not request_obj:
        raise HTTPException(status_code=404, detail="Song request not found")

    request_obj.status = RequestStatus.ACCEPTED
    await db.commit()
    await _notify_clients({"action": "status_update", "data": {"songRequestId": request_id, "status": RequestStatus.ACCEPTED.value}})
    return {"status": "success", "message": f"Song request {request_id} accepted"}


@song_request_router.put("/reject/{request_id}")
async def reject_song_request(
    request_id: int,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    user_data = decode_access_token(token)
    if not user_data or user_data["role"] not in ["dj", "admin"]:
        raise HTTPException(status_code=403, detail="Only DJ or Admin can reject song requests")

    result = await db.execute(select(SongRequest).where(SongRequest.id == request_id))
    request_obj = result.scalar_one_or_none()
    if not request_obj:
        raise HTTPException(status_code=404, detail="Song request not found")

    request_obj.status = RequestStatus.REJECTED
    await db.commit()
    await _notify_clients({"action": "status_update", "data": {"songRequestId": request_id, "status": RequestStatus.REJECTED.value}})
    return {"status": "success", "message": f"Song request {request_id} rejected"}


@song_request_router.put("/updateStatus/{request_id}", response_model=SongRequestResponse)
async def update_song_status(
    request_id: int,
    status_data: StatusUpdateSchema,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if user_data.get("role") not in ["dj", "admin"]:
        raise HTTPException(status_code=403, detail="Only DJ or Admin can update song status")

    result = await db.execute(select(SongRequest).where(SongRequest.id == request_id))
    song_request = result.scalar_one_or_none()

    if not song_request:
        raise HTTPException(status_code=404, detail="Song request not found")

    if status_data.status in [RequestStatus.PLAYING, RequestStatus.PLAYED]:
        song_request.playedAt = datetime.now(timezone.utc)

    old_status = song_request.status
    song_request.status = status_data.status
    await db.commit()
    await db.refresh(song_request)

    await _notify_clients({
        "action": "status_update",
        "data": {
            "songRequestId": request_id,
            "status": status_data.status.value,
            "previousStatus": old_status.value if old_status else None
        }
    })

    logger.info(f"🎧 Updated song request {request_id} from {old_status} → {status_data.status}")

    return SongRequestResponse(
        id=song_request.id,
        songName=song_request.songName,
        songName2=song_request.songName2,
        status=song_request.status,
        mixedAudioUrl=f"{PUBLIC_API_BASE}/requests/audio/{os.path.basename(song_request.mixedAudioPath)}"
        if song_request.mixedAudioPath else None,
        tipAmount=song_request.tipAmount
    )

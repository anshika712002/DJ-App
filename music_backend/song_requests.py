import logging, os, asyncio, re, emoji, time, shutil
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
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import (
    select,
    desc,
    case
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from models import (
    SongRequest,
    RequestStatus,
    User,
    UserSearchHistory,
    RoleMaster,
    CachedSong
)
from database import get_db, AsyncSessionLocal
from auth_utils import decode_access_token
from typing import Optional, List
from fastapi.security import OAuth2PasswordBearer
from starlette.concurrency import run_in_threadpool
import httpx
import json

from process_audio import (
    mashup_tracks,
    overlay_tracks,
    download_audius_audio,
    crossfade_tracks,
    change_pitch,
    change_tempo,
    mix_audio,
    overlay_beat,
    search_audius_tracks,
    get_audius_track_details,
    AUDIUS_DOWNLOADS_FOLDER,
    MIXED_AUDIO_FOLDER
)

from websocket_manager import broadcast_song_request, broadcast_message

from schemas import (
    SongInfo,
    SongRequestResponse,
    AllSongResponseWrapper,
    SongRequestSimplifiedResponse,
    StatusUpdateSchema
)

from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

ORIGINAL_AUDIO_FOLDER = AUDIUS_DOWNLOADS_FOLDER

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
    "without-mixing"
}

AUDIUS_API_BASE = "https://discoveryprovider.audius.co/v1"


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

    elif mixing_mode == "without-mixing":
        shutil.copy(valid_tracks[0], final_path)

    else:
        raise ValueError("Invalid mixing mode")

    logger.info(f"Mix '{mixing_mode}' completed in {time.time() - start_time:.2f}s")


@song_request_router.post("/requestSong")
async def download_and_mix(
    background_tasks: BackgroundTasks,
    trackIds: List[str] = Body(..., embed=True),
    tipAmount: Optional[float] = Body(None),
    mixer: Optional[str] = Body(None),
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

    download_results = await asyncio.gather(
        *[download_audius_audio(t, ORIGINAL_AUDIO_FOLDER) for t in trackIds],
        return_exceptions=True,
    )
    failed_tracks = [
        tid for tid, res in zip(trackIds, download_results)
        if isinstance(res, BaseException)
    ]
    if failed_tracks:
        logger.warning("Audius download failed for tracks: %s", failed_tracks)
        raise HTTPException(
            400,
            "These tracks are not available for streaming/download: "
            + ", ".join(failed_tracks),
        )

    selected_mixer = mixer if mixer in VALID_MIXERS else "overlay"

    song_infos = await asyncio.gather(
        *[get_audius_track_details(t) for t in trackIds]
    )

    new_req = SongRequest(
        requesterId=user.id,
        status=RequestStatus.PENDING,
        videoIds=",".join(trackIds),
        songName=song_infos[0]["title"] if len(song_infos) > 0 else None,
        songName2=song_infos[1]["title"] if len(song_infos) > 1 else None,
        tipAmount=tipAmount,
        mixer=selected_mixer,
        videoTitle1=song_infos[0]["title"] if len(song_infos) > 0 else None,
        videoThumbnail1=song_infos[0]["thumbnail"] if len(song_infos) > 0 else None,
        videoArtist1=song_infos[0]["artistName"] if len(song_infos) > 0 else None,
        videoTitle2=song_infos[1]["title"] if len(song_infos) > 1 else None,
        videoThumbnail2=song_infos[1]["thumbnail"] if len(song_infos) > 1 else None,
        videoArtist2=song_infos[1]["artistName"] if len(song_infos) > 1 else None,
    )

    db.add(new_req)
    await db.commit()
    await db.refresh(new_req)

    try:
        await broadcast_song_request(new_req)
    except Exception as e:
        logger.warning("WebSocket broadcast failed: %s", e)

    final_filename = f"{'_'.join(trackIds)}_{selected_mixer}.mp3"
    final_path = os.path.join(MIXED_AUDIO_FOLDER, final_filename)

    asyncio.create_task(_process_mixing_async(new_req.id, selected_mixer, trackIds, final_path))

    return {
        "requestId": new_req.id,
        "message": f"Mix started with '{selected_mixer}' mode.",
        "downloadedTracks": song_infos

    }
    
async def _process_mixing_async(request_id, mixer, video_ids, final_path):
    try:
        valid_tracks = [
            os.path.join(ORIGINAL_AUDIO_FOLDER, vid + ".mp3")
            for vid in video_ids
        ]
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

@song_request_router.get("/audio/{filename}")
async def download_mixed_audio(filename: str, request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")

    if not token:
        token = request.query_params.get("token")

    if not token or not decode_access_token(token):
        raise HTTPException(401, "Unauthorized")

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

    return FileResponse(path=file_path, media_type="audio/mpeg")

@song_request_router.get("/searchSong")
async def search_song(
    q: str = Query(...),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):

    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(401, "Invalid token")

    await db.execute(
        insert(UserSearchHistory).values(
            userId=user_data["userId"], 
            queryText=q
        )
    )
    await db.commit()

    url = f"{AUDIUS_API_BASE}/tracks/search"
    params = {"query": q, "limit": 10}

    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            raise HTTPException(500, "Audius search failed")

    data = r.json().get("data", [])
    results = []

    for item in data:
        track_id = item.get("id")
        artwork = item.get("artwork") or {}
        mapped_artwork = {
            "small": artwork.get("150x150"),
            "medium": artwork.get("480x480"),
            "large": artwork.get("1000x1000"),
            "mirrors": artwork.get("mirrors", [])
        }

        song = {
            "videoId": track_id,
            "title": item.get("title"),
            "artistName": item.get("user", {}).get("name", ""),
            "thumbnail": artwork.get("150x150", ""),
            "artwork": mapped_artwork,
            "duration": item.get("duration"),
            "genre": item.get("genre"),
            "downloadAble": item.get("downloadable", False),
            "downloadUrl": item.get("download_url"),
            "license": item.get("license") or "all-rights-reserved",
            "streamUrl": f"{AUDIUS_API_BASE}/tracks/{track_id}/stream?app_name=djapp"
        }

        results.append(song)

        try:
            stmt = (
                insert(CachedSong)
                .values(
                    query=q,
                    videoId=song["videoId"],
                    title=song["title"],
                    thumbnail=song["thumbnail"],
                    artistName=song["artistName"],
                    duration=song["duration"],
                    genre=song["genre"],
                    downloadAble=song["downloadAble"],
                    license=song["license"],
                    artwork=song["artwork"]
                )
                .on_conflict_do_nothing(
                    index_elements=["query", "videoId"]
                )
            )
            await db.execute(stmt)

        except Exception as e:
            logger.warning(f"⚠️ Failed to cache song {track_id} → {e}")

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

        videoIds = req.videoIds.split(",") if req.videoIds else []

        requested_songs = []
        if len(videoIds) > 0:
            requested_songs.append(SongInfo(
                videoId=videoIds[0],
                title=req.videoTitle1,
                thumbnail=req.videoThumbnail1,
                artistName=req.videoArtist1
            ))
        if len(videoIds) > 1:
            requested_songs.append(SongInfo(
                videoId=videoIds[1],
                title=req.videoTitle2,
                thumbnail=req.videoThumbnail2,
                artistName=req.videoArtist2
            ))

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
    videoIds: str = Query(..., description="Comma-separated Audius track IDs"),
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

    results = []

    async with httpx.AsyncClient() as client:
        for track_id in id_list:
            url = f"https://discoveryprovider.audius.co/v1/tracks/{track_id}"
            params = {"app_name": "djapp"}

            response = await client.get(url, params=params)
            data = response.json()

            # Audius returns a dict, not a list
            track = data.get("data", None)
            if not track:
                continue
            artwork = track.get("artwork") or {}

            mapped_artwork = {
                "small": artwork.get("150x150"),
                "medium": artwork.get("480x480"),
                "large": artwork.get("1000x1000"),
                "mirrors": artwork.get("mirrors", [])
            }

            results.append({
                "videoId": track_id,
                "title": track.get("title"),
                "artistName": track.get("user", {}).get("name"),
                "artwork": mapped_artwork,
                "duration": track.get("duration"),
                "genre": track.get("genre"),
                "downloadAble": track.get("downloadable", False),
                "downloadUrl": track.get("download_url"),
                "streamUrl": track.get("stream_url"),
            })

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

    tracks = await search_audius_tracks(keyword, limit=10)
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

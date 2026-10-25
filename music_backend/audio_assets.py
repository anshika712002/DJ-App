import asyncio
import logging
import math
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
from pydub.exceptions import CouldntDecodeError
from pydub.utils import mediainfo_json
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from auth_utils import decode_access_token
from database import get_db
from models import AudioAsset
from schemas import Track


logger = logging.getLogger(__name__)
audio_asset_router = APIRouter(prefix="/tracks", tags=["Audio Assets"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
ASSET_DIR = Path(
    os.getenv("AUDIO_ASSET_DIR", Path(__file__).resolve().parent / "audio_assets")
).resolve()
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
ALLOWED_SUFFIXES = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
AssetSourceType = Literal["local", "licensed", "public_domain"]


def _user_id(token: str) -> int:
    payload = decode_access_token(token)
    if not payload or payload.get("tokenType") != "access":
        raise HTTPException(status_code=401, detail="Invalid access token.")
    user_id = payload.get("userId")
    if not isinstance(user_id, int):
        raise HTTPException(status_code=401, detail="Invalid access token.")
    return user_id


def _track(asset: AudioAsset) -> Track:
    return Track(
        trackId=f"asset:{asset.id}",
        sourceType=asset.sourceType,
        title=asset.title,
        artist=asset.artist,
        artwork=asset.artwork,
        duration=asset.duration,
        playbackUrl=f"/tracks/assets/{asset.id}/audio",
        mixEligible=True,
        license=asset.license,
        attribution=asset.attribution,
    )


@audio_asset_router.post("/assets", response_model=Track)
async def upload_audio_asset(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=255),
    artist: str | None = Form(default=None, max_length=255),
    source_type: AssetSourceType = Form(...),
    license: str = Form(..., min_length=1, max_length=255),
    attribution: str | None = Form(default=None, max_length=4000),
    rights_confirmed: bool = Form(...),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    owner_id = _user_id(token)
    if not rights_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirm that you have permission to upload and mix this audio.",
        )
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported audio file type. Upload MP3, WAV, OGG, FLAC, M4A, or AAC.",
        )
    if not title.strip() or not license.strip():
        raise HTTPException(status_code=422, detail="Title and license are required.")

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    asset_name = f"{uuid.uuid4().hex}{suffix}"
    final_path = ASSET_DIR / asset_name
    temporary_path = ASSET_DIR / f".{uuid.uuid4().hex}.upload"
    size = 0
    try:
        with temporary_path.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Audio upload exceeds 100 MB.")
                output.write(chunk)
        try:
            probe = await asyncio.to_thread(mediainfo_json, str(temporary_path))
        except (CouldntDecodeError, OSError, ValueError) as exc:
            raise HTTPException(
                status_code=415, detail="The uploaded file is not readable audio."
            ) from exc
        audio_streams = [
            stream for stream in probe.get("streams", [])
            if stream.get("codec_type") == "audio"
        ]
        if not audio_streams:
            raise HTTPException(status_code=415, detail="The uploaded file contains no audio.")
        duration_seconds = float(probe.get("format", {}).get("duration", 0))
        if duration_seconds <= 0:
            raise HTTPException(status_code=415, detail="Could not determine audio duration.")
        duration = math.ceil(duration_seconds)
        os.replace(temporary_path, final_path)

        asset = AudioAsset(
            ownerId=owner_id,
            sourceType=source_type,
            title=title.strip(),
            artist=artist.strip() if artist else None,
            duration=duration,
            filePath=str(final_path),
            license=license.strip(),
            attribution=attribution.strip() if attribution else None,
        )
        db.add(asset)
        await db.commit()
        await db.refresh(asset)
        return _track(asset)
    except HTTPException:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    except (SQLAlchemyError, OSError) as exc:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        try:
            await db.rollback()
        except (SQLAlchemyError, OSError) as rollback_error:
            logger.error(
                "Audio asset database rollback failed (%s).",
                type(rollback_error).__name__,
            )
        logger.error("Audio asset database operation failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please try again shortly.",
        ) from None
    except Exception:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        await db.rollback()
        logger.exception("Audio asset upload failed")
        raise HTTPException(status_code=500, detail="Audio upload could not be completed.")
    finally:
        await file.close()


@audio_asset_router.get("/assets", response_model=list[Track])
async def list_audio_assets(
    q: str = Query(default="", max_length=255),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    owner_id = _user_id(token)
    statement = select(AudioAsset).order_by(AudioAsset.createdAt.desc()).limit(100)
    statement = statement.where(
        or_(AudioAsset.sourceType != "local", AudioAsset.ownerId == owner_id)
    )
    if q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            AudioAsset.title.ilike(pattern) | AudioAsset.artist.ilike(pattern)
        )
    result = await db.execute(statement)
    return [_track(asset) for asset in result.scalars().all()]


@audio_asset_router.get("/assets/{asset_id}/audio")
async def get_audio_asset(
    asset_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    owner_id = _user_id(token)
    result = await db.execute(select(AudioAsset).where(AudioAsset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Audio asset not found.")
    if asset.sourceType == "local" and asset.ownerId != owner_id:
        raise HTTPException(status_code=404, detail="Audio asset not found.")
    path = Path(asset.filePath).resolve()
    if path.parent != ASSET_DIR or not path.is_file():
        logger.error("Audio asset %s points to a missing or unsafe file", asset_id)
        raise HTTPException(status_code=404, detail="Audio asset file is unavailable.")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)

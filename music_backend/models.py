from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime,
    UniqueConstraint, Text, Float, func,LargeBinary
)
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
from sqlalchemy import Enum as SAEnum
from enum import Enum
from sqlalchemy.dialects.postgresql import JSONB


def utcnow():
    """Naive UTC timestamp (avoids deprecated datetime.utcnow)."""
    return datetime.now().replace(microsecond=0)


class RequestStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PLAYING = "playing"
    PLAYED = "played"
    FAILED = "failed"
    COMPLETED = "completed"
    READY = "ready"


class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    location = Column(String(100), nullable=True)
    contactNumber = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    isActive = Column(Boolean, default=True)
    createdAt = Column(DateTime, default=func.now())
    updatedAt = Column(DateTime, default=func.now(), onupdate=func.now())

    roles = relationship("RoleMaster", back_populates="restaurant")


class RoleMaster(Base):
    __tablename__ = "role_master"

    id = Column(Integer, primary_key=True, index=True)
    roleName = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    isActive = Column(Boolean, default=True)
    createdAt = Column(DateTime, default=func.now())

    restaurantId = Column(Integer, ForeignKey("restaurants.id"), nullable=True)

    restaurant = relationship("Restaurant", back_populates="roles")
    users = relationship("User", back_populates="roleObj")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    userName = Column(String, nullable=False)
    email = Column(String, nullable=True)
    password = Column(String, nullable=False)
    roleId = Column(Integer, ForeignKey("role_master.id"), nullable=False)
    phone = Column(String, nullable=False)
    restaurantName = Column(String, nullable=True)
    restaurantId = Column(Integer, ForeignKey("restaurants.id"), nullable=True)

    roleObj = relationship("RoleMaster", back_populates="users")
    refreshTokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    searchHistory = relationship("UserSearchHistory", back_populates="user")

    __table_args__ = (
        UniqueConstraint("userName", "roleId", name="unique_userName_role"),
        UniqueConstraint("email", "roleId", name="unique_email_role"),
        UniqueConstraint("phone", "roleId", name="unique_phone_role"),
    )

class CachedSong(Base):
    __tablename__ = "cached_songs"

    id = Column(Integer, primary_key=True, index=True)
    query = Column(String(255), nullable=False, index=True)  # user search keyword
    videoId = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    thumbnail = Column(String(255), nullable=True)
    channelName = Column(String(255), nullable=True)
    createdAt = Column(DateTime, default=func.now())
    artistName = Column(String(255), nullable=True)
    duration = Column(Integer, nullable=True)
    genre = Column(String(100), nullable=True)
    downloadAble = Column(Boolean, nullable=True)
    license = Column(String(255), nullable=True)
    artwork = Column(JSONB, nullable=True)
    
    __table_args__ = (
        UniqueConstraint("query", "videoId", name="unique_query_video"),
    )

class DownloadedAudio(Base):
    __tablename__ = "downloaded_audios"

    id = Column(Integer, primary_key=True, index=True)
    videoId = Column(String(50), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    audioData = Column(LargeBinary, nullable=False)
    filePath = Column(String(255), nullable=True)
    createdAt = Column(DateTime, default=func.now())


class AudioAsset(Base):
    __tablename__ = "audio_assets"

    id = Column(Integer, primary_key=True, index=True)
    ownerId = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sourceType = Column(String(32), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    artist = Column(String(255), nullable=True)
    artwork = Column(String(2048), nullable=True)
    duration = Column(Integer, nullable=False)
    filePath = Column(String(512), nullable=False, unique=True)
    license = Column(String(255), nullable=False)
    attribution = Column(Text, nullable=True)
    createdAt = Column(DateTime, default=func.now(), nullable=False)

    owner = relationship("User")


class SongRequest(Base):
    __tablename__ = "song_requests"

    id = Column(Integer, primary_key=True, index=True)
    songName = Column(String, nullable=True)
    songName2 = Column(String, nullable=True)
    tipAmount = Column(Float, nullable=True)
    requesterId = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    status = Column(
        SAEnum(RequestStatus, name="requeststatus", values_callable=lambda enum: [e.value for e in enum]),
        nullable=False,
        default=RequestStatus.PENDING.value,
        index=True
    )

    mixedAudioPath = Column(String, nullable=True)
    mixedAudioData = Column(LargeBinary, nullable=True)
    videoIds = Column(String, nullable=True)
    trackMetadata = Column(JSONB, nullable=True)
    mixer = Column(String, nullable=True, default="overlay")
    createdAt = Column(DateTime, default=utcnow, index=True)
    playedAt = Column(DateTime(timezone=True), nullable=True)

    videoTitle1 = Column(String, nullable=True)
    videoThumbnail1 = Column(String, nullable=True)
    videoArtist1 = Column(String, nullable=True)
    videoTitle2 = Column(String, nullable=True)
    videoThumbnail2 = Column(String, nullable=True)
    videoArtist2 = Column(String, nullable=True)

    restaurantName = Column(String, nullable=True)

    requester = relationship("User", foreign_keys=[requesterId])


class UserSearchHistory(Base):
    __tablename__ = "user_search_history"

    id = Column(Integer, primary_key=True, index=True)
    userId = Column(Integer, ForeignKey("users.id"), nullable=True)
    queryText = Column(Text, nullable=False)
    timestamp = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="searchHistory")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String, unique=True, nullable=False)
    userId = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(Text, nullable=False)
    createdAt = Column(DateTime, default=utcnow)
    expiresAt = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)

    user = relationship("User", back_populates="refreshTokens")

from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional, List
from enum import Enum
from datetime import datetime


class UserCreate(BaseModel):
    userName: str
    email: Optional[EmailStr] = None
    password: str
    phone: str
    role: str
    restaurantName: Optional[str] = None


class UserLogin(BaseModel):
    identifier: str  # phone or email
    password: str
    role: str


class UserSignupResponse(BaseModel):
    id: int
    userName: str
    phone: str
    email: Optional[EmailStr] = None
    roleId: Optional[int] = None
    role: Optional[str] = None
    restaurantName: Optional[str] = None


class UserLoginResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str
    userName: str
    phone: str
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    restaurantName: Optional[str] = None

class TokenRefreshResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str


class UserTokenData(BaseModel):
    sub: str
    role: str
    userId: int
    exp: Optional[int] = None
    jti: Optional[str] = None
    tokenType: Optional[str] = None


class Track(BaseModel):
    trackId: str
    sourceType: Literal["youtube", "local", "licensed", "public_domain"]
    title: Optional[str] = None
    artist: Optional[str] = None
    artwork: Optional[str] = None
    duration: Optional[int] = None
    playbackUrl: Optional[str] = None
    mixEligible: bool = False
    license: Optional[str] = None
    attribution: Optional[str] = None


class TrackReference(BaseModel):
    trackId: str
    sourceType: Literal["youtube", "local", "licensed", "public_domain"]


class SongMixRequest(BaseModel):
    tracks: List[TrackReference]
    tipAmount: Optional[float] = None
    mixer: Optional[str] = None


class StatusEnum(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    playing = "playing"
    played = "played"

class StatusUpdateSchema(BaseModel):
    status: StatusEnum

class SongRequestResponse(BaseModel):
    id: int
    songName: Optional[str]
    songName2: Optional[str]
    status: Optional[str]
    mixedAudioUrl: Optional[str]
    tipAmount: Optional[float]

class SongRequestSimplifiedResponse(BaseModel):
    songRequestId: int
    songStatus: str
    mixedAudioUrl: Optional[str]
    tipAmount: float
    mixSongTitle: Optional[str]
    mixerType: str
    requestedBy: str
    requestedAt: Optional[str]
    playedAt: Optional[str]
    requestedSongs: List[Track]
    restaurantName: Optional[str]

class AllSongResponseWrapper(BaseModel):
    data: List[SongRequestSimplifiedResponse]

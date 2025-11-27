from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
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


class SongInfo(BaseModel):
    videoId: str
    title: Optional[str]
    thumbnail: Optional[str]
    artistName: Optional[str]

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
    requestedSongs: List[SongInfo]
    restaurantName: Optional[str]

class AllSongResponseWrapper(BaseModel):
    data: List[SongRequestSimplifiedResponse]

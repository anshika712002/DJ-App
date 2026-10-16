from pydantic import BaseModel, EmailStr
from typing import Literal, Optional, List


class UserCreate(BaseModel):
    userName: str
    email: Optional[EmailStr] = None
    password: str
    phone: str
    # Accepted for backward compatibility but ignored: every new account is a
    # plain "user" (single-role application).
    role: Optional[str] = None


class UserLogin(BaseModel):
    identifier: str  # phone or email
    password: str
    # Optional: when omitted, the account is looked up by identifier alone.
    role: Optional[str] = None


class UserSignupResponse(BaseModel):
    id: int
    userName: str
    phone: str
    email: Optional[EmailStr] = None
    roleId: Optional[int] = None
    role: Optional[str] = None


class UserLoginResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str
    userName: str
    phone: str
    email: Optional[EmailStr] = None
    role: Optional[str] = None

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

class AllSongResponseWrapper(BaseModel):
    data: List[SongRequestSimplifiedResponse]

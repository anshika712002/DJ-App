from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import User, RoleMaster
from auth_utils import decode_access_token
from pydantic import BaseModel
from utils import format_response

user_router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class UserProfile(BaseModel):
    userName: str
    email: str
    role: str | None = None
    restaurantName: str | None = None


# ✅ Fetch user using userId from JWT
async def _get_user(db: AsyncSession, userId: int):
    result = await db.execute(
        select(User, RoleMaster.roleName)
        .join(RoleMaster, User.roleId == RoleMaster.id)
        .where(User.id == userId)
    )
    return result.first()


@user_router.get("/profile")
async def get_profile(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    user_data = decode_access_token(token)
    if not user_data:
        return format_response(401, "Invalid or expired token", None)

    userId = user_data.get("userId")
    if not userId:
        return format_response(401, "Invalid token payload", None)

    user_record = await _get_user(db, userId)
    if not user_record:
        return format_response(404, "User not found", None)

    user, roleName = user_record

    return format_response(200, "success", {
        "id": user.id,
        "userName": user.userName,
        "email": user.email,
        "role": roleName,
        "phone": user.phone,
        "restaurantName": user.restaurantName
    })


@user_router.put("/profile")
async def update_profile(
    updated_data: UserProfile,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    userId = user_data.get("userId")
    if not userId:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user_record = await _get_user(db, userId)
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")

    user, _ = user_record

    user.userName = updated_data.userName
    user.email = updated_data.email
    user.restaurantName = updated_data.restaurantName

    await db.commit()
    await db.refresh(user)

    return format_response(200, "Profile updated successfully", {
        "id": user.id,
        "userName": user.userName,
        "email": user.email,
        "restaurantName": user.restaurantName
    })


@user_router.delete("/profile")
async def delete_profile(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    user_data = decode_access_token(token)
    if not user_data:
        return format_response(401, "Invalid or expired token", None)

    userId = user_data.get("userId")
    if not userId:
        return format_response(401, "Invalid token payload", None)

    user_record = await _get_user(db, userId)
    if not user_record:
        return format_response(404, "User not found", None)

    user, _ = user_record
    await db.delete(user)
    await db.commit()

    return format_response(200, "Profile deleted successfully", None)

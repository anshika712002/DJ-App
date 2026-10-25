from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from database import get_db
from models import User, RefreshToken, RoleMaster
from auth_utils import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    create_refresh_token,
    REFRESH_TOKEN_EXPIRE_DAYS
)
from schemas import UserCreate, UserLogin, UserLoginResponse, UserSignupResponse, TokenRefreshResponse, UserTokenData
from utils import format_response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import or_, func
import time
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

auth_router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@auth_router.post("/signup")
async def signup(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    start_time = time.time()
    # Single-role application: every new account is an ordinary user. Any role
    # sent by an older client is ignored (the field is optional now).
    role_name = "user"
    try:
        logger.info("📥 Signup request received for userName: %s", user_data.userName)

        role_result = await db.execute(
            select(RoleMaster).where(RoleMaster.roleName == role_name)
        )
        role_obj = role_result.scalars().first()

        if not role_obj:
            return format_response(400, "Signup is unavailable: user role not configured", {"role": role_name})

        role_id = role_obj.id

        result = await db.execute(
            select(User).filter(User.userName == user_data.userName, User.roleId == role_id)
        )
        if result.scalars().first():
            return format_response(400, "User already registered", {"userName": user_data.userName})

        result = await db.execute(
            select(User).filter(User.phone == user_data.phone, User.roleId == role_id)
        )
        if result.scalars().first():
            return format_response(400, "Phone number already registered", {"phone": user_data.phone})

        if user_data.email:
            result = await db.execute(
                select(User).filter(func.lower(User.email) == func.lower(user_data.email), User.roleId == role_id)
            )
            if result.scalars().first():
                return format_response(400, "Email already registered", {"email": user_data.email})

        new_user = User(
            userName=user_data.userName,
            email=user_data.email,
            phone=user_data.phone,
            password=hash_password(user_data.password),
            roleId=role_id,
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        access_token = create_access_token({"sub": new_user.userName, "role": role_name, "userId": new_user.id})

        return format_response(
            200,
            "success",
            UserSignupResponse(
                id=new_user.id,
                userName=new_user.userName,
                phone=new_user.phone,
                email=new_user.email,
                roleId=new_user.roleId,
                role=role_name,
            ).dict()
        )

    except (SQLAlchemyError, OSError) as exc:
        logger.error("Signup database operation failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please try again shortly.",
        ) from None
    except Exception:
        logger.exception("Signup failed")
        return format_response(
            500, "Internal Server Error", {"error": "Unexpected server error"}
        )

    finally:
        duration = time.time() - start_time
        logger.info("Signup request finished in %.2f seconds", duration)


@auth_router.post("/login")
async def login(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    start_time = time.time()
    try:
        logger.info("📥 Login request received for identifier: %s", user_data.identifier)

        filters = [
            or_(
                func.lower(User.email) == func.lower(user_data.identifier),
                User.phone == user_data.identifier
            )
        ]
        # Role is optional in the single-role app. If a legacy client still
        # sends one, honour it; otherwise match any role (newest account wins).
        if user_data.role:
            filters.append(RoleMaster.roleName == user_data.role)

        stmt = (
            select(User, RoleMaster)
            .join(RoleMaster, User.roleId == RoleMaster.id)
            .filter(*filters)
            .order_by(User.id.desc())
        )

        result = await db.execute(stmt)
        user_with_role = result.first()

        if not user_with_role:
            return format_response(404, "User not found", {"identifier": user_data.identifier})

        user, role = user_with_role

        if not verify_password(user_data.password, user.password):
            return format_response(401, "Invalid credentials", {"identifier": user_data.identifier})

        token_data = {
            "sub": user.userName,
            "role": role.roleName,
            "userId": user.id
        }

        accessToken = create_access_token(token_data)
        refreshToken = create_refresh_token(token_data)

        refresh_payload = decode_access_token(refreshToken)
        new_refresh_entry = RefreshToken(
            jti=refresh_payload.get("jti"),
            userId=user.id,
            token=refreshToken,
            expiresAt=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
            revoked=False
        )
        db.add(new_refresh_entry)
        await db.commit()

        logger.info("🔑 Login successful | userId=%s | role=%s", user.id, role.roleName)

        return format_response(
            200,
            "success",
            UserLoginResponse(
                accessToken=accessToken,
                refreshToken=refreshToken,
                tokenType="bearer",
                userName=user.userName,
                phone=user.phone,
                email=user.email,
                role=role.roleName,
            ).dict()
        )

    except (SQLAlchemyError, OSError) as exc:
        logger.error("Login database operation failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please try again shortly.",
        ) from None
    except Exception:
        logger.exception("Login failed")
        return format_response(
            500,
            "Login failed due to server error",
            {"error": "Unexpected server error"},
        )

    finally:
        duration = time.time() - start_time
        logger.info("Login request finished in %.2f seconds", duration)


@auth_router.get("/protected")
async def protected_route(token: str = Depends(oauth2_scheme)):
    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    mapped_user_data = {
        "sub": user_data.get("sub"),
        "role": user_data.get("role"),
        "userId": user_data.get("userId"),
        "exp": user_data.get("exp"),
        "jti": user_data.get("jti"),
        "tokenType": user_data.get("tokenType")
    }

    return {
        "message": "You have access!",
        "user": mapped_user_data
    }



@auth_router.post("/refresh")
async def refresh_token(
    refresh_token: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    user_data = decode_access_token(refresh_token)

    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    if user_data.get("tokenType") != "refresh":
        raise HTTPException(status_code=400, detail="Access token not allowed here")

    jti = user_data.get("jti")

    stmt = select(RefreshToken).filter(RefreshToken.jti == jti, RefreshToken.revoked == False)
    result = await db.execute(stmt)
    stored_token = result.scalars().first()

    if not stored_token:
        raise HTTPException(status_code=401, detail="Refresh token is not valid or already revoked")

    stored_token.revoked = True
    await db.commit()

    new_access_token = create_access_token({
        "sub": user_data["sub"],
        "role": user_data["role"],
        "userId": user_data["userId"]
    })

    new_refresh_token = create_refresh_token({
        "sub": user_data["sub"],
        "role": user_data["role"],
        "userId": user_data["userId"]
    })

    new_refresh_payload = decode_access_token(new_refresh_token)

    new_token_entry = RefreshToken(
        jti=new_refresh_payload.get("jti"),
        userId=user_data["userId"],
        token=new_refresh_token,
        expiresAt=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        revoked=False
    )
    db.add(new_token_entry)
    await db.commit()

    logger.info("🔄 Refresh issued new refresh token jti=%s for userId=%s", new_refresh_payload.get("jti"), user_data["userId"])

    return format_response(
        200,
        "success",
        TokenRefreshResponse(
            accessToken=new_access_token,
            refreshToken=new_refresh_token,
            tokenType="bearer"
        ).dict()
    )

import sys

# Windows consoles/pipes default to cp1252; the app logs emoji/UTF-8.
# Reconfigure before any module prints so startup cannot crash with
# UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
import os
import logging
# from sqlalchemy.ext.asyncio import AsyncSession
# from database import get_db
from auth import auth_router
from database import async_engine, wait_for_database
from user import user_router
from song_requests import song_request_router 
from audio_assets import audio_asset_router
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from database import AsyncSessionLocal

logger = logging.getLogger(__name__)

print("✅ FastAPI server is starting...") 

REQUIRED_TABLES = (
    "users", "role_master", "song_requests",
    "cached_songs", "downloaded_audios", "refresh_tokens", "user_search_history",
    "audio_assets",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await wait_for_database()
        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                text("select tablename from pg_tables where schemaname='public'")
            )
            existing = {r[0] for r in rows}
        missing = [t for t in REQUIRED_TABLES if t not in existing]
        if missing:
            logger.error("Database schema is incomplete; missing tables: %s", missing)
            raise RuntimeError(
                "Database schema is incomplete. Review migrations before starting the API."
            )
        logger.info("Database connected and schema verified.")
        yield
    finally:
        await async_engine.dispose()


app = FastAPI(lifespan=lifespan)

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    # No cookies are used (auth is a Bearer header), so credentials stay off
    # and the wildcard origin is safe. Explicit headers are required because
    # the CORS spec does not apply "*" to the Authorization header.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

# The queue feed carried requester names, tips and song titles for the DJ role.
# The app is single-role now, so the realtime queue socket was removed;
# clients poll /requests/allSongs (scoped to their own requests) instead.

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(user_router, prefix="/user", tags=["User Management"])
app.include_router(song_request_router, prefix="/requests", tags=["Song Requests"])
app.include_router(audio_asset_router)

@app.get("/")
def home():
    return {"message": "Welcome to Music App Backend!"}


@app.get("/health/live", include_in_schema=False)
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
async def health_ready():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("Database readiness check failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok", "database": "ok"}

# @app.get("/auth/protected")
# async def protected_route(
#     query: str =  Query(None),
#     token: str = Depends(oauth2_scheme),
#     authorization: str = Header(None)
# ):
#     return {
#         "message": "You have access!", 
#         "query": query,
#         "token": token,
#         "authorization_header":authorization
#     }

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Music App Backend",
        version="1.0.0",
        description="Backend APIs",
        routes=app.routes,
    )

    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
    openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT"
    }

    for path in openapi_schema["paths"].values():
        for method in path:
            path[method]["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return openapi_schema

app.openapi = custom_openapi

if __name__ == "__main__":
    print("✅ Running Uvicorn...") 
    uvicorn.run(app, host="0.0.0.0", port=8085, reload=True)

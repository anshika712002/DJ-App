import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

# Load .env from the project root (and music_backend/ if present) so the app
# works no matter whether it is started from the repo root or music_backend/.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing. Check your .env file.")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

ECHO_SQL = os.getenv("ECHO_SQL", "false").lower() in ("1", "true", "yes")

async_engine = create_async_engine(
    DATABASE_URL,
    echo=ECHO_SQL,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={"timeout": 5},
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


class DatabaseUnavailableError(RuntimeError):
    pass


async def wait_for_database(
    max_attempts: int = 8,
    initial_delay_seconds: float = 0.5,
    max_delay_seconds: float = 3.0,
) -> None:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")
    if initial_delay_seconds < 0 or max_delay_seconds < 0:
        raise ValueError("Database retry delays cannot be negative.")

    delay = initial_delay_seconds
    for attempt in range(1, max_attempts + 1):
        try:
            async with async_engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError) as exc:
            if attempt == max_attempts:
                logger.error(
                    "Database connection failed after %d attempts (%s). "
                    "Verify PostgreSQL is running and DATABASE_URL targets "
                    "the intended database.",
                    max_attempts,
                    type(exc).__name__,
                )
                raise DatabaseUnavailableError(
                    f"Database unavailable after {max_attempts} connection attempts."
                ) from None
            logger.warning(
                "Database connection attempt %d/%d failed (%s); retrying.",
                attempt,
                max_attempts,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay_seconds)
        else:
            logger.info("Database connection verified with SELECT 1.")
            return


async def get_db():
    """FastAPI dependency: one AsyncSession per request, rollback on error."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                yield session
            except Exception:
                try:
                    await session.rollback()
                except (SQLAlchemyError, OSError) as rollback_error:
                    logger.error(
                        "Database rollback failed (%s).",
                        type(rollback_error).__name__,
                    )
                raise
    except (SQLAlchemyError, OSError) as exc:
        logger.error("Database request failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please try again shortly.",
        ) from None


if __name__ == "__main__":
    import sys

    async def _verify_database():
        try:
            await wait_for_database()
        finally:
            await async_engine.dispose()

    try:
        asyncio.run(_verify_database())
    except DatabaseUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None

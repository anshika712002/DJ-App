import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import urlopen


EXPECTED_ROOT = Path(
    r"C:\Users\Anshika Tyagi\OneDrive\Desktop\DJ App\DJ-App"
)
EXPECTED_HOST = "dpg-db967oqvcj2c73ahq3hg-a.oregon-postgres.render.com"
EXPECTED_DATABASE = "dj_app_staging_pg"
EXPECTED_TABLES = {
    "users",
    "role_master",
    "song_requests",
    "cached_songs",
    "downloaded_audios",
    "refresh_tokens",
    "user_search_history",
    "audio_assets",
}
GUARD_PATH = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "DJ-App"
    / "render-staging-db-migration-attempted"
)


def stop(message: str) -> int:
    print(f"STOPPED: {message}")
    return 1


def read_hidden_url() -> str:
    if os.name != "nt" or not sys.stdin.isatty():
        raise OSError("A Windows terminal with interactive input is required.")

    import msvcrt

    sys.stderr.write("External URL for dj-app-staging-pg (hidden input): ")
    sys.stderr.flush()
    characters = []
    while True:
        character = msvcrt.getwch()
        if character in ("\r", "\n"):
            sys.stderr.write("\n")
            sys.stderr.flush()
            return "".join(characters).strip()
        if character == "\003":
            raise KeyboardInterrupt
        if character == "\b":
            if characters:
                characters.pop()
            continue
        if character in ("\x00", "\xe0"):
            msvcrt.getwch()
            continue
        characters.append(character)


def main() -> int:
    root = Path(__file__).resolve().parent
    if root != EXPECTED_ROOT or not (root / ".git").exists():
        return stop("Script is not at the expected DJ-App repository root.")

    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        return stop("Repository virtual-environment Python is missing.")

    dependencies = subprocess.run(
        [str(python), "-c", "import alembic, sqlalchemy, asyncpg"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if dependencies.returncode:
        return stop("Required Alembic or PostgreSQL dependencies are unavailable.")

    process_check = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "$p = Get-CimInstance Win32_Process | Where-Object { "
            "$_.Name -match '^python(w)?\\.exe$' -and "
            "$_.CommandLine -match 'alembic.*upgrade.*head' }; "
            "if ($p) { exit 1 } else { exit 0 }",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if process_check.returncode:
        return stop("Could not confirm that no Alembic upgrade process is running.")

    if not os.environ.get("LOCALAPPDATA"):
        return stop("LOCALAPPDATA is unavailable; cannot use a safe attempt guard.")
    if GUARD_PATH.exists():
        return stop("The one-attempt guard already exists. Do not retry automatically.")

    try:
        database_url = read_hidden_url()
    except OSError:
        return stop("Hidden terminal input is unavailable; no migration was run.")
    if not database_url:
        return stop("No URL was entered; no migration was run.")

    try:
        parsed = urlsplit(database_url)
        valid_scheme = parsed.scheme in {
            "postgres",
            "postgresql",
            "postgresql+asyncpg",
        }
        valid_target = (
            valid_scheme
            and parsed.hostname == EXPECTED_HOST
            and parsed.path.lstrip("/") == EXPECTED_DATABASE
        )
    except ValueError:
        valid_target = False
    if not valid_target:
        return stop(
            "URL did not match the PostgreSQL scheme, exact Render Oregon host, "
            "and staging database name. No migration was run."
        )

    try:
        GUARD_PATH.parent.mkdir(parents=True, exist_ok=True)
        with GUARD_PATH.open("x", encoding="ascii") as guard:
            guard.write("STAGING_MIGRATION_ATTEMPT_STARTED")
    except FileExistsError:
        return stop("The one-attempt guard already exists; no migration was run.")
    except OSError:
        return stop("Could not create the one-attempt guard; no migration was run.")

    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    environment["PYTHON_DOTENV_DISABLED"] = "1"
    print("Staging host and database validated. Running Alembic upgrade once.")
    try:
        migration = subprocess.run(
            [str(python), "-m", "alembic", "upgrade", "head"],
            cwd=root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        return stop("Could not start Alembic. The attempt guard remains; do not retry.")
    if migration.returncode:
        return stop(
            f"Alembic failed with exit code {migration.returncode}. "
            "The attempt guard remains; do not retry automatically."
        )
    print("ALEMBIC_UPGRADE=SUCCEEDED")

    verification_code = """
import asyncio, os, sys
from sqlalchemy.ext.asyncio import create_async_engine

url = os.environ["DATABASE_URL"]
if url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
expected = {
    "users", "role_master", "song_requests", "cached_songs",
    "downloaded_audios", "refresh_tokens", "user_search_history",
    "audio_assets",
}

async def verify():
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            revision = (
                await connection.exec_driver_sql(
                    "SELECT version_num FROM alembic_version"
                )
            ).scalar_one_or_none()
            rows = await connection.exec_driver_sql(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            tables = {row[0] for row in rows}
        missing = sorted(expected - tables)
        print("ALEMBIC_REVISION=" + str(revision))
        print("EXPECTED_TABLES_PRESENT=" + str(not missing))
        print("MISSING_TABLES=" + ",".join(missing))
        return not missing
    finally:
        await engine.dispose()

try:
    success = asyncio.run(verify())
    sys.exit(0 if success else 2)
except Exception as error:
    print("SCHEMA_VERIFICATION_ERROR=" + type(error).__name__)
    sys.exit(3)
"""
    verification = subprocess.run(
        [str(python), "-c", verification_code],
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    for line in verification.stdout.splitlines():
        if line.startswith(
            (
                "ALEMBIC_REVISION=",
                "EXPECTED_TABLES_PRESENT=",
                "MISSING_TABLES=",
                "SCHEMA_VERIFICATION_ERROR=",
            )
        ):
            print(line)
    if verification.returncode:
        return stop(
            "Migration succeeded but verification failed. "
            "The attempt guard remains; do not retry automatically."
        )

    for path in ("/health/live", "/health/ready"):
        try:
            with urlopen(
                "https://dj-app-api-staging.onrender.com" + path,
                timeout=90,
            ) as response:
                print(f"{path} HTTP={response.status}")
        except Exception as error:
            print(f"{path} REQUEST_FAILED={type(error).__name__}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped by user. If the attempt guard exists, do not retry.")
        raise SystemExit(130)

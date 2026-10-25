import argparse
import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "music_backend"
sys.path.insert(0, str(BACKEND_DIR))

import database


PG_ROOT = Path(
    os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
) / "pgsql17"
PG_HOME = PG_ROOT / "pgsql"
DATA_DIR = PG_ROOT / "data"
BIN_DIR = PG_HOME / "bin"
POSTGRES_EXE = BIN_DIR / "postgres.exe"
PG_CTL = BIN_DIR / "pg_ctl.exe"
PG_ISREADY = BIN_DIR / "pg_isready.exe"
START_TIMEOUT_SECONDS = 45

logger = logging.getLogger("djapp.startup")


class StartupError(RuntimeError):
    pass


def configure_logging() -> None:
    log_directory = PG_ROOT / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_directory / "djapp-startup.log", encoding="utf-8"),
        ],
    )


def validate_database_target() -> int:
    try:
        url = make_url(database.DATABASE_URL)
    except (SQLAlchemyError, TypeError, ValueError):
        raise StartupError("DATABASE_URL could not be parsed; its value was not logged.") from None

    if (
        url.database != "djapp_db"
        or url.username != "djapp"
        or url.host not in {"127.0.0.1", "localhost"}
    ):
        raise StartupError(
            "The local launcher requires DATABASE_URL to target the existing "
            "djapp_db database with role djapp on this computer."
        )

    configured_port = url.port or 5432
    if not 1 <= configured_port <= 65535:
        raise StartupError("DATABASE_URL contains an invalid PostgreSQL port.")
    return configured_port


def run_safely(
    command: list[str],
    *,
    timeout: int = 15,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise StartupError(
            f"Could not run {Path(command[0]).name} ({type(exc).__name__})."
        ) from None


def postgres_setting(name: str) -> str:
    result = run_safely(
        [str(POSTGRES_EXE), "-D", str(DATA_DIR), "-C", name],
        cwd=PG_ROOT,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise StartupError(
            f"Could not read PostgreSQL setting '{name}' from the selected cluster."
        )
    return result.stdout.strip().splitlines()[-1].strip()


def canonical_path(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(path)).rstrip("\\/")


def listener_process_ids(port: int) -> set[int]:
    result = run_safely(["netstat.exe", "-ano", "-p", "tcp"])
    listeners: set[int] = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0].upper() != "TCP":
            continue
        if fields[3].upper() != "LISTENING":
            continue
        try:
            local_port = int(fields[1].rsplit(":", 1)[1])
            process_id = int(fields[4])
        except (IndexError, ValueError):
            continue
        if local_port == port:
            listeners.add(process_id)
    return listeners


def process_data_directory(process_id: int) -> str | None:
    command = (
        f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={process_id}'; "
        "if ($p -and $p.Name -eq 'postgres.exe') { "
        "$c=$p.CommandLine; "
        "if ($c -match '(?i)(?:^|\\s)-D\\s+\"([^\"]+)\"') "
        "{ [Console]::Out.WriteLine($Matches[1]) } "
        "elseif ($c -match '(?i)(?:^|\\s)-D\\s+([^\\s]+)') "
        "{ [Console]::Out.WriteLine($Matches[1]) } "
        "else { exit 2 } } else { exit 2 }"
    )
    result = run_safely(
        ["powershell.exe", "-NoProfile", "-Command", command],
        timeout=10,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip().splitlines()[-1].strip()


def assert_port_belongs_to_cluster(port: int) -> set[int]:
    process_ids = listener_process_ids(port)
    expected_directory = canonical_path(DATA_DIR)
    for process_id in process_ids:
        data_directory = process_data_directory(process_id)
        if data_directory is None:
            raise StartupError(
                f"Port {port} is occupied by an unrecognized process "
                f"(PID {process_id}); PostgreSQL was not started."
            )
        if canonical_path(data_directory) != expected_directory:
            raise StartupError(
                f"Port {port} belongs to another PostgreSQL data directory; "
                "that instance was left running."
            )
    return process_ids


def postgres_is_ready(port: int) -> bool:
    result = run_safely(
        [str(PG_ISREADY), "-q", "-h", "127.0.0.1", "-p", str(port), "-t", "2"],
        timeout=5,
    )
    return result.returncode == 0


def ensure_postgres_started(expected_port: int) -> None:
    if os.name != "nt":
        raise StartupError("This PostgreSQL launcher is for the local Windows development cluster.")
    if not PG_ROOT.is_dir():
        raise StartupError("PostgreSQL 17 was not found under %LOCALAPPDATA%\\pgsql17.")
    for executable in (POSTGRES_EXE, PG_CTL, PG_ISREADY):
        if not executable.is_file():
            raise StartupError(f"Required PostgreSQL executable is missing: {executable.name}.")
    version_file = DATA_DIR / "PG_VERSION"
    if not version_file.is_file() or version_file.read_text(encoding="ascii").strip() != "17":
        raise StartupError("The selected existing data directory is not a PostgreSQL 17 cluster.")

    configured_data_directory = postgres_setting("data_directory")
    if canonical_path(configured_data_directory) != canonical_path(DATA_DIR):
        raise StartupError(
            "PostgreSQL configuration points to a different data directory; "
            "the selected cluster was not started."
        )

    try:
        cluster_port = int(postgres_setting("port"))
    except ValueError:
        raise StartupError("The selected PostgreSQL cluster has an invalid port.") from None
    if cluster_port != expected_port:
        raise StartupError(
            "DATABASE_URL's port does not match the selected PostgreSQL cluster."
        )

    listen_addresses = {
        address.strip().strip("'\"")
        for address in postgres_setting("listen_addresses").split(",")
    }
    if "127.0.0.1" not in listen_addresses:
        raise StartupError(
            "PostgreSQL is not configured to listen on 127.0.0.1; "
            "network exposure was not changed."
        )

    status = run_safely([str(PG_CTL), "status", "-D", str(DATA_DIR)], cwd=PG_ROOT)
    if status.returncode not in {0, 3}:
        raise StartupError(
            f"Could not safely determine selected PostgreSQL cluster status "
            f"(pg_ctl exit {status.returncode})."
        )
    cluster_running = status.returncode == 0
    process_ids = assert_port_belongs_to_cluster(cluster_port)

    if not cluster_running and not process_ids:
        log_directory = PG_ROOT / "logs"
        log_directory.mkdir(parents=True, exist_ok=True)
        server_log = log_directory / "postgres-server.log"
        start = run_safely(
            [
                str(PG_CTL),
                "start",
                "-D",
                str(DATA_DIR),
                "-l",
                str(server_log),
                "-w",
                "-t",
                str(START_TIMEOUT_SECONDS),
            ],
            timeout=START_TIMEOUT_SECONDS + 10,
            cwd=PG_ROOT,
        )
        if start.returncode != 0:
            raise StartupError(
                f"PostgreSQL did not start (pg_ctl exit {start.returncode}). "
                f"Review '{server_log}'. PID files are never removed automatically."
            )

    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if postgres_is_ready(cluster_port):
            assert_port_belongs_to_cluster(cluster_port)
            logger.info(
                "PostgreSQL 17 is ready on 127.0.0.1:%d using the selected existing cluster.",
                cluster_port,
            )
            return
        time.sleep(0.5)

    raise StartupError(
        f"PostgreSQL did not become ready on 127.0.0.1:{cluster_port} "
        f"within {START_TIMEOUT_SECONDS} seconds."
    )


async def verify_database_connection() -> None:
    try:
        await database.wait_for_database()
    finally:
        await database.async_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--postgres-only",
        action="store_true",
        help="Start/verify PostgreSQL without starting Uvicorn.",
    )
    args = parser.parse_args()
    configure_logging()

    try:
        port = validate_database_target()
        ensure_postgres_started(port)
        if args.postgres_only:
            return 0
        asyncio.run(verify_database_connection())
        logger.info("Database connection verified; starting the FastAPI backend.")
        server = subprocess.run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8085",
            ],
            cwd=BACKEND_DIR,
            check=False,
        )
        return server.returncode
    except StartupError as exc:
        logger.error("%s", exc)
        return 1
    except database.DatabaseUnavailableError as exc:
        logger.error(
            "%s Confirm PostgreSQL is running and the local .env target is correct.",
            exc,
        )
        return 1
    except KeyboardInterrupt:
        logger.info("Backend launcher interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

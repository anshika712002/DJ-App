import logging
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
STARTUP_SCRIPT = Path(__file__).with_name("start_backend.py")
TASK_NAME = "DJApp_PG_AutoStart"
LEGACY_TASKS = ("djapp_pg_start", "DJApp_StartPG", "DJApp_Postgres_Start")
logger = logging.getLogger("djapp.task_setup")


class TaskNotFoundError(RuntimeError):
    pass


def run_schtasks(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["schtasks.exe", *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            f"Could not update Windows Task Scheduler ({type(exc).__name__})."
        ) from None
    if result.returncode != 0:
        output = (result.stdout + result.stderr).casefold()
        if "access is denied" in output or "0x80070005" in output:
            raise PermissionError(
                "Task Scheduler denied access to the current-user task."
            ) from None
        if (
            "cannot find the file specified" in output
            or "cannot find the task" in output
        ):
            raise TaskNotFoundError("The scheduled task does not exist.") from None
        raise RuntimeError(
            f"Windows Task Scheduler operation failed (exit {result.returncode})."
        )
    return result


def disable_legacy_task(task_name: str) -> None:
    try:
        result = subprocess.run(
            ["schtasks.exe", "/Change", "/TN", task_name, "/DISABLE"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            f"Could not inspect legacy startup task ({type(exc).__name__})."
        ) from None
    if result.returncode == 0:
        return
    task_error = (result.stdout + result.stderr).casefold()
    if (
        "cannot find the file specified" in task_error
        or "cannot find the task" in task_error
    ):
        return
    if "access is denied" in task_error or "0x80070005" in task_error:
        raise PermissionError(
            f"Task Scheduler denied access to legacy task '{task_name}'."
        ) from None
    raise RuntimeError(
        f"Could not disable legacy startup task '{task_name}' "
        f"(exit {result.returncode})."
    )


def register_startup_folder() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("The current user's Startup folder could not be located.")
    startup_folder = (
        Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )
    if not startup_folder.is_dir():
        raise RuntimeError("The current user's Startup folder does not exist.")

    startup_file = startup_folder / "DJApp_Postgres_AutoStart.cmd"
    content = (
        "@echo off\r\n"
        "rem DJAPP_POSTGRES_AUTOSTART\r\n"
        f'start "" /min "{PYTHON}" "{STARTUP_SCRIPT}" --postgres-only\r\n'
    )
    if startup_file.exists():
        existing = startup_file.read_text(encoding="utf-8", errors="replace")
        if "DJAPP_POSTGRES_AUTOSTART" not in existing:
            raise RuntimeError(
                "A different file already exists in the user's Startup folder; "
                "it was left unchanged."
            )
        if existing != content:
            startup_file.write_text(content, encoding="utf-8", newline="")
    else:
        startup_file.write_text(content, encoding="utf-8", newline="")
    return startup_file


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if os.name != "nt":
        logger.error("PostgreSQL autostart registration is supported only on Windows.")
        return 1
    if not PYTHON.is_file() or not STARTUP_SCRIPT.is_file():
        logger.error(
            "The project virtual environment or startup script is missing; "
            "run this setup from the repository root after installing requirements."
        )
        return 1

    task_command = subprocess.list2cmdline(
        [str(PYTHON), str(STARTUP_SCRIPT), "--postgres-only"]
    )
    registration_method = "Task Scheduler"
    try:
        run_schtasks(["/Change", "/TN", TASK_NAME, "/TR", task_command])
    except TaskNotFoundError:
        try:
            whoami = subprocess.run(
                ["whoami.exe"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error(
                "Could not determine the current Windows account (%s).",
                type(exc).__name__,
            )
            return 1
        if whoami.returncode != 0 or not whoami.stdout.strip():
            logger.error("Could not determine the current Windows account.")
            return 1
        try:
            run_schtasks(
                [
                    "/Create",
                    "/TN",
                    TASK_NAME,
                    "/SC",
                    "ONLOGON",
                    "/RU",
                    whoami.stdout.strip(),
                    "/IT",
                    "/RL",
                    "LIMITED",
                    "/TR",
                    task_command,
                    "/F",
                ]
            )
        except PermissionError:
            registration_method = "current-user Startup folder"
            try:
                startup_file = register_startup_folder()
            except (OSError, RuntimeError) as exc:
                logger.error(
                    "Could not register a per-user Startup entry (%s).",
                    type(exc).__name__,
                )
                return 1
            logger.info("Registered user-logon startup entry: %s", startup_file)
    except PermissionError:
        registration_method = "current-user Startup folder"
        try:
            startup_file = register_startup_folder()
        except (OSError, RuntimeError) as exc:
            logger.error(
                "Could not register a per-user Startup entry (%s).",
                type(exc).__name__,
            )
            return 1
        logger.info("Registered user-logon startup entry: %s", startup_file)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    blocked_legacy_tasks = []
    tasks_to_disable = LEGACY_TASKS
    if registration_method == "current-user Startup folder":
        tasks_to_disable = (TASK_NAME, *LEGACY_TASKS)
    for legacy_task in tasks_to_disable:
        try:
            disable_legacy_task(legacy_task)
        except PermissionError:
            blocked_legacy_tasks.append(legacy_task)
        except RuntimeError as exc:
            logger.error("%s", exc)
            return 1

    logger.info("PostgreSQL user-logon startup uses %s.", registration_method)
    if blocked_legacy_tasks:
        logger.warning(
            "Could not disable legacy PostgreSQL tasks: %s. "
            "Disable these once in Task Scheduler with an account allowed to edit them.",
            ", ".join(blocked_legacy_tasks),
        )
    else:
        logger.info("Conflicting legacy DJ App PostgreSQL tasks were disabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

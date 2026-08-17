"""Detached Backlot intent runner: poll pending intents and tick produce helpers."""

from __future__ import annotations

import os
import time
from pathlib import Path

from lib.paths import REPO_ROOT


LOCK_NAME = "runner.lock"
LOG_NAME = "runner.log"
POLL_SECONDS = 2.0


def _backlot_dir() -> Path:
    path = REPO_ROOT / ".backlot"
    path.mkdir(parents=True, exist_ok=True)
    return path


def lock_path() -> Path:
    return _backlot_dir() / LOCK_NAME


def log_path() -> Path:
    return _backlot_dir() / LOG_NAME


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
        except Exception:
            return False
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def runner_alive() -> bool:
    path = lock_path()
    if not path.is_file():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return False
    return _pid_alive(pid)


def acquire_lock() -> bool:
    path = lock_path()
    if path.is_file():
        try:
            pid = int(path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            pid = 0
        if _pid_alive(pid):
            return False
        try:
            path.unlink()
        except OSError:
            return False
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        return True
    except FileExistsError:
        return False


def release_lock() -> None:
    path = lock_path()
    try:
        stored = int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return
    if stored == os.getpid():
        try:
            path.unlink()
        except OSError:
            pass


def run_loop(project_id: str = "", poll_seconds: float = POLL_SECONDS) -> int:
    os.environ.setdefault("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    os.environ.setdefault("PYTHONUTF8", "1")
    if not acquire_lock():
        return 0
    from openmontage.mcp.bootstrap.tools import produce_runner_tick

    try:
        while True:
            produce_runner_tick(project_id)
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        return 0
    finally:
        release_lock()

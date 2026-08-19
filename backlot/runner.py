"""Detached Backlot intent runner: poll pending intents and tick produce helpers."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from lib.paths import REPO_ROOT


LOCK_NAME = "runner.lock"
LOG_NAME = "runner.log"
POLL_SECONDS = 2.0
_STAMP_FILES = (
    "backlot/runner.py",
    "lib/approval_bundle.py",
    "lib/board_runner.py",
    "lib/board_produce.py",
    "lib/board_advance.py",
    "lib/board_gap_plan.py",
    "lib/board_assets_gate.py",
)


def _backlot_dir() -> Path:
    path = REPO_ROOT / ".backlot"
    path.mkdir(parents=True, exist_ok=True)
    return path


def lock_path() -> Path:
    return _backlot_dir() / LOCK_NAME


def log_path() -> Path:
    return _backlot_dir() / LOG_NAME


def runner_code_stamp() -> str:
    parts: list[str] = []
    for rel in _STAMP_FILES:
        path = REPO_ROOT / rel
        try:
            parts.append(f"{rel}:{path.stat().st_mtime_ns}")
        except OSError:
            parts.append(f"{rel}:0")
    return ";".join(parts)


class RunnerBusyError(Exception):
    """Another project already owns the single machine runner."""

    def __init__(self, active_project_id: str) -> None:
        self.active_project_id = str(active_project_id or "").strip()
        self.code = "runner_busy"
        self.friendly_zh = (
            f"本机正在做「{self.active_project_id}」。"
            "请先结束或冻结当前项目，再创建或继续另一个。"
        )
        super().__init__(self.friendly_zh)


def _empty_lock() -> dict[str, Any]:
    return {"pid": 0, "code_stamp": "", "project_id": ""}


def parse_lock(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return _empty_lock()
    if raw[:1] == "{":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return _empty_lock()
        if not isinstance(data, dict):
            return _empty_lock()
        try:
            pid = int(data.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        return {
            "pid": pid,
            "code_stamp": str(data.get("code_stamp") or ""),
            "project_id": str(data.get("project_id") or "").strip(),
        }
    try:
        return {"pid": int(raw), "code_stamp": "", "project_id": ""}
    except ValueError:
        return _empty_lock()


def read_lock() -> dict[str, Any]:
    path = lock_path()
    if not path.is_file():
        return _empty_lock()
    try:
        return parse_lock(path.read_text(encoding="utf-8"))
    except OSError:
        return _empty_lock()


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
    return _pid_alive(int(read_lock().get("pid") or 0))


def runner_needs_restart() -> bool:
    if not runner_alive():
        return False
    stamp = str(read_lock().get("code_stamp") or "")
    return stamp != runner_code_stamp()


def runner_code_current() -> bool:
    return runner_alive() and not runner_needs_restart()


def active_project_id() -> str:
    info = read_lock()
    if not _pid_alive(int(info.get("pid") or 0)):
        return ""
    return str(info.get("project_id") or "").strip()


def require_idle_or_same(project_id: str) -> None:
    active = active_project_id()
    wanted = str(project_id or "").strip()
    if active and active != wanted:
        raise RunnerBusyError(active)


def acquire_lock(project_id: str = "") -> bool:
    wanted = str(project_id or "").strip()
    if not wanted:
        return False
    path = lock_path()
    if path.is_file():
        info = read_lock()
        pid = int(info.get("pid") or 0)
        if _pid_alive(pid):
            return False
        try:
            path.unlink()
        except OSError:
            return False
    payload = json.dumps(
        {
            "pid": os.getpid(),
            "code_stamp": runner_code_stamp(),
            "project_id": wanted,
        },
        ensure_ascii=False,
    )
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, payload.encode("utf-8"))
        os.close(fd)
        return True
    except FileExistsError:
        return False


def release_lock() -> None:
    path = lock_path()
    info = read_lock()
    if int(info.get("pid") or 0) != os.getpid():
        return
    try:
        path.unlink()
    except OSError:
        pass


def stop_runner(*, wait_seconds: float = 4.0) -> bool:
    """Stop the detached runner if it is alive. Safe if already gone."""
    info = read_lock()
    pid = int(info.get("pid") or 0)
    if pid == os.getpid():
        return False
    if pid <= 0 or not _pid_alive(pid):
        try:
            lock_path().unlink()
        except OSError:
            pass
        return True
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    if _pid_alive(pid) and os.name != "nt":
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        lock_path().unlink()
    except OSError:
        pass
    return not _pid_alive(pid)


def runner_should_exit(tick_result: dict[str, Any] | None) -> bool:
    if not isinstance(tick_result, dict):
        return False
    items = tick_result.get("projects")
    if not isinstance(items, list):
        items = [tick_result]
    for item in items:
        if not isinstance(item, dict):
            continue
        phase = str(item.get("phase") or "")
        if phase == "exported" or item.get("retry_exhausted") or item.get("stop_runner"):
            return True
    return False


def spawn_detached(project_id: str) -> Path | None:
    """Start the unique runner for one project. Empty id is a no-op."""
    import subprocess
    import sys

    wanted = str(project_id or "").strip()
    if not wanted:
        return None
    if runner_alive() and not runner_needs_restart():
        current = active_project_id()
        if current and current != wanted:
            raise RunnerBusyError(current)
        if not current or current == wanted:
            return log_path()
    if runner_alive():
        current = active_project_id()
        if current and current != wanted:
            raise RunnerBusyError(current)
        stop_runner()
    cmd = [sys.executable, "-m", "backlot", "runner", wanted]
    log_fh = open(log_path(), "a", encoding="utf-8")
    log_fh.write(f"\n--- spawn runner project={wanted} ---\n")
    log_fh.flush()
    env = os.environ.copy()
    env.setdefault("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("OPENMONTAGE_PROJECTS_DIR", str(REPO_ROOT / "projects"))
    kwargs: dict = {
        "stdout": log_fh,
        "stderr": log_fh,
        "stdin": subprocess.DEVNULL,
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)
    return log_path()


def run_loop(project_id: str = "", poll_seconds: float = POLL_SECONDS) -> int:
    os.environ.setdefault("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("OPENMONTAGE_PROJECTS_DIR", str(REPO_ROOT / "projects"))
    wanted = str(project_id or "").strip()
    if not wanted:
        return 0
    if not acquire_lock(wanted):
        return 0
    from openmontage.mcp.bootstrap.tools import produce_runner_tick

    try:
        while True:
            result = produce_runner_tick(wanted)
            if runner_should_exit(result):
                return 0
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        return 0
    finally:
        release_lock()

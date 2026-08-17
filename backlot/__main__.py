"""Backlot CLI.

    python -m backlot open [project-id]   # start server if needed, open browser
    python -m backlot serve [--port N]    # run the server in the foreground

``open`` is idempotent and non-fatal by design: agents call it at pipeline
initialization and must continue the production even if it fails.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

from backlot import DEFAULT_PORT


def _port() -> int:
    try:
        return int(os.environ.get("BACKLOT_PORT", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


def _board_url(port: int, project_id: str | None) -> str:
    if project_id:
        return f"http://127.0.0.1:{port}/p/{project_id}"
    return f"http://127.0.0.1:{port}/"


def _log_path() -> "Path":
    from pathlib import Path

    from lib.paths import REPO_ROOT

    log_dir = REPO_ROOT / ".backlot"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "server.log"


def _server_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _spawn_server(port: int):
    """Start the server as a detached background process; log stdout/stderr."""
    from pathlib import Path

    log_path = _log_path()
    cmd = [sys.executable, "-m", "backlot", "serve", "--port", str(port)]
    log_fh = open(log_path, "a", encoding="utf-8")
    log_fh.write(f"\n--- spawn port={port} ---\n")
    log_fh.flush()
    kwargs: dict = {
        "stdout": log_fh,
        "stderr": log_fh,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)
    return Path(log_path)


def _spawn_runner(project_id: str | None):
    """Start the local intent runner beside Backlot; idempotent if already alive."""
    from backlot.runner import log_path, runner_alive
    from lib.paths import REPO_ROOT

    if runner_alive():
        return log_path()
    cmd = [sys.executable, "-m", "backlot", "runner"]
    if project_id:
        cmd.append(project_id)
    log_fh = open(log_path(), "a", encoding="utf-8")
    log_fh.write(f"\n--- spawn runner project={project_id or '*'} ---\n")
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


def cmd_open(project_id: str | None) -> int:
    port = _port()
    url = _board_url(port, project_id)
    log_path = None
    if not _server_alive(port):
        try:
            log_path = _spawn_server(port)
        except Exception as exc:
            print(f"backlot: {url}")
            print(f"backlot: could not start server ({exc})")
            return 1
        deadline = time.time() + 15
        while time.time() < deadline:
            if _server_alive(port):
                break
            time.sleep(0.4)
        else:
            print(f"backlot: {url}")
            extra = f" log={log_path}" if log_path else ""
            print(f"backlot: server did not come up in time{extra}")
            return 1
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        _spawn_runner(project_id)
    except Exception as exc:
        print(f"backlot: runner not started ({exc})")
    print(f"backlot: {url}")
    return 0


def cmd_serve(port: int) -> int:
    import uvicorn

    uvicorn.run("backlot.server:app", host="127.0.0.1", port=port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backlot", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    p_open = sub.add_parser("open", help="open the board in the browser (starts server if needed)")
    p_open.add_argument("project_id", nargs="?", default=None)

    p_serve = sub.add_parser("serve", help="run the Backlot server in the foreground")
    p_serve.add_argument("--port", type=int, default=_port())

    p_runner = sub.add_parser("runner", help="consume pending board intents on this machine")
    p_runner.add_argument("project_id", nargs="?", default="")

    args = parser.parse_args(argv)
    if args.command == "open":
        return cmd_open(args.project_id)
    if args.command == "serve":
        return cmd_serve(args.port)
    if args.command == "runner":
        from backlot.runner import run_loop

        return run_loop(args.project_id or "")
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

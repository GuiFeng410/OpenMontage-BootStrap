"""Local BootStrap install snapshot (no secrets)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import WorkspacePaths

STATE_RELATIVE = Path(".openmontage") / "install-state.json"
STATE_VERSION = 1
VIDEO_SECTION_MARK = "## 【二、视频生成专项服务】"
STOCK_KEY_NAMES = ("PEXELS_API_KEY", "PIXABAY_API_KEY")
ENV_ASSIGN_RE = re.compile(r"^(?:export\s+)?([A-Z][A-Z0-9_]+)\s*=")
KEYISH_RE = re.compile(r"(?:KEY|TOKEN|SECRET)$")
EXCLUDE_NAME_MARKERS = ("OSS_", "ALIYUN_")
PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "changeme",
        "change_me",
        "your_key_here",
        "your-key-here",
        "xxx",
        "todo",
        "none",
        "null",
    }
)
STATE_FIELDS = (
    "version",
    "verify_ready",
    "repo_root",
    "projects_dir",
    "latest_project_id",
    "existing_project_count",
    "video_key_present",
    "video_key_names_present",
    "video_key_sources",
    "stock_key_present",
    "stock_key_names_present",
    "stock_key_sources",
    "scanned_names",
    "scanned_at",
)


def _workspace(repo_root: Path) -> WorkspacePaths:
    return WorkspacePaths(repo_root=Path(repo_root).resolve())


def state_path(repo_root: Path) -> Path:
    return _workspace(repo_root).install_state_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_filled(raw: str) -> bool:
    value = raw.strip().strip("'").strip('"').strip()
    if not value:
        return False
    lowered = value.lower()
    if lowered in PLACEHOLDER_VALUES:
        return False
    if lowered.startswith("<") and lowered.endswith(">"):
        return False
    return True


def parse_assignment_names(text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        match = ENV_ASSIGN_RE.match(stripped)
        if not match:
            continue
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def video_channel_names_from_example(example_text: str) -> list[str]:
    start = example_text.find(VIDEO_SECTION_MARK)
    if start < 0:
        section = example_text
    else:
        rest = example_text[start + len(VIDEO_SECTION_MARK) :]
        end = rest.find("\n## 【")
        section = rest if end < 0 else rest[:end]
    return [
        name
        for name in parse_assignment_names(section)
        if KEYISH_RE.search(name) and not any(mark in name for mark in EXCLUDE_NAME_MARKERS)
    ]


def parse_dotenv_filled_names(text: str, names: list[str]) -> list[str]:
    wanted = set(names)
    filled: list[str] = []
    found: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_ASSIGN_RE.match(stripped)
        if not match:
            continue
        name = match.group(1)
        if name not in wanted or name in found:
            continue
        value = stripped.split("=", 1)[1]
        if "#" in value:
            value = value.split("#", 1)[0]
        if _is_filled(value):
            filled.append(name)
            found.add(name)
    return filled


def process_env_filled_names(names: list[str], environ: dict[str, str] | None = None) -> list[str]:
    env = os.environ if environ is None else environ
    filled: list[str] = []
    for name in names:
        raw = env.get(name)
        if raw is not None and _is_filled(raw):
            filled.append(name)
    return filled


def _merge_present(from_file: list[str], from_proc: list[str]) -> list[str]:
    present: list[str] = []
    seen: set[str] = set()
    for name in from_file + from_proc:
        if name in seen:
            continue
        seen.add(name)
        present.append(name)
    return present


def _scan_named_keys(
    *,
    repo_root: Path,
    names: list[str],
    environ: dict[str, str] | None = None,
) -> tuple[list[str], list[str], list[str], dict[str, Any]]:
    root = Path(repo_root).resolve()
    env_path = root / ".env"
    env_text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
    from_file = parse_dotenv_filled_names(env_text, names)
    from_proc = process_env_filled_names(names, environ)
    present = _merge_present(from_file, from_proc)
    meta = {
        "repo_root": str(root),
        "env_path": str(env_path),
        "env_file_exists": env_path.is_file(),
        "scanned_names": list(names),
    }
    return from_file, from_proc, present, meta


def scan_video_keys(*, repo_root: Path, environ: dict[str, str] | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    example_path = root / ".env-example.md"
    example_text = example_path.read_text(encoding="utf-8") if example_path.is_file() else ""
    names = video_channel_names_from_example(example_text)
    from_file, from_proc, present, meta = _scan_named_keys(
        repo_root=root, names=names, environ=environ
    )
    return {
        **meta,
        "example_path": str(example_path),
        "example_exists": example_path.is_file(),
        "video_key_present": bool(present),
        "video_key_names_present": present,
        "video_key_sources": {
            "env_file": from_file,
            "process_env": from_proc,
        },
        "note_zh": "只报告变量名是否非空，不返回 Key 值。空 Key 禁止付费 generate。",
    }


def scan_stock_keys(*, repo_root: Path, environ: dict[str, str] | None = None) -> dict[str, Any]:
    from_file, from_proc, present, meta = _scan_named_keys(
        repo_root=repo_root, names=list(STOCK_KEY_NAMES), environ=environ
    )
    return {
        **meta,
        "stock_key_present": bool(present),
        "stock_key_names_present": present,
        "stock_key_sources": {
            "env_file": from_file,
            "process_env": from_proc,
        },
        "note_zh": "只报告 Pexels/Pixabay 变量名是否非空，不返回 Key 值。",
    }


def _empty_state(repo_root: Path) -> dict[str, Any]:
    ws = _workspace(repo_root)
    return {
        "version": STATE_VERSION,
        "verify_ready": False,
        "repo_root": str(ws.repo_root),
        "projects_dir": str(ws.projects_dir),
        "latest_project_id": None,
        "existing_project_count": 0,
        "video_key_present": False,
        "video_key_names_present": [],
        "video_key_sources": {"env_file": [], "process_env": []},
        "stock_key_present": False,
        "stock_key_names_present": [],
        "stock_key_sources": {"env_file": [], "process_env": []},
        "scanned_names": [],
        "scanned_at": None,
    }


def _public_state(data: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    clean = _empty_state(repo_root)
    for key in STATE_FIELDS:
        if key in data:
            clean[key] = data[key]
    clean["version"] = STATE_VERSION
    if clean.get("video_key_names_present") is None:
        clean["video_key_names_present"] = []
    if clean.get("stock_key_names_present") is None:
        clean["stock_key_names_present"] = []
    ws = _workspace(repo_root)
    clean["repo_root"] = str(ws.repo_root)
    clean["projects_dir"] = str(ws.projects_dir)
    return clean


def count_existing_projects(projects_dir: Path) -> int:
    root = Path(projects_dir)
    if not root.is_dir():
        return 0
    count = 0
    try:
        children = list(root.iterdir())
    except OSError:
        return 0
    for child in children:
        try:
            if child.is_dir() and (child / "project.json").is_file():
                count += 1
        except OSError:
            continue
    return count


def read_install_state(*, repo_root: Path) -> dict[str, Any]:
    path = state_path(repo_root)
    if not path.is_file():
        return {
            "exists": False,
            "path": str(path),
            "state": _empty_state(repo_root),
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "exists": True,
            "path": str(path),
            "state": _empty_state(repo_root),
            "note_zh": "状态文件损坏，已按空快照返回，未读取任何密钥。",
        }
    if not isinstance(raw, dict):
        raw = {}
    return {
        "exists": True,
        "path": str(path),
        "state": _public_state(raw, repo_root),
    }


def snapshot_install_state(
    *,
    repo_root: Path,
    verify_ready: bool | None = None,
    latest_project_id: str = "",
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    scan = scan_video_keys(repo_root=repo_root, environ=environ)
    stock = scan_stock_keys(repo_root=repo_root, environ=environ)
    current = read_install_state(repo_root=repo_root)["state"]
    state = _public_state(current, repo_root)
    ws = _workspace(repo_root)
    state["repo_root"] = str(ws.repo_root)
    state["projects_dir"] = str(ws.projects_dir)
    projects_dir = ws.projects_dir
    state["existing_project_count"] = count_existing_projects(projects_dir)
    state["video_key_present"] = bool(scan["video_key_present"])
    state["video_key_names_present"] = list(scan["video_key_names_present"])
    state["video_key_sources"] = scan["video_key_sources"]
    state["stock_key_present"] = bool(stock["stock_key_present"])
    state["stock_key_names_present"] = list(stock["stock_key_names_present"])
    state["stock_key_sources"] = stock["stock_key_sources"]
    state["scanned_names"] = list(scan["scanned_names"])
    state["scanned_at"] = _now_iso()
    if verify_ready is not None:
        state["verify_ready"] = bool(verify_ready)
    pid = (latest_project_id or "").strip()
    if pid:
        state["latest_project_id"] = pid
    path = state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    dumped = path.read_text(encoding="utf-8")
    env = environ or os.environ
    checked = list(state["video_key_names_present"]) + list(state["stock_key_names_present"])
    for name in checked:
        secret = env.get(name, "")
        if secret and _is_filled(secret) and len(secret.strip()) >= 8 and secret in dumped:
            raise RuntimeError("install-state.json must not contain secret values")
    return {
        "path": str(path),
        "state": state,
        "scan": scan,
        "stock_scan": stock,
    }

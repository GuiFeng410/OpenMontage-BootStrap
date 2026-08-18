"""Create a commercial project from the Backlot library (local writes only)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from lib.paths import REPO_ROOT
from openmontage.mcp.bootstrap import install_state as install_state_mod
from openmontage.mcp.bootstrap import tools as bootstrap_tools
from openmontage.mcp.common.errors import ConfigError, DoctorError

REVIEW_MODE_IDS = frozenset({"minimal", "normal", "pro"})
DEFAULT_REVIEW_MODE = "normal"
MAX_DURATION = 75
MAX_ASSET_FILES = 40
MAX_ASSET_BYTES = 25 * 1024 * 1024
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_FILE_RE = re.compile(r"[^A-Za-z0-9._-]+")


class LibraryCreateError(Exception):
    def __init__(self, message: str, *, code: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.friendly_zh = message


def public_install_flags(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = Path(repo_root or REPO_ROOT)
    listed = install_state_mod.read_install_state(repo_root=root)
    state = listed.get("state") if isinstance(listed.get("state"), dict) else {}
    projects = Path(os.environ.get("OPENMONTAGE_PROJECTS_DIR") or (root / "projects"))
    counted = install_state_mod.count_existing_projects(projects)
    return {
        "install_state_exists": bool(listed.get("exists")),
        "verify_ready": bool(state.get("verify_ready")),
        "video_key_present": bool(state.get("video_key_present")),
        "latest_project_id": state.get("latest_project_id"),
        "existing_project_count": counted or int(state.get("existing_project_count") or 0),
    }


def prepare_local_runtime(*, repo_root: Path | None = None) -> Path:
    """Backlot serve/create must set sandbox env; clone alone does not."""
    root = Path(repo_root or REPO_ROOT)
    os.environ.setdefault("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    projects = Path(os.environ.get("OPENMONTAGE_PROJECTS_DIR") or (root / "projects"))
    os.environ["OPENMONTAGE_PROJECTS_DIR"] = str(projects.resolve())
    projects.mkdir(parents=True, exist_ok=True)
    return projects


def remember_machine_seen(
    *,
    repo_root: Path | None = None,
    verify_ready: bool | None = None,
    latest_project_id: str = "",
) -> dict[str, Any]:
    root = Path(repo_root or REPO_ROOT)
    prepare_local_runtime(repo_root=root)
    return install_state_mod.snapshot_install_state(
        repo_root=root,
        verify_ready=verify_ready,
        latest_project_id=latest_project_id,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slug_project_id(title: str) -> str:
    ascii_part = _SLUG_RE.sub("-", (title or "").strip().lower()).strip("-")
    base = ascii_part[:32] if ascii_part else "commercial"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{base}-{stamp}"


def _parse_duration(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise LibraryCreateError("时长须为 1–75 的整数秒", code="bad_duration") from exc
    if value < 1 or value > MAX_DURATION:
        raise LibraryCreateError("时长须在 1–75 秒", code="bad_duration")
    return value


def _normalize_review_mode(raw: Any) -> str:
    mode = str(raw or "").strip()
    if mode not in REVIEW_MODE_IDS:
        return DEFAULT_REVIEW_MODE
    return mode


def _patch_marker(
    project_dir: Path,
    *,
    review_mode: str,
    duration_seconds: int | None,
    asset_location: str,
    theme: str,
    imported_asset_count: int = 0,
) -> None:
    path = project_dir / "project.json"
    marker = json.loads(path.read_text(encoding="utf-8"))
    profile = dict(marker.get("production_profile") or {})
    stored_review = "pro" if review_mode == "pro" else "normal"
    profile["review_mode"] = stored_review
    profile["review_mode_preset"] = review_mode
    profile["fast_track_requested"] = review_mode == "minimal"
    if duration_seconds is not None:
        profile["duration_seconds"] = duration_seconds
    if theme:
        profile["theme_zh"] = theme
    if asset_location:
        profile["asset_location"] = asset_location
        if asset_location.startswith(("http://", "https://")):
            profile["product_url"] = asset_location
    if imported_asset_count:
        profile["imported_asset_count"] = imported_asset_count
    marker["production_profile"] = profile
    marker["library_created_at"] = _now_iso()
    path.write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_asset_name(raw: str, index: int) -> str:
    name = Path(str(raw or "").replace("\\", "/")).name.strip()
    stem = _FILE_RE.sub("-", name).strip(".-") or f"asset-{index:02d}"
    return stem[:80]


def import_local_asset_files(
    project_dir: Path,
    files: Iterable[tuple[str, bytes]],
) -> list[str]:
    dest = project_dir / "assets" / "images"
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for index, (name, data) in enumerate(files, start=1):
        if index > MAX_ASSET_FILES:
            break
        if not data or len(data) > MAX_ASSET_BYTES:
            continue
        filename = _safe_asset_name(name, index)
        target = dest / filename
        if target.exists():
            target = dest / f"{target.stem}-{index}{target.suffix}"
        target.write_bytes(data)
        written.append(str(target.relative_to(project_dir)).replace("\\", "/"))
    return written


def create_library_project(
    *,
    title: str,
    review_mode: str = DEFAULT_REVIEW_MODE,
    duration_seconds: Any = None,
    asset_location: str = "",
    product_url: str = "",
    repo_root: Path | None = None,
    asset_files: Iterable[tuple[str, bytes]] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root or REPO_ROOT)
    prepare_local_runtime(repo_root=root)
    flags = public_install_flags(repo_root=root)
    theme = (title or "").strip()
    if not theme:
        raise LibraryCreateError("请先填写商品主题", code="missing_title")
    location = (asset_location or product_url or "").strip()
    duration = _parse_duration(duration_seconds)
    mode = _normalize_review_mode(review_mode)
    requested_id = slug_project_id(theme)
    try:
        result = bootstrap_tools.produce_init_project(
            requested_id,
            theme,
            "bootstrap-commercial",
            "create_new",
        )
    except (ConfigError, DoctorError) as exc:
        raise LibraryCreateError(
            f"本机创建项目失败：{exc}。请回聊天让 Agent 先读 .openmontage/install-state.json；"
            "已经下载使用过的不要再克隆。",
            code="init_failed",
        ) from exc
    except Exception as exc:
        raise LibraryCreateError(
            f"本机创建项目失败：{type(exc).__name__}。请回聊天继续。",
            code="init_failed",
        ) from exc
    project_id = str(result.get("project_id") or "").strip()
    project_dir = Path(str(result.get("project_dir") or ""))
    if not project_id or not project_dir.is_dir():
        raise LibraryCreateError(
            "创建结果不完整。请回聊天让 Agent 检查项目目录。",
            code="init_incomplete",
        )
    imported = import_local_asset_files(project_dir, asset_files or ())
    if imported and not location:
        location = "local-upload"
    _patch_marker(
        project_dir,
        review_mode=mode,
        duration_seconds=duration,
        asset_location=location,
        theme=theme,
        imported_asset_count=len(imported),
    )
    try:
        remember_machine_seen(
            repo_root=root,
            verify_ready=True,
            latest_project_id=project_id,
        )
    except Exception:
        pass
    return {
        "ok": True,
        "project_id": project_id,
        "title": theme,
        "pipeline_type": "bootstrap-commercial",
        "review_mode": mode,
        "imported_count": len(imported),
        "imported_files": imported,
        "video_key_present": flags["video_key_present"],
        "board_path": f"/p/{project_id}",
        "friendly_zh": (
            (
                f"已创建项目，导入 {len(imported)} 个本地文件。请按当前挡位一步一步确认。"
                if imported
                else "已创建项目。请按当前挡位一步一步确认。"
            )
            if flags["video_key_present"]
            else (
                f"已创建项目，导入 {len(imported)} 个本地文件。当前没有视频 Key，付费生视频前请回聊天补 Key。"
                if imported
                else "已创建项目。当前没有视频 Key，付费生视频前请回聊天补 Key。"
            )
        ),
        "request_id": str(uuid4()),
    }

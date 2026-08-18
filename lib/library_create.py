"""Create a commercial project from the Backlot library (local writes only)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from lib.experiment_budget import (
    DEFAULT_AI_SHARE_PCT,
    clamp_ai_share_pct,
    motion_mix_from_ai_share_pct,
)
from lib.paths import REPO_ROOT
from openmontage.mcp.bootstrap import install_state as install_state_mod
from openmontage.mcp.bootstrap import tools as bootstrap_tools
from openmontage.mcp.common.errors import ConfigError, DoctorError

REVIEW_MODE_IDS = frozenset({"minimal", "normal", "pro"})
DEFAULT_REVIEW_MODE = "normal"
PRODUCTION_TIERS = frozenset({"light", "medium", "heavy"})
TIER_LABEL_ZH = {"light": "轻", "medium": "中", "heavy": "重"}
COMMERCIAL_VIDEO_MODELS: tuple[dict[str, Any], ...] = (
    {
        "id": "agnes-video-v2.0",
        "channel": "agnes",
        "label_zh": "Agnes",
        "key_names": ("AGNES_API_KEY", "AGNES_AI_API_KEY"),
        "capability_zh": "超长自动切段拼接。",
    },
    {
        "id": "hy-video-1.5",
        "channel": "tokenhub",
        "label_zh": "TokenHub·混元",
        "key_names": ("TOKENHUB_API_KEY", "TENCENT_TOKENHUB_API_KEY"),
        "capability_zh": "单段时长由模型定，长片自动拼接。",
    },
    {
        "id": "pixverse-video-v6.0",
        "channel": "tokenhub",
        "label_zh": "TokenHub·Pixverse",
        "key_names": ("TOKENHUB_API_KEY", "TENCENT_TOKENHUB_API_KEY"),
        "capability_zh": "默认可约 5 秒一段，长片自动拼接。",
    },
)
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


def list_commercial_video_models(
    key_names_present: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    present = {str(name) for name in (key_names_present or [])}
    models: list[dict[str, Any]] = []
    for spec in COMMERCIAL_VIDEO_MODELS:
        models.append(
            {
                "id": spec["id"],
                "channel": spec["channel"],
                "label_zh": spec["label_zh"],
                "available": any(name in present for name in spec["key_names"]),
                "capability_zh": spec["capability_zh"],
            }
        )
    return models


def default_commercial_video_model(
    models: list[dict[str, Any]] | None = None,
    *,
    key_names_present: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    rows = models if models is not None else list_commercial_video_models(key_names_present)
    for item in rows:
        if item.get("available"):
            return item
    return None


def resolve_commercial_video_model(
    raw_id: str | None,
    *,
    key_names_present: Iterable[str] | None = None,
) -> dict[str, Any]:
    models = list_commercial_video_models(key_names_present)
    wanted = str(raw_id or "").strip()
    if wanted:
        picked = next((item for item in models if item["id"] == wanted), None)
        if picked is None:
            raise LibraryCreateError("请选择已接线的视频模型", code="bad_video_model")
        if not picked["available"]:
            raise LibraryCreateError(
                "该模型尚未填入 Key。请写入仓根 .env 后点「已填入 Key，刷新可用性」，或改选其它模型。",
                code="missing_model_key",
            )
        return picked
    picked = default_commercial_video_model(models)
    if picked is None:
        raise LibraryCreateError(
            "重度需要视频模型 Key。请写入仓根 .env 后点「已填入 Key，刷新可用性」。",
            code="missing_video_key",
        )
    return picked


def public_install_flags(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = Path(repo_root or REPO_ROOT)
    listed = install_state_mod.read_install_state(repo_root=root)
    state = listed.get("state") if isinstance(listed.get("state"), dict) else {}
    projects = Path(os.environ.get("OPENMONTAGE_PROJECTS_DIR") or (root / "projects"))
    counted = install_state_mod.count_existing_projects(projects)
    try:
        live = _flags_from_live_scan(repo_root=root)
    except Exception:
        names = list(state.get("video_key_names_present") or [])
        live = {
            "video_key_present": bool(state.get("video_key_present")),
            "stock_key_present": bool(state.get("stock_key_present")),
            "video_key_names_present": names,
            "stock_key_names_present": list(state.get("stock_key_names_present") or []),
            "video_models": list_commercial_video_models(names),
        }
    return {
        "install_state_exists": bool(listed.get("exists")),
        "verify_ready": bool(state.get("verify_ready")),
        **live,
        "scanned_at": state.get("scanned_at"),
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


def _flags_from_live_scan(
    *,
    repo_root: Path,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    video = install_state_mod.scan_video_keys(repo_root=repo_root, environ=environ)
    stock = install_state_mod.scan_stock_keys(repo_root=repo_root, environ=environ)
    names = list(video["video_key_names_present"])
    return {
        "video_key_present": bool(video["video_key_present"]),
        "stock_key_present": bool(stock["stock_key_present"]),
        "video_key_names_present": names,
        "stock_key_names_present": list(stock["stock_key_names_present"]),
        "video_models": list_commercial_video_models(names),
    }


def refresh_key_availability(
    *,
    repo_root: Path | None = None,
    environ: dict[str, str] | None = None,
    load_dotenv_file: bool = True,
) -> dict[str, Any]:
    """Re-scan .env on disk. Never returns Key values."""
    root = Path(repo_root or REPO_ROOT)
    prepare_local_runtime(repo_root=root)
    if load_dotenv_file and environ is None:
        env_path = root / ".env"
        if env_path.is_file():
            from dotenv import load_dotenv

            load_dotenv(env_path, override=True)
    snap = install_state_mod.snapshot_install_state(
        repo_root=root,
        environ=environ,
    )
    flags = public_install_flags(repo_root=root)
    video_ok = bool(flags["video_key_present"])
    stock_ok = bool(flags["stock_key_present"])
    if video_ok and stock_ok:
        friendly = "已刷新：重度与中度均可用。"
    elif video_ok:
        friendly = "已刷新：重度可用。中度还需要 Pexels 或 Pixabay Key。"
    elif stock_ok:
        friendly = "已刷新：中度可用。重度还需要视频模型 Key。"
    else:
        friendly = "已刷新：尚未检测到视频或素材 Key。写入仓根 .env 后再点刷新。"
    return {
        "ok": True,
        **flags,
        "video_key_names_present": list(snap["state"].get("video_key_names_present") or []),
        "stock_key_names_present": list(snap["state"].get("stock_key_names_present") or []),
        "scanned_at": snap["state"].get("scanned_at"),
        "friendly_zh": friendly,
        "note_zh": "只报告变量名是否非空，不返回 Key 值。",
    }


def start_production(
    *,
    project_id: str,
    production_tier: str,
    ai_share_pct: int | float | str | None = None,
    video_model: str | None = None,
    repo_root: Path | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Lock production tier on project.json. Never calls paid generate."""
    root = Path(repo_root or REPO_ROOT)
    projects = prepare_local_runtime(repo_root=root)
    pid = str(project_id or "").strip()
    if not pid or any(c in pid for c in "/\\:") or pid in {".", ".."}:
        raise LibraryCreateError("无效的项目编号", code="bad_project")
    project_dir = projects / pid
    marker_path = project_dir / "project.json"
    if not marker_path.is_file():
        raise LibraryCreateError("找不到该项目", code="unknown_project", http_status=404)
    tier = str(production_tier or "").strip()
    if tier not in PRODUCTION_TIERS:
        raise LibraryCreateError("请选择轻度、中度或重度", code="bad_tier")
    keys = _flags_from_live_scan(repo_root=root, environ=environ)
    if tier == "heavy" and not keys["video_key_present"]:
        raise LibraryCreateError(
            "重度需要视频模型 Key。请写入仓根 .env 后点「已填入 Key，刷新可用性」。",
            code="missing_video_key",
        )
    if tier == "medium" and not keys["stock_key_present"]:
        raise LibraryCreateError(
            "中度需要素材库 Key（Pexels 或 Pixabay）。请写入仓根 .env 后点「已填入 Key，刷新可用性」。",
            code="missing_stock_key",
        )
    picked_model: dict[str, Any] | None = None
    if tier == "heavy":
        picked_model = resolve_commercial_video_model(
            video_model,
            key_names_present=keys["video_key_names_present"],
        )
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if not isinstance(marker, dict):
        raise LibraryCreateError("项目标记损坏", code="bad_marker")
    profile = dict(marker.get("production_profile") or {})
    profile["production_tier"] = tier
    profile["production_start_requested_at"] = _now_iso()
    locked_pct: int | None = None
    if tier == "heavy":
        existing_pct = profile.get("ai_share_pct")
        default_pct = (
            int(existing_pct) if existing_pct is not None else DEFAULT_AI_SHARE_PCT
        )
        locked_pct = clamp_ai_share_pct(ai_share_pct, default=default_pct)
        profile["ai_share_pct"] = locked_pct
        profile["motion_mix"] = motion_mix_from_ai_share_pct(locked_pct)
        profile["motion_mix_source"] = "user_selected"
        profile["ai_video"] = "enabled"
        if picked_model is None:
            raise LibraryCreateError(
                "重度需要视频模型 Key。请写入仓根 .env 后点「已填入 Key，刷新可用性」。",
                code="missing_video_key",
            )
        profile["video_channel"] = picked_model["channel"]
        profile["video_model"] = picked_model["id"]
    else:
        profile["ai_video"] = "disabled"
    marker["production_profile"] = profile
    marker_path.write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        remember_machine_seen(repo_root=root, latest_project_id=pid)
    except Exception:
        pass
    label = TIER_LABEL_ZH[tier]
    result = {
        "ok": True,
        "project_id": pid,
        "production_tier": tier,
        "production_tier_zh": label,
        "video_key_present": keys["video_key_present"],
        "stock_key_present": keys["stock_key_present"],
        "friendly_zh": f"已锁定制作档「{label}」，可以从当前停点继续。本页不会直接调付费接口。",
    }
    if locked_pct is not None:
        result["ai_share_pct"] = locked_pct
        result["motion_mix"] = profile["motion_mix"]
    if picked_model is not None:
        result["video_channel"] = picked_model["channel"]
        result["video_model"] = picked_model["id"]
        result["video_model_zh"] = picked_model["label_zh"]
        result["video_models"] = keys["video_models"]
    return result


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
                f"已创建项目，导入 {len(imported)} 个本地文件。当前没有视频 Key，重度请先在流程页补 Key 并刷新。"
                if imported
                else "已创建项目。当前没有视频 Key，重度请先在流程页补 Key 并刷新。"
            )
        ),
        "request_id": str(uuid4()),
    }

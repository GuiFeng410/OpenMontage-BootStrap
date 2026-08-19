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
        "board_generate": True,
    },
    {
        "id": "hy-video-1.5",
        "channel": "tokenhub",
        "label_zh": "TokenHub·混元",
        "key_names": ("TOKENHUB_API_KEY", "TENCENT_TOKENHUB_API_KEY"),
        "capability_zh": "看板可开烧。单段时长由模型定，长片自动拼接。",
        "board_generate": True,
    },
    {
        "id": "pixverse-video-v6.0",
        "channel": "tokenhub",
        "label_zh": "TokenHub·Pixverse",
        "key_names": ("TOKENHUB_API_KEY", "TENCENT_TOKENHUB_API_KEY"),
        "capability_zh": "看板可开烧。默认可约 5 秒一段，长片自动拼接。",
        "board_generate": True,
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
        key_ready = any(name in present for name in spec["key_names"])
        board_generate = bool(spec.get("board_generate"))
        models.append(
            {
                "id": spec["id"],
                "channel": spec["channel"],
                "label_zh": spec["label_zh"],
                "key_ready": key_ready,
                "board_generate": board_generate,
                "available": key_ready and board_generate,
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
        if not picked.get("board_generate"):
            raise LibraryCreateError(
                "该模型看板暂不能开烧，不会改走其它渠道。请改选 Agnes，或回聊天。",
                code="board_generate_unsupported",
            )
        if not picked["available"]:
            raise LibraryCreateError(
                "该模型尚未填入 Key。请写入仓根 .env 后点「已填入 Key，刷新可用性」，或改选其它模型。",
                code="missing_model_key",
            )
        return picked
    picked = default_commercial_video_model(models)
    if picked is None:
        raise LibraryCreateError(
            "重度需要已填 Key 的视频模型。可开烧：Agnes、混元、Pixverse。请写入对应 Key 后刷新。",
            code="missing_video_key",
        )
    return picked


def _empty_image_flags() -> dict[str, Any]:
    from lib.board_gap_plan import list_commercial_image_models

    return {
        "image_key_present": False,
        "image_key_names_present": [],
        "image_models": list_commercial_image_models([]),
    }


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
            **_empty_image_flags(),
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


def _image_flags(
    *,
    repo_root: Path,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    from lib.board_gap_plan import list_commercial_image_models, scan_image_key_names

    names = scan_image_key_names(repo_root=repo_root, environ=environ)
    models = list_commercial_image_models(names)
    return {
        "image_key_present": any(item.get("available") for item in models),
        "image_key_names_present": names,
        "image_models": models,
    }


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
        **_image_flags(repo_root=repo_root, environ=environ),
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
    image_ok = bool(flags.get("image_key_present"))
    image_count = sum(
        1 for item in flags.get("image_models") or [] if item.get("available")
    )
    if video_ok and stock_ok:
        friendly = "已刷新：重度与中度均可用。"
    elif video_ok:
        friendly = "已刷新：重度可用。中度还需要 Pexels 或 Pixabay Key。"
    elif stock_ok:
        friendly = "已刷新：中度可用。重度还需要视频模型 Key。"
    else:
        friendly = "已刷新：尚未检测到视频或素材 Key。写入仓根 .env 后再点刷新。"
    if image_ok:
        friendly += f" 已检测到 {image_count} 个可用生图模型。"
        if image_count > 1:
            friendly += " 方案页若选图生图，全片共用其中一个。"
    else:
        friendly += " 尚未检测到生图 Key；方案页「图生图」不可执行。"
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
            "重度需要已填 Key 的视频模型。可开烧：Agnes、混元、Pixverse。请写入对应 Key 后刷新。",
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
    profile["runner_start_pending"] = True
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
                "重度需要已填 Key 的视频模型。可开烧：Agnes、混元、Pixverse。请写入对应 Key 后刷新。",
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
    stop_stage = None
    try:
        from lib.board_advance import ensure_current_stop_card

        stop_stage = ensure_current_stop_card(pid, marker, projects_dir=projects)
        if stop_stage:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            profile = dict(marker.get("production_profile") or {})
            profile["runner_start_pending"] = False
            marker["production_profile"] = profile
            marker_path.write_text(
                json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    except Exception:
        stop_stage = None
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
        "friendly_zh": f"已锁定制作档「{label}」，请留在本页确认当前停点。本页不会直接调付费接口。",
        "next_stop": stop_stage,
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


def runner_occupant(*, projects_dir: Path | None = None) -> dict[str, str]:
    """Title of the project currently bound to the unique runner, if any."""
    try:
        from backlot.runner import active_project_id, runner_alive
    except Exception:
        return {"project_id": "", "title": ""}
    from lib.paths import PROJECTS_DIR

    if not runner_alive():
        return {"project_id": "", "title": ""}
    pid = str(active_project_id() or "").strip()
    if not pid:
        return {"project_id": "", "title": ""}
    title = pid
    root = Path(projects_dir or PROJECTS_DIR)
    marker_path = root / pid / "project.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        marker = {}
    if isinstance(marker, dict) and str(marker.get("title") or "").strip():
        title = str(marker.get("title")).strip()
    return {"project_id": pid, "title": title}


def interrupt_active_project(
    *,
    projects_dir: Path | None = None,
    reason_zh: str = "",
    pause_busy: bool = True,
) -> dict[str, Any]:
    """Mark the bound project interrupted. Does not export or stop serve."""
    occupant = runner_occupant(projects_dir=projects_dir)
    if pause_busy:
        from lib.board_produce import STATUS_PAUSED, busy_project_ids, write_job

        copy = reason_zh or "已中断。项目未结束，可在库页继续。"
        for pid in busy_project_ids(projects_dir=projects_dir):
            try:
                write_job(
                    pid,
                    {
                        "status": STATUS_PAUSED,
                        "code": "interrupted",
                        "friendly_zh": copy,
                    },
                    projects_dir=projects_dir,
                )
            except Exception:
                continue
    pid = str(occupant.get("project_id") or "").strip()
    if pid:
        from lib.project_export import mark_interrupted

        mark_interrupted(
            pid,
            reason_zh=reason_zh or "已中断。项目未结束，可在库页继续。",
            projects_dir=projects_dir,
        )
    return occupant


def release_library_runner(
    *,
    confirm: bool = False,
    interrupt: bool = False,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    """Stop the unique runner without shutting the web server. Does not export."""
    if confirm is not True:
        raise LibraryCreateError("confirm required", code="confirm_required", http_status=400)
    from lib.board_produce import busy_project_ids

    busy = busy_project_ids(projects_dir=projects_dir)
    if busy and not interrupt:
        raise LibraryCreateError(
            "正在出片。确认中断后才能停下；不会结束导出。",
            code="producing",
            http_status=409,
        )
    occupant = interrupt_active_project(
        projects_dir=projects_dir,
        reason_zh="已中断。项目未结束，可在库页继续。",
        pause_busy=bool(busy),
    )
    from backlot.runner import stop_runner

    stop_runner()
    title = occupant.get("title") or occupant.get("project_id") or "当前项目"
    return {
        "ok": True,
        "released_project_id": occupant.get("project_id") or "",
        "friendly_zh": f"已中断「{title}」。可以创建或继续另一个项目。网页服务还在。",
    }


def _assert_runner_idle_or_same(project_id: str = "") -> None:
    try:
        from backlot.runner import active_project_id, runner_alive
    except Exception:
        return
    if not runner_alive():
        return
    active = str(active_project_id() or "").strip()
    wanted = str(project_id or "").strip()
    if not active:
        return
    if wanted and active == wanted:
        return
    raise LibraryCreateError(
        f"本机正在做「{active}」。请先在库页点「中断并做别的」，再创建或继续另一个。",
        code="runner_busy",
        http_status=409,
    )


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
    _assert_runner_idle_or_same("")
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
        "spawn_runner": True,
    }


def continue_library_project(
    *,
    project_id: str,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Bind the unique runner to an existing unfinished project. Does not burn."""
    from lib.project_export import is_completed

    root = Path(repo_root or REPO_ROOT)
    projects = prepare_local_runtime(repo_root=root)
    pid = str(project_id or "").strip()
    if not pid or any(c in pid for c in "/\\:") or pid in {".", ".."}:
        raise LibraryCreateError("无效的项目编号", code="bad_project")
    marker_path = projects / pid / "project.json"
    if not marker_path.is_file():
        raise LibraryCreateError("找不到该项目", code="unknown_project", http_status=404)
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LibraryCreateError("项目标记损坏", code="bad_marker") from exc
    if not isinstance(marker, dict):
        raise LibraryCreateError("项目标记损坏", code="bad_marker")
    if is_completed(marker):
        raise LibraryCreateError(
            "这个项目已经结束并导出。请在库页下载成片，不要续做。",
            code="already_completed",
            http_status=409,
        )
    _assert_runner_idle_or_same(pid)
    stop = marker.get("board_stop") if isinstance(marker.get("board_stop"), dict) else {}
    stage = str(stop.get("stage") or "")
    prompt = str(stop.get("decision_prompt_zh") or "")
    try:
        remember_machine_seen(repo_root=root, latest_project_id=pid)
    except Exception:
        pass
    return {
        "ok": True,
        "project_id": pid,
        "board_path": f"/p/{pid}",
        "current_stop": stage,
        "user_stage_zh": prompt or stage,
        "friendly_zh": "已继续这个项目。从当前停点接着做，不会新建，也不会自动开烧。",
        "spawn_runner": True,
    }

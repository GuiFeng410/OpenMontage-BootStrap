"""Start and poll a local produce job after minimal assets_gate.

Browser still does not generate. This module may call local compose.
Locked heavy with a video Key may call video_generate after the board
「开始出片」click (that click is the human confirm). It does not call
image generate, TTS generate, or stock downloads, and never switches
providers.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import lib.board_production_run as production_run
from lib.board_stage_artifacts import (
    StageArtifactValidationError,
    build_final_review,
    build_review_overview,
    validate_stage_artifact,
)
from lib.board_advance import write_board_stop_overlay
from lib.checkpoint import (
    CheckpointValidationError,
    merge_write_checkpoint,
    read_checkpoint,
)
from lib.paths import PROJECTS_DIR, REPO_ROOT
from lib.review_interrupt import normalize_review_preset

JOB_NAME = "produce_job.json"
OUTPUT_REL = "renders/final.mp4"
GENERATE_RETRY_LIMIT = 5
RETRY_EXHAUSTED_ZH = (
    "同一渠道同一模型已重试 5 次仍失败。项目已冻结。"
    "可回库页继续这个项目，或换模型另开。不会自动换渠道。"
)
COMPOSE_WAIT_ZH = (
    "素材已确认，本机正在按锁定轻度合成成片，大约 1–3 分钟。请留在本页。"
)

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_FAILED = "failed"
STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"

_PAID_PROVIDERS = (
    "agnes",
    "kling",
    "seedance",
    "sora",
    "veo",
    "minimax",
    "runway",
)
_HEAVY_KEY_HINTS = {
    "agnes": ("AGNES_API_KEY", "AGNES_AI_API_KEY"),
    "kling": ("KLING_API_KEY",),
    "seedance": ("FAL_KEY", "FAL_AI_API_KEY"),
    "sora": ("OPENAI_API_KEY",),
    "veo": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "FAL_KEY", "FAL_AI_API_KEY"),
    "minimax": ("FAL_KEY", "FAL_AI_API_KEY"),
    "runway": ("RUNWAY_API_KEY", "RUNWAYML_API_SECRET"),
    "pixverse": ("PIXVERSE_API_KEY", "TOKENHUB_API_KEY"),
}


class ProduceJobError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "produce_job",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.extra = extra or {}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _project_dir(project_id: str, projects_dir: Path | None = None) -> Path:
    return Path(projects_dir or PROJECTS_DIR) / project_id


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for attempt in range(4):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.01 * (2**attempt))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _locked_artifact_revision(project: Path) -> str:
    marker = _read_json(project / "project.json")
    profile = marker.get("production_profile") if isinstance(marker, dict) else {}
    if not isinstance(profile, dict):
        profile = {}
    identity = {
        "production_profile": {
            key: profile.get(key)
            for key in (
                "production_tier",
                "review_mode_preset",
                "review_mode",
                "provider",
                "video_channel",
                "video_model",
                "model",
                "resolution",
            )
        },
        "artifacts": {
            name: _read_json(project / "artifacts" / f"{name}.json")
            for name in (
                "brief",
                "video_plan",
                "segment_cards",
                "asset_ledger",
                "asset_precheck",
            )
        },
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def job_path(project_id: str, *, projects_dir: Path | None = None) -> Path:
    return production_run.produce_job_path(_project_dir(project_id, projects_dir))


def read_job(project_id: str, *, projects_dir: Path | None = None) -> dict[str, Any] | None:
    project = _project_dir(project_id, projects_dir)
    try:
        run = production_run.read_production_run(project)
        run_revision = run.get("run_revision") if run else "1"
        return production_run.read_produce_job(
            project,
            run_revision=run_revision,
        )
    except production_run.ProductionRunError as exc:
        return {
            "version": production_run.JOB_VERSION,
            "project_id": project_id,
            "status": STATUS_PAUSED,
            "code": "run_state_invalid",
            "friendly_zh": "生产状态文件无效，已暂停且不会自动重试。请先修复状态文件。",
            "error": str(exc),
        }


def busy_project_ids(*, projects_dir: Path | None = None) -> list[str]:
    root = Path(projects_dir or PROJECTS_DIR)
    if not root.is_dir():
        return []
    busy: list[str] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        job = read_job(entry.name, projects_dir=root) or {}
        if str(job.get("status") or "") in {STATUS_QUEUED, STATUS_RUNNING}:
            busy.append(entry.name)
    return busy


def write_job(
    project_id: str,
    payload: dict[str, Any],
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    project = _project_dir(project_id, projects_dir)
    run, _created = production_run.load_or_initialize_production_run(
        project,
        persist=True,
    )
    existing = production_run.read_produce_job(
        project,
        run_revision=run["run_revision"],
    ) or {}
    if existing and any(
        field in payload and payload.get(field) != existing.get(field)
        for field in ("stage", "kind", "artifact_revision", "batch_id")
    ):
        existing = {}
    authorization_refs = run.get("authorization_refs") or []
    latest_authorization = (
        authorization_refs[-1]
        if authorization_refs and isinstance(authorization_refs[-1], dict)
        else {}
    )
    body = {
        **existing,
        "version": production_run.JOB_VERSION,
        "project_id": project_id,
        "run_revision": run["run_revision"],
        "stage": existing.get("stage") or "final_compose",
        "kind": existing.get("kind") or "final",
        "artifact_revision": (
            existing.get("artifact_revision") or _locked_artifact_revision(project)
        ),
        "authorization_revision": existing.get("authorization_revision")
        or latest_authorization.get("authorization_revision"),
        "attempt": existing.get("attempt") or 1,
        "provider": existing.get("provider") or run.get("locked_provider") or "",
        "model": existing.get("model") or run.get("locked_model") or "",
        "batch_id": existing.get("batch_id") or "",
        "beat_ids": existing.get("beat_ids") or [],
        "expected_outputs": existing.get("expected_outputs")
        or [OUTPUT_REL, "artifacts/edit_decisions.json"],
        "cost_snapshot": existing.get("cost_snapshot") or {},
        "created_at": existing.get("created_at") or _now(),
        **payload,
        "updated_at": _now(),
    }
    written = production_run.write_produce_job(project, body)
    updated_run = production_run.register_job_summary(run, written)
    production_run.write_production_run(project, updated_run)
    return written


def is_minimal(marker: dict[str, Any]) -> bool:
    profile = marker.get("production_profile") if isinstance(marker, dict) else {}
    if not isinstance(profile, dict):
        profile = {}
    return normalize_review_preset(
        profile.get("review_mode_preset") or profile.get("review_mode")
    ) == "minimal"


def assets_gate_completed(project_id: str, *, projects_dir: Path | None = None) -> bool:
    root = Path(projects_dir or PROJECTS_DIR)
    checkpoint = read_checkpoint(root, project_id, "assets_gate")
    return isinstance(checkpoint, dict) and checkpoint.get("status") == "completed"


def _has_final(project_id: str, *, projects_dir: Path | None = None) -> bool:
    path = _project_dir(project_id, projects_dir) / OUTPUT_REL
    return path.is_file() and path.stat().st_size > 0


def final_ready_for_delivery(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> bool:
    if not _has_final(project_id, projects_dir=projects_dir):
        return False
    project = _project_dir(project_id, projects_dir)
    try:
        run = production_run.read_production_run(project)
    except production_run.ProductionRunError:
        return False
    if run is None:
        return True
    review = _read_json(project / "artifacts" / "final_review.json")
    try:
        validate_stage_artifact("final_review", review)
    except StageArtifactValidationError:
        return False
    artifact_revision = _locked_artifact_revision(project)
    review_metadata = review.get("metadata")
    if not isinstance(review_metadata, dict) or (
        review_metadata.get("artifact_revision") != artifact_revision
    ):
        return False
    final_result = (run.get("stage_results") or {}).get("final_compose")
    checkpoint = read_checkpoint(
        Path(projects_dir or PROJECTS_DIR),
        project_id,
        "final_compose",
    )
    checkpoint_review = (
        (checkpoint.get("artifacts") or {}).get("final_review")
        if isinstance(checkpoint, dict)
        else None
    )
    completed_final_job = any(
        item.get("stage") == "final_compose"
        and item.get("kind") == "final"
        and item.get("artifact_revision") == artifact_revision
        and item.get("status") == STATUS_DONE
        for item in (run.get("task_summaries") or [])
        if isinstance(item, dict)
    )
    return all(
        (
            review.get("status") == "pass",
            str(review.get("output_path") or "") == OUTPUT_REL,
            isinstance(final_result, dict),
            final_result.get("status") == "completed"
            if isinstance(final_result, dict)
            else False,
            "artifacts/final_review.json" in (final_result.get("evidence_refs") or [])
            if isinstance(final_result, dict)
            else False,
            isinstance(checkpoint, dict),
            checkpoint.get("status") == "completed"
            if isinstance(checkpoint, dict)
            else False,
            isinstance(checkpoint_review, dict),
            checkpoint_review.get("status") == "pass"
            if isinstance(checkpoint_review, dict)
            else False,
            str(checkpoint_review.get("output_path") or "") == OUTPUT_REL
            if isinstance(checkpoint_review, dict)
            else False,
            (
                checkpoint_review.get("metadata") or {}
            ).get("artifact_revision")
            == artifact_revision
            if isinstance(checkpoint_review, dict)
            else False,
            completed_final_job,
        )
    )


def _profile(marker: dict[str, Any]) -> dict[str, Any]:
    raw = marker.get("production_profile") if isinstance(marker, dict) else {}
    return raw if isinstance(raw, dict) else {}


def _tier(profile: dict[str, Any]) -> str:
    value = str(profile.get("production_tier") or "light").strip().lower()
    if value in {"light", "medium", "heavy"}:
        return value
    return "light"


def _provider_id(profile: dict[str, Any], brief: dict[str, Any]) -> str:
    raw = " ".join(
        [
            str(profile.get("video_channel") or ""),
            str(profile.get("provider") or ""),
            str(profile.get("video_model") or profile.get("model") or ""),
            str(brief.get("video_channel") or ""),
            str(brief.get("provider") or ""),
        ]
    ).lower()
    for name in _HEAVY_KEY_HINTS:
        if name in raw:
            return name
    return ""


def _present_key_names() -> set[str]:
    names: set[str] = set()
    try:
        from openmontage.mcp.bootstrap.install_state import scan_stock_keys, scan_video_keys

        video = scan_video_keys(repo_root=REPO_ROOT, environ=dict(os.environ))
        stock = scan_stock_keys(repo_root=REPO_ROOT, environ=dict(os.environ))
        names.update(video.get("video_key_names_present") or [])
        names.update(stock.get("stock_key_names_present") or [])
    except Exception:
        pass
    for key, value in os.environ.items():
        if value and str(value).strip():
            names.add(key)
    return names


def key_gate(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Return a paused job payload when locked tier cannot run. None = compose OK."""
    profile = _profile(marker)
    tier = _tier(profile)
    if tier == "light":
        return None
    present = _present_key_names()
    if tier == "medium":
        source = str(profile.get("medium_source") or "user_assets").strip().lower()
        if source != "stock":
            return None
        if "PEXELS_API_KEY" in present or "PIXABAY_API_KEY" in present:
            return {
                "status": STATUS_PAUSED,
                "engine": "stock",
                "tier": tier,
                "code": "stock_not_auto",
                "friendly_zh": (
                    "已锁定中度 Stock，不降为轻度。"
                    "本页不自动下载素材；请刷新可用性后按锁定来源继续。"
                ),
            }
        return {
            "status": STATUS_PAUSED,
            "engine": "stock",
            "tier": tier,
            "code": "stock_key_missing",
            "friendly_zh": (
                "已锁定中度 Stock，但本机没有 Stock Key，不能改走轻度。"
                "请在本页刷新可用性，或回方案改档。"
            ),
        }
    brief = _read_json(_project_dir(project_id, projects_dir) / "artifacts" / "brief.json")
    provider = _provider_id(profile, brief)
    hints = _HEAVY_KEY_HINTS.get(provider) or ()
    has_key = any(name in present for name in hints) if hints else bool(
        present.intersection(
            {name for group in _HEAVY_KEY_HINTS.values() for name in group}
        )
    )
    if not has_key:
        return {
            "status": STATUS_PAUSED,
            "engine": "paid_video",
            "tier": tier,
            "code": "video_key_missing",
            "friendly_zh": (
                "已锁定重度，不降为轻度。本机未检测到对应视频 Key。"
                "请在本页刷新可用性后再试。"
            ),
        }
    if provider not in _PAID_PROVIDERS:
        locked = " / ".join(
            part
            for part in (
                str(profile.get("video_channel") or "").strip(),
                str(profile.get("video_model") or profile.get("model") or "").strip(),
                provider,
            )
            if part
        )
        supported = "Agnes、Kling、Seedance、Sora、Veo、MiniMax、Runway"
        return {
            "status": STATUS_PAUSED,
            "engine": "paid_video",
            "tier": tier,
            "code": "video_channel_missing",
            "friendly_zh": (
                f"已锁定重度{('（' + locked + '）') if locked else ''}。"
                "看板本机分段目前不能走该渠道，也不会改成轻度或其它模型。"
                f"请回方案改成支持的渠道后再点开始出片：{supported}。"
            ),
        }
    return None


def _beat_token(beat: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in beat) or "beat"


def _seg_rel(beat: str, artifact_revision: str = "") -> str:
    suffix = ""
    if artifact_revision:
        digest = hashlib.sha256(artifact_revision.encode("utf-8")).hexdigest()[:12]
        suffix = f"_{digest}"
    return f"assets/video/seg_{_beat_token(beat)}{suffix}.mp4"


def _matching_segment_rel(project: Path, beat: str, artifact_revision: str) -> str:
    overview = _read_json(project / "artifacts" / "review_overview.json")
    try:
        validate_stage_artifact("review_overview", overview)
    except StageArtifactValidationError:
        return ""
    for item in overview.get("overview") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("beat") or "") != beat:
            continue
        if str(item.get("artifact_revision") or "") != artifact_revision:
            continue
        if str(item.get("status") or "") != "completed":
            continue
        rel = str(item.get("output_path") or "").strip()
        if not rel.replace("\\", "/").startswith("assets/video/"):
            continue
        path = project / rel
        if rel and path.is_file() and path.stat().st_size > 0:
            return rel
    return ""


def _sandbox_rel(project_id: str, rel: str) -> str:
    return f"{project_id}/{rel.replace(chr(92), '/')}"


def _aspect_ratio(width: int, height: int) -> str:
    if height > width:
        return "9:16"
    if width == height:
        return "1:1"
    return "16:9"


def _frame_size(profile: dict[str, Any]) -> tuple[int, int]:
    resolution = str(profile.get("resolution") or "1080x1920")
    if "x" in resolution:
        try:
            width, height = (int(part) for part in resolution.lower().split("x", 1))
            return width, height
        except ValueError:
            pass
    return 1080, 1920


def _cards_by_beat(project: Path) -> dict[str, dict[str, Any]]:
    cards = _read_json(project / "artifacts" / "segment_cards.json")
    out: dict[str, dict[str, Any]] = {}
    for item in cards.get("segments") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("beat") or item.get("id") or "").strip()
        if key:
            out[key] = item
    return out


def _segment_prompt(brief: dict[str, Any], card: dict[str, Any], beat: str) -> str:
    parts = [
        str(brief.get("theme") or "").strip(),
        str(card.get("shot_plan_zh") or "").strip(),
        str(card.get("copy_plan_zh") or "").strip(),
    ]
    text = "。".join(part for part in parts if part)
    return text or f"商品展示镜头 {beat}"


def _kling_duration(seconds: float) -> str:
    value = int(round(float(seconds) or 5))
    return str(min(15, max(3, value)))


def _video_extras(
    provider: str,
    still_path: str,
    duration: float,
    aspect: str,
) -> dict[str, Any]:
    if provider == "agnes":
        return {
            "operation": "image_to_video",
            "duration": duration,
            "aspect_ratio": aspect,
            "image_path": still_path,
        }
    if provider == "kling":
        return {
            "operation": "image_to_video",
            "duration": _kling_duration(duration),
            "reference_image_path": still_path,
        }
    return {
        "operation": "image_to_video",
        "duration": duration,
        "aspect_ratio": aspect,
        "image_path": still_path,
        "reference_image_path": still_path,
    }


def _plan_beats(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> list[dict[str, Any]]:
    project = _project_dir(project_id, projects_dir)
    plan = _read_json(project / "artifacts" / "video_plan.json")
    ledger = _read_json(project / "artifacts" / "asset_ledger.json")
    brief = _read_json(project / "artifacts" / "brief.json")
    profile = _profile(_read_json(project / "project.json"))
    cards = _cards_by_beat(project)
    segments = [item for item in (plan.get("segments") or []) if isinstance(item, dict)]
    if not segments:
        raise ProduceJobError("缺少 video_plan 分段，无法生成。", code="no_plan")
    by_beat: dict[str, str] = {}
    for entry in ledger.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        beats = entry.get("beats") or []
        if isinstance(beats, str):
            beats = [part.strip() for part in beats.split(",") if part.strip()]
        for beat in beats:
            by_beat[str(beat)] = path
    duration = float(brief.get("duration_seconds") or profile.get("duration_seconds") or 15)
    fallback = max(2.0, duration / max(1, len(segments)))
    rows: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        beat = str(segment.get("beat") or segment.get("id") or f"beat_{index + 1:02d}")
        still = str(segment.get("ref_image") or by_beat.get(beat) or "").strip()
        if not still:
            raise ProduceJobError(f"分段 {beat} 没有锁定图片。", code="missing_still")
        rows.append(
            {
                "beat": beat,
                "still": still,
                "span": _span_seconds(segment.get("t") or segment.get("time"), fallback),
                "prompt": _segment_prompt(brief, cards.get(beat) or {}, beat),
            }
        )
    return rows


def _clock_seconds(token: str) -> float:
    text = str(token or "").strip().rstrip("sS")
    if not text:
        return 0.0
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except ValueError:
        return 0.0


def _span_seconds(raw: Any, fallback: float) -> float:
    text = str(raw or "").strip()
    if not text or "-" not in text:
        return fallback
    left, right = text.split("-", 1)
    span = _clock_seconds(right) - _clock_seconds(left)
    return span if span >= 0.5 else fallback


def build_compose_bundle(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    project = _project_dir(project_id, projects_dir)
    plan = _read_json(project / "artifacts" / "video_plan.json")
    ledger = _read_json(project / "artifacts" / "asset_ledger.json")
    brief = _read_json(project / "artifacts" / "brief.json")
    marker = _read_json(project / "project.json")
    profile = _profile(marker)
    artifact_revision = _locked_artifact_revision(project)
    segments = [item for item in (plan.get("segments") or []) if isinstance(item, dict)]
    if not segments:
        raise ProduceJobError("缺少 video_plan 分段，无法合成。", code="no_plan")
    by_beat: dict[str, str] = {}
    assets: list[dict[str, Any]] = []
    for entry in ledger.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        beats = entry.get("beats") or []
        if isinstance(beats, str):
            beats = [part.strip() for part in beats.split(",") if part.strip()]
        for beat in beats:
            by_beat[str(beat)] = path
        asset_id = f"img_{len(assets) + 1:02d}"
        assets.append({"id": asset_id, "path": path, "type": "image", "kind": "image"})
        by_beat[f"__path__{path}"] = asset_id
    if not by_beat:
        raise ProduceJobError("账本没有可用图片，无法合成。", code="empty_ledger")
    duration = float(brief.get("duration_seconds") or profile.get("duration_seconds") or 15)
    fallback = max(2.0, duration / max(1, len(segments)))
    cuts: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        beat = str(segment.get("beat") or segment.get("id") or f"beat_{index + 1:02d}")
        still = str(segment.get("ref_image") or by_beat.get(beat) or "").strip()
        if not still:
            raise ProduceJobError(f"分段 {beat} 没有锁定图片。", code="missing_still")
        video_rel = _matching_segment_rel(project, beat, artifact_revision)
        video_path = project / video_rel if video_rel else None
        source = still
        kind = "image"
        if (
            video_path is not None
            and video_path.is_file()
            and video_path.stat().st_size > 0
        ):
            source = video_rel
            kind = "video"
            assets.append(
                {
                    "id": f"vid_{index + 1:02d}",
                    "path": video_rel,
                    "type": "video",
                    "kind": "video",
                }
            )
        span = _span_seconds(segment.get("t") or segment.get("time"), fallback)
        cuts.append(
            {
                "id": f"c{index + 1:02d}",
                "source": source,
                "in_seconds": 0,
                "out_seconds": round(span, 3),
                "reason": beat,
                "kind": kind,
            }
        )
    runtime = str(profile.get("render_runtime") or "remotion").strip().lower() or "remotion"
    all_video = bool(cuts) and all(str(cut.get("kind") or "") == "video" for cut in cuts)
    if all_video:
        # Paid beat clips are already rendered; concat them. Remotion cannot
        # load local file:// sources on this path.
        runtime = "ffmpeg"
    family = str(profile.get("renderer_family") or "").strip()
    if not family and runtime == "remotion":
        family = "product-reveal"
    width, height = _frame_size(profile)
    edit = {
        "version": "1.0",
        "project_id": project_id,
        "render_runtime": runtime,
        "cuts": cuts,
        "audio": {},
        "subtitles": {"enabled": False},
        "metadata": {
            "compose_target": {"width": width, "height": height, "fit": "cover"},
            "board_produce": True,
        },
    }
    if family:
        edit["renderer_family"] = family
    manifest = {"version": "1.0", "assets": assets, "total_cost_usd": 0.0}
    return {"edit_decisions": edit, "asset_manifest": manifest}


def _record_completed_stage(
    project_id: str,
    stage: str,
    artifact_name: str,
    artifact: dict[str, Any],
    *,
    projects_dir: Path | None,
) -> None:
    root = Path(projects_dir or PROJECTS_DIR)
    merge_write_checkpoint(
        root,
        project_id,
        stage,
        "completed",
        {artifact_name: artifact},
        pipeline_type="bootstrap-commercial",
        human_approval_required=False,
        human_approved=False,
        metadata_patch={"needs_user_decision": False, "auto_completed": True},
    )
    project = _project_dir(project_id, projects_dir)
    run = production_run.read_production_run(project)
    if run is None:
        return
    updated = production_run.record_stage_result(
        run,
        stage,
        "completed",
        checkpoint_refs=[f"checkpoint_{stage}.json"],
        evidence_refs=[f"artifacts/{artifact_name}.json"],
        human_approved=False,
    )
    production_run.write_production_run(project, updated)


def _materialize_review_overview(
    project_id: str,
    beats: list[dict[str, Any]],
    *,
    provider: str,
    model: str,
    artifact_revision: str,
    projects_dir: Path | None,
    completed: bool,
) -> dict[str, Any]:
    project = _project_dir(project_id, projects_dir)
    rows: list[dict[str, Any]] = []
    for row in beats:
        beat = str(row["beat"])
        rel = _matching_segment_rel(project, beat, artifact_revision) or _seg_rel(
            beat,
            artifact_revision,
        )
        path = project / rel
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        rows.append(
            {
                "beat": beat,
                "output_path": rel,
                "status": "completed",
                "artifact_revision": artifact_revision,
                "provider": provider,
                "model": model,
            }
        )
    if completed and len(rows) != len(beats):
        raise ProduceJobError(
            "分段证据不完整，不能完成 segment_build。",
            code="segment_evidence_incomplete",
        )
    artifact = build_review_overview(
        rows,
        batches=[],
        extra={
            "artifact_revision": artifact_revision,
            "provider": provider,
            "model": model,
            "status": "completed" if completed else "in_progress",
        },
    )
    _write_json(project / "artifacts" / "review_overview.json", artifact)
    if completed:
        _record_completed_stage(
            project_id,
            "segment_build",
            "review_overview",
            artifact,
            projects_dir=projects_dir,
        )
    return artifact


def _materialize_final_evidence(
    project_id: str,
    *,
    projects_dir: Path | None,
) -> dict[str, Any]:
    project = _project_dir(project_id, projects_dir)
    final_path = project / OUTPUT_REL
    if not final_path.is_file() or final_path.stat().st_size <= 0:
        raise ProduceJobError("成片文件缺失，不能完成 final_compose。", code="final_missing")
    run = production_run.read_production_run(project)
    if run is None:
        raise ProduceJobError(
            "缺少生产运行记录，不能为新任务补写终稿证据。",
            code="final_run_missing",
        )
    artifact_revision = _locked_artifact_revision(project)
    current_job = production_run.read_produce_job(
        project,
        run_revision=run["run_revision"],
    )
    if not isinstance(current_job, dict) or any(
        (
            current_job.get("stage") != "final_compose",
            current_job.get("kind") != "final",
            current_job.get("artifact_revision") != artifact_revision,
        )
    ):
        raise ProduceJobError(
            "终稿任务与当前输入版本不一致，旧成片未被重新认领。",
            code="final_revision_stale",
        )
    existing = _read_json(project / "artifacts" / "final_review.json")
    if existing:
        try:
            validate_stage_artifact("final_review", existing)
        except StageArtifactValidationError as exc:
            raise ProduceJobError(
                f"已有终稿证据无效：{exc}",
                code="final_review_invalid",
            ) from exc
        existing_metadata = existing.get("metadata")
        existing_revision = (
            existing_metadata.get("artifact_revision")
            if isinstance(existing_metadata, dict)
            else None
        )
        if existing_revision != artifact_revision:
            raise ProduceJobError(
                "已有终稿证据属于旧输入版本，未开放交付。",
                code="final_revision_stale",
            )
    final_result = (run.get("stage_results") or {}).get("final_compose") if run else {}
    checkpoint = read_checkpoint(
        Path(projects_dir or PROJECTS_DIR),
        project_id,
        "final_compose",
    )
    if (
        existing.get("status") == "pass"
        and existing.get("output_path") == OUTPUT_REL
        and isinstance(final_result, dict)
        and final_result.get("status") == "completed"
        and isinstance(checkpoint, dict)
        and checkpoint.get("status") == "completed"
    ):
        return existing
    marker = _read_json(project / "project.json")
    profile = _profile(marker)
    artifact = build_final_review(
        OUTPUT_REL,
        status="pass",
        checks={
            "technical_probe": {
                "file_exists": True,
                "non_empty": True,
                "size_bytes": final_path.stat().st_size,
                "verification_level": "file_presence",
            }
        },
        metadata={
            "artifact_revision": artifact_revision,
            "provider": str(profile.get("provider") or profile.get("video_channel") or ""),
            "model": str(profile.get("video_model") or profile.get("model") or ""),
        },
    )
    _write_json(project / "artifacts" / "final_review.json", artifact)
    _record_completed_stage(
        project_id,
        "final_compose",
        "final_review",
        artifact,
        projects_dir=projects_dir,
    )
    return artifact


def _refresh_overlay(
    project_id: str,
    friendly_zh: str,
    *,
    projects_dir: Path | None = None,
    paused: bool = False,
) -> None:
    marker = _read_json(_project_dir(project_id, projects_dir) / "project.json")
    stop = marker.get("board_stop") if isinstance(marker.get("board_stop"), dict) else {}
    stage = str(stop.get("stage") or "delivery_signoff")
    write_board_stop_overlay(project_id, stage, projects_dir=projects_dir)
    marker = _read_json(_project_dir(project_id, projects_dir) / "project.json")
    stop = marker.get("board_stop") if isinstance(marker.get("board_stop"), dict) else {}
    if not stop:
        return
    stop["producing_wait"] = not paused
    stop["paused"] = bool(paused)
    stop["needs_user_decision"] = bool(paused)
    stop["decision_title_zh"] = "已暂停" if paused else "制作中"
    stop["decision_prompt_zh"] = friendly_zh
    stop["decision_options"] = []
    marker["board_stop"] = stop
    _write_json(_project_dir(project_id, projects_dir) / "project.json", marker)


def _fail_job(
    project_id: str,
    *,
    projects_dir: Path | None,
    engine: str,
    tier: str,
    code: str,
    friendly_zh: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "status": STATUS_FAILED,
        "engine": engine,
        "tier": tier,
        "code": code,
        "friendly_zh": friendly_zh,
    }
    if extra:
        payload.update(extra)
    try:
        job = write_job(project_id, payload, projects_dir=projects_dir)
    except (production_run.ProductionRunError, OSError) as exc:
        job = {
            "version": production_run.JOB_VERSION,
            "project_id": project_id,
            **payload,
            "code": "run_state_invalid",
            "error": str(exc),
            "friendly_zh": "生产状态无法安全写入，已暂停且不会启动或重试任务。",
        }
    _refresh_overlay(project_id, friendly_zh, projects_dir=projects_dir, paused=True)
    return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}


def call_video_generate_with_retries(
    generate: Callable[..., Any],
    *args: Any,
    dest: Path | None = None,
) -> Any:
    """Retry the same provider/model up to GENERATE_RETRY_LIMIT times."""
    last_error = "分段生成失败，未换渠道。"
    last_result: Any = None
    for attempt in range(1, GENERATE_RETRY_LIMIT + 1):
        try:
            last_result = generate(*args)
        except Exception as exc:
            last_error = str(exc) or last_error
            if attempt >= GENERATE_RETRY_LIMIT:
                raise ProduceJobError(
                    f"{RETRY_EXHAUSTED_ZH} 最后错误：{last_error}",
                    code="video_generate_failed",
                    extra={
                        "retry_exhausted": True,
                        "generate_attempts": attempt,
                    },
                ) from exc
            continue
        failed = isinstance(last_result, dict) and last_result.get("success") is False
        missing = dest is not None and (
            not dest.is_file() or dest.stat().st_size <= 0
        )
        if failed:
            last_error = str(
                (last_result or {}).get("error") if isinstance(last_result, dict) else last_error
            ) or last_error
        if failed or missing:
            if attempt >= GENERATE_RETRY_LIMIT:
                raise ProduceJobError(
                    f"{RETRY_EXHAUSTED_ZH} 最后错误：{last_error}",
                    code="video_generate_failed",
                    extra={
                        "retry_exhausted": True,
                        "generate_attempts": attempt,
                    },
                )
            continue
        return last_result
    raise ProduceJobError(
        RETRY_EXHAUSTED_ZH,
        code="video_generate_failed",
        extra={"retry_exhausted": True, "generate_attempts": GENERATE_RETRY_LIMIT},
    )


def _wait_copy(project_id: str, marker: dict[str, Any], *, projects_dir: Path | None) -> str:
    from lib.board_advance import producing_wait_copy_zh

    return producing_wait_copy_zh(marker, project_id=project_id, projects_dir=projects_dir)


def _start_compose(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    engine: str = "compose",
    wait_copy: str = "",
) -> dict[str, Any]:
    tier = _tier(_profile(marker))
    try:
        bundle = build_compose_bundle(project_id, projects_dir=projects_dir)
    except ProduceJobError as exc:
        return _fail_job(
            project_id,
            projects_dir=projects_dir,
            engine=engine,
            tier=tier,
            code=exc.code,
            friendly_zh=exc.safe_message,
        )
    art = _project_dir(project_id, projects_dir) / "artifacts"
    _write_json(art / "edit_decisions.json", bundle["edit_decisions"])
    _write_json(art / "asset_manifest.json", bundle["asset_manifest"])
    friendly = wait_copy or COMPOSE_WAIT_ZH
    try:
        artifact_revision = _locked_artifact_revision(
            _project_dir(project_id, projects_dir)
        )
        write_job(
            project_id,
            {
                "stage": "final_compose",
                "kind": "final",
                "artifact_revision": artifact_revision,
                "batch_id": "",
                "beat_ids": [],
                "status": STATUS_QUEUED,
                "engine": engine,
                "tier": tier,
                "job_id": "",
                "output_path": OUTPUT_REL,
                "expected_outputs": [OUTPUT_REL, "artifacts/final_review.json"],
                "friendly_zh": friendly,
            },
            projects_dir=projects_dir,
        )
    except (production_run.ProductionRunError, OSError) as exc:
        message = "生产任务无法安全登记，未启动合成。请先修复生产状态文件。"
        _refresh_overlay(project_id, message, projects_dir=projects_dir, paused=True)
        return {
            "action": "produce_paused",
            "status": STATUS_PAUSED,
            "job": {
                "status": STATUS_PAUSED,
                "code": "run_state_invalid",
                "friendly_zh": message,
                "error": str(exc),
            },
        }
    starter = compose_start
    if starter is None:
        from openmontage.mcp.media.tools import compose_start as starter
    os.environ.setdefault("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    try:
        started = starter(
            json.dumps(bundle["edit_decisions"], ensure_ascii=False),
            json.dumps(bundle["asset_manifest"], ensure_ascii=False),
            _sandbox_rel(project_id, OUTPUT_REL),
        )
    except Exception as exc:
        return _fail_job(
            project_id,
            projects_dir=projects_dir,
            engine=engine,
            tier=tier,
            code="compose_start_failed",
            friendly_zh=f"本机无法启动合成：{exc}",
            extra={"error": str(exc)},
        )
    if not isinstance(started, dict):
        started = {}
    job = write_job(
        project_id,
        {
            "status": STATUS_QUEUED,
            "engine": engine,
            "tier": tier,
            "job_id": str(started.get("job_id") or ""),
            "output_path": str(started.get("output_path") or OUTPUT_REL),
            "friendly_zh": friendly,
        },
        projects_dir=projects_dir,
    )
    _refresh_overlay(project_id, job["friendly_zh"], projects_dir=projects_dir)
    return {"action": "produce_start", "status": STATUS_QUEUED, "job": job, "started": started}


def _wait_compose_done(
    project_id: str,
    started: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
) -> None:
    if _has_final(project_id, projects_dir=projects_dir):
        return
    compose_id = str(started.get("job_id") or "")
    if not compose_id:
        if _has_final(project_id, projects_dir=projects_dir):
            return
        raise ProduceJobError("合成已启动但没有任务号，也没有成片。", code="compose_no_job")
    reader = job_status
    if reader is None:
        from openmontage.mcp.media.tools import job_status as reader
    for _ in range(3600):
        if _has_final(project_id, projects_dir=projects_dir):
            return
        remote = reader(compose_id)
        if not isinstance(remote, dict):
            remote = {}
        remote_status = str(remote.get("status") or "")
        if remote_status in {"failed", "error"}:
            raise ProduceJobError(
                str(remote.get("error") or "合成失败，请留在本页重试。"),
                code="compose_failed",
            )
        if remote_status in {"completed", "done", "succeeded"}:
            if _has_final(project_id, projects_dir=projects_dir):
                return
            raise ProduceJobError(
                "合成报告完成，但还没有成片文件。请留在本页重试。",
                code="final_missing",
            )
        time.sleep(1)
    raise ProduceJobError("合成等待超时。请留在本页重试。", code="compose_timeout")


def _run_paid_pipeline(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    video_generate: Callable[..., dict[str, Any]] | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
) -> None:
    profile = _profile(marker)
    brief = _read_json(_project_dir(project_id, projects_dir) / "artifacts" / "brief.json")
    provider = _provider_id(profile, brief)
    model = str(profile.get("video_model") or profile.get("model") or "").strip()
    beats = _plan_beats(project_id, projects_dir=projects_dir)
    width, height = _frame_size(profile)
    aspect = _aspect_ratio(width, height)
    wait_copy = _wait_copy(project_id, marker, projects_dir=projects_dir)
    generate = video_generate
    if generate is None:
        from openmontage.mcp.providers_video.tools import video_generate as generate
    project = _project_dir(project_id, projects_dir)
    artifact_revision = _locked_artifact_revision(project)
    total = len(beats)
    for index, row in enumerate(beats, start=1):
        beat = str(row["beat"])
        matched_rel = _matching_segment_rel(project, beat, artifact_revision)
        if matched_rel:
            write_job(
                project_id,
                {
                    "stage": "segment_build",
                    "kind": "segment",
                    "artifact_revision": artifact_revision,
                    "batch_id": beat,
                    "beat_ids": [beat],
                    "expected_outputs": [
                        matched_rel,
                        "artifacts/review_overview.json",
                    ],
                    "status": STATUS_DONE,
                    "engine": "paid_video",
                    "tier": "heavy",
                    "provider": provider,
                    "model": model,
                    "beat": beat,
                    "reused": True,
                    "friendly_zh": f"第 {index}/{total} 段复用当前版本证据。",
                },
                projects_dir=projects_dir,
            )
            continue
        dest_rel = _seg_rel(beat, artifact_revision)
        dest = project / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        still_abs = str((project / str(row["still"])).resolve())
        extras = _video_extras(provider, still_abs, float(row["span"]), aspect)
        if model:
            extras["model"] = model
        friendly = f"第 {index}/{total} 段正在生成。{wait_copy}"
        write_job(
            project_id,
            {
                "stage": "segment_build",
                "kind": "segment",
                "artifact_revision": artifact_revision,
                "batch_id": beat,
                "beat_ids": [beat],
                "expected_outputs": [
                    dest_rel,
                    "artifacts/review_overview.json",
                ],
                "status": STATUS_RUNNING,
                "engine": "paid_video",
                "tier": "heavy",
                "provider": provider,
                "model": model,
                "beat": beat,
                "friendly_zh": friendly,
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(project_id, friendly, projects_dir=projects_dir)
        result = call_video_generate_with_retries(
            generate,
            provider,
            str(row["prompt"]),
            _sandbox_rel(project_id, dest_rel),
            json.dumps(extras, ensure_ascii=False),
            True,
            True,
            dest=dest,
        )
        if not dest.is_file() or dest.stat().st_size <= 0:
            raise ProduceJobError(
                f"分段 {row['beat']} 生成结束但没有视频文件，未换渠道。",
                code="segment_missing",
            )
        _materialize_review_overview(
            project_id,
            beats,
            provider=provider,
            model=model,
            artifact_revision=artifact_revision,
            projects_dir=projects_dir,
            completed=False,
        )
        cost_snapshot = {}
        if isinstance(result, dict):
            cost_snapshot = {
                key: result[key]
                for key in ("estimated_cost_usd", "cost_usd")
                if result.get(key) is not None
            }
        write_job(
            project_id,
            {
                "stage": "segment_build",
                "kind": "segment",
                "artifact_revision": artifact_revision,
                "batch_id": beat,
                "beat_ids": [beat],
                "expected_outputs": [
                    dest_rel,
                    "artifacts/review_overview.json",
                ],
                "status": STATUS_DONE,
                "engine": "paid_video",
                "tier": "heavy",
                "provider": provider,
                "model": model,
                "beat": beat,
                "cost_snapshot": cost_snapshot,
                "friendly_zh": f"第 {index}/{total} 段已生成。",
            },
            projects_dir=projects_dir,
        )
    _materialize_review_overview(
        project_id,
        beats,
        provider=provider,
        model=model,
        artifact_revision=artifact_revision,
        projects_dir=projects_dir,
        completed=True,
    )
    launched = _start_compose(
        project_id,
        marker,
        projects_dir=projects_dir,
        compose_start=compose_start,
        engine="paid_video",
        wait_copy=wait_copy,
    )
    if launched.get("status") == STATUS_FAILED:
        raise ProduceJobError(
            str((launched.get("job") or {}).get("friendly_zh") or "合成失败。"),
            code=str((launched.get("job") or {}).get("code") or "compose_start_failed"),
        )
    started = launched.get("started") if isinstance(launched.get("started"), dict) else {}
    _wait_compose_done(
        project_id,
        started,
        projects_dir=projects_dir,
        job_status=job_status,
    )
    _materialize_final_evidence(project_id, projects_dir=projects_dir)


def maybe_start(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    video_generate: Callable[..., dict[str, Any]] | None = None,
    paid_inline: bool = False,
    job_status: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if _has_final(project_id, projects_dir=projects_dir):
        project = _project_dir(project_id, projects_dir)
        try:
            if production_run.read_production_run(project) is not None:
                _materialize_final_evidence(project_id, projects_dir=projects_dir)
        except (
            production_run.ProductionRunError,
            ProduceJobError,
            CheckpointValidationError,
            OSError,
        ) as exc:
            return _fail_job(
                project_id,
                projects_dir=projects_dir,
                engine="compose",
                tier=_tier(_profile(marker)),
                code="final_evidence_failed",
                friendly_zh=f"成片存在，但终稿证据写入失败，未开放交付：{exc}",
            )
        return {"action": "", "status": STATUS_DONE, "skipped": True}
    if not is_minimal(marker) or not assets_gate_completed(
        project_id, projects_dir=projects_dir
    ):
        return {"action": "", "status": STATUS_SKIPPED, "skipped": True}
    existing = read_job(project_id, projects_dir=projects_dir) or {}
    status = str(existing.get("status") or "")
    if status in {STATUS_QUEUED, STATUS_RUNNING, STATUS_FAILED}:
        return {"action": "", "status": status, "job": existing, "skipped": True}
    if status == STATUS_PAUSED and str(existing.get("code") or "") in {
        "orphaned",
        "run_state_invalid",
    }:
        return {"action": "", "status": status, "job": existing, "skipped": True}

    gated = key_gate(project_id, marker, projects_dir=projects_dir)
    if status == STATUS_PAUSED and gated is not None:
        return {"action": "", "status": STATUS_PAUSED, "job": existing, "skipped": True}
    if gated is not None:
        job = write_job(project_id, gated, projects_dir=projects_dir)
        _refresh_overlay(
            project_id,
            str(gated.get("friendly_zh") or ""),
            projects_dir=projects_dir,
            paused=True,
        )
        return {"action": "produce_paused", "status": STATUS_PAUSED, "job": job}

    profile = _profile(marker)
    tier = _tier(profile)
    wait_copy = _wait_copy(project_id, marker, projects_dir=projects_dir)
    if tier != "heavy":
        return _start_compose(
            project_id,
            marker,
            projects_dir=projects_dir,
            compose_start=compose_start,
            engine="compose",
            wait_copy=COMPOSE_WAIT_ZH,
        )

    brief = _read_json(_project_dir(project_id, projects_dir) / "artifacts" / "brief.json")
    provider = _provider_id(profile, brief)
    artifact_revision = _locked_artifact_revision(
        _project_dir(project_id, projects_dir)
    )
    reservation = {
        "stage": "final_compose",
        "kind": "final",
        "artifact_revision": artifact_revision,
        "batch_id": "",
        "beat_ids": [],
        "status": STATUS_QUEUED,
        "engine": "paid_video",
        "tier": "heavy",
        "provider": provider,
        "job_id": "",
        "output_path": OUTPUT_REL,
        "expected_outputs": [OUTPUT_REL, "artifacts/final_review.json"],
        "friendly_zh": wait_copy,
    }
    try:
        write_job(project_id, reservation, projects_dir=projects_dir)
    except (production_run.ProductionRunError, OSError) as exc:
        message = "生产任务无法安全登记，未调用视频模型。请先修复生产状态文件。"
        _refresh_overlay(project_id, message, projects_dir=projects_dir, paused=True)
        return {
            "action": "produce_paused",
            "status": STATUS_PAUSED,
            "job": {
                "status": STATUS_PAUSED,
                "code": "run_state_invalid",
                "friendly_zh": message,
                "error": str(exc),
            },
        }

    def worker(_job_id: str = "") -> None:
        try:
            _run_paid_pipeline(
                project_id,
                marker,
                projects_dir=projects_dir,
                compose_start=compose_start,
                video_generate=video_generate,
                job_status=job_status,
            )
            if _has_final(project_id, projects_dir=projects_dir):
                write_job(
                    project_id,
                    {
                        "status": STATUS_DONE,
                        "engine": "paid_video",
                        "tier": "heavy",
                        "provider": provider,
                        "friendly_zh": "成片已就绪，请在本页预览并导出。",
                    },
                    projects_dir=projects_dir,
                )
        except ProduceJobError as exc:
            extra = dict(exc.extra or {})
            _fail_job(
                project_id,
                projects_dir=projects_dir,
                engine="paid_video",
                tier="heavy",
                code=exc.code,
                friendly_zh=exc.safe_message,
                extra=extra or None,
            )
            raise
        except Exception as exc:
            _fail_job(
                project_id,
                projects_dir=projects_dir,
                engine="paid_video",
                tier="heavy",
                code="paid_pipeline_failed",
                friendly_zh=f"分段生成失败，未换渠道：{exc}",
                extra={"error": str(exc)},
            )
            raise

    if paid_inline:
        try:
            worker()
        except Exception:
            job = read_job(project_id, projects_dir=projects_dir) or {}
            return {
                "action": "produce_failed",
                "status": str(job.get("status") or STATUS_FAILED),
                "job": job,
            }
        job = read_job(project_id, projects_dir=projects_dir) or {}
        return {
            "action": "produce_start",
            "status": str(job.get("status") or STATUS_QUEUED),
            "job": job,
        }

    from openmontage.mcp.common.jobs import create_job, start_background

    try:
        media_job = create_job("board_paid_video", meta={"project_id": project_id})
    except Exception as exc:
        return _fail_job(
            project_id,
            projects_dir=projects_dir,
            engine="paid_video",
            tier="heavy",
            code="background_job_start_failed",
            friendly_zh=f"本机无法登记后台任务，未调用视频模型：{exc}",
        )
    job = write_job(
        project_id,
        {
            "status": STATUS_QUEUED,
            "engine": "paid_video",
            "tier": "heavy",
            "provider": provider,
            "job_id": str(media_job.get("job_id") or ""),
            "friendly_zh": wait_copy,
        },
        projects_dir=projects_dir,
    )
    _refresh_overlay(project_id, wait_copy, projects_dir=projects_dir)
    try:
        start_background(str(media_job["job_id"]), worker)
    except Exception as exc:
        return _fail_job(
            project_id,
            projects_dir=projects_dir,
            engine="paid_video",
            tier="heavy",
            code="background_job_start_failed",
            friendly_zh=f"本机无法启动后台任务，未调用视频模型：{exc}",
        )
    return {"action": "produce_start", "status": STATUS_QUEUED, "job": job}


def _reconcile_missing_background(
    project_id: str,
    job: dict[str, Any],
    *,
    projects_dir: Path | None,
) -> dict[str, Any]:
    project = _project_dir(project_id, projects_dir)
    recovered = production_run.reconcile_orphaned_job(
        job,
        project,
        background_job_exists=False,
    )
    written = write_job(project_id, recovered, projects_dir=projects_dir)
    status = str(written.get("status") or "")
    if status == STATUS_DONE:
        return {"action": "produce_done", "status": status, "job": written}
    friendly = (
        "原后台任务记录已失联，证据尚不完整。已暂停且不会自动重试或重复收费。"
    )
    written = write_job(
        project_id,
        {**written, "friendly_zh": friendly},
        projects_dir=projects_dir,
    )
    _refresh_overlay(project_id, friendly, projects_dir=projects_dir, paused=True)
    return {"action": "produce_paused", "status": STATUS_PAUSED, "job": written}


def _finalize_completed_job(
    project_id: str,
    job: dict[str, Any],
    *,
    projects_dir: Path | None,
) -> dict[str, Any]:
    try:
        _materialize_final_evidence(project_id, projects_dir=projects_dir)
    except (
        production_run.ProductionRunError,
        ProduceJobError,
        CheckpointValidationError,
        OSError,
    ) as exc:
        return _fail_job(
            project_id,
            projects_dir=projects_dir,
            engine=str(job.get("engine") or "compose"),
            tier=str(job.get("tier") or "light"),
            code="final_evidence_failed",
            friendly_zh=f"成片存在，但终稿证据写入失败，未开放交付：{exc}",
        )
    written = write_job(
        project_id,
        {
            **job,
            "status": STATUS_DONE,
            "friendly_zh": "成片已就绪，请在本页预览并导出。",
        },
        projects_dir=projects_dir,
    )
    return {"action": "produce_done", "status": STATUS_DONE, "job": written}


def poll(
    project_id: str,
    *,
    projects_dir: Path | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    job = read_job(project_id, projects_dir=projects_dir)
    if not job:
        return {"action": "", "status": ""}
    if _has_final(project_id, projects_dir=projects_dir):
        return _finalize_completed_job(
            project_id,
            job,
            projects_dir=projects_dir,
        )
    if job.get("status") in {STATUS_PAUSED, STATUS_FAILED, STATUS_DONE}:
        return {"action": "", "status": str(job.get("status") or ""), "job": job}
    compose_id = str(job.get("job_id") or "")
    if not compose_id:
        return _reconcile_missing_background(
            project_id,
            job,
            projects_dir=projects_dir,
        )
    reader = job_status
    if reader is None:
        from openmontage.mcp.media.tools import job_status as reader
    try:
        remote = reader(compose_id)
    except Exception as exc:
        error_code = str(getattr(exc, "code", "") or "").lower()
        error_text = str(exc).lower()
        if error_code == "not_found" or "job not found" in error_text:
            return _reconcile_missing_background(
                project_id,
                job,
                projects_dir=projects_dir,
            )
        job = write_job(
            project_id,
            {
                **job,
                "status": STATUS_FAILED,
                "code": "compose_status_failed",
                "friendly_zh": f"无法读取合成进度：{exc}",
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(
            project_id,
            job["friendly_zh"],
            projects_dir=projects_dir,
            paused=True,
        )
        return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}
    if not isinstance(remote, dict):
        remote = {}
    remote_status = str(remote.get("status") or "")
    if remote_status in {"failed", "error"}:
        friendly = str(remote.get("error") or "合成失败，请留在本页重试。")
        job = write_job(
            project_id,
            {
                **job,
                "status": STATUS_FAILED,
                "code": "compose_failed",
                "friendly_zh": friendly,
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(project_id, friendly, projects_dir=projects_dir, paused=True)
        return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}
    if remote_status in {"completed", "done", "succeeded"}:
        if _has_final(project_id, projects_dir=projects_dir):
            return _finalize_completed_job(
                project_id,
                projects_dir=projects_dir,
                job=job,
            )
        job = write_job(
            project_id,
            {
                **job,
                "status": STATUS_FAILED,
                "code": "final_missing",
                "friendly_zh": "合成报告完成，但还没有成片文件。请留在本页重试。",
            },
            projects_dir=projects_dir,
        )
        _refresh_overlay(
            project_id, job["friendly_zh"], projects_dir=projects_dir, paused=True
        )
        return {"action": "produce_failed", "status": STATUS_FAILED, "job": job}
    progress = remote.get("progress")
    engine = str(job.get("engine") or "compose")
    if engine == "paid_video":
        marker = _read_json(_project_dir(project_id, projects_dir) / "project.json")
        friendly = str(job.get("friendly_zh") or "") or _wait_copy(
            project_id, marker, projects_dir=projects_dir
        )
    else:
        friendly = "本机正在合成成片，大约 1–3 分钟。请留在本页。"
        if progress not in (None, ""):
            try:
                friendly = (
                    f"本机正在合成成片（{int(float(progress) * 100)}%），"
                    "大约还需要一两分钟。请留在本页。"
                )
            except (TypeError, ValueError):
                pass
    job = write_job(
        project_id,
        {**job, "status": STATUS_RUNNING, "friendly_zh": friendly},
        projects_dir=projects_dir,
    )
    _refresh_overlay(project_id, friendly, projects_dir=projects_dir)
    return {"action": "produce_poll", "status": STATUS_RUNNING, "job": job}


def sync_produce(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
    video_generate: Callable[..., dict[str, Any]] | None = None,
    paid_inline: bool = False,
) -> dict[str, Any]:
    started = maybe_start(
        project_id,
        marker,
        projects_dir=projects_dir,
        compose_start=compose_start,
        video_generate=video_generate,
        paid_inline=paid_inline,
        job_status=job_status,
    )
    if started.get("action"):
        return started
    return poll(project_id, projects_dir=projects_dir, job_status=job_status)

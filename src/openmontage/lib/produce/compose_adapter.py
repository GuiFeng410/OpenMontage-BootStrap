"""Remotion compose bundle + start/wait adapters."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import lib.board_production_run as production_run
from lib.board_stage_artifacts import StageArtifactValidationError, validate_stage_artifact
from lib.produce.job_store import (
    OUTPUT_REL,
    ProduceJobError,
    STATUS_PAUSED,
    STATUS_QUEUED,
    _fail_job,
    _has_final,
    _locked_artifact_revision,
    _profile,
    _project_dir,
    _read_json,
    _refresh_overlay,
    _tier,
    _write_json,
    write_job
)
COMPOSE_WAIT_ZH = (
    "素材已确认，本机正在按锁定轻度合成成片，大约 1–3 分钟。请留在本页。"
)

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
        overview = {}
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
    # Disk fallback: resume must not ignore already-generated segments when
    # review_overview was rewritten to only the sample-promoted first beat.
    candidate = _seg_rel(beat, artifact_revision)
    path = project / candidate
    if path.is_file() and path.stat().st_size > 0:
        return candidate
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

"""BoardState derivation — turn a project directory into renderable state.

Everything here is read-only and defensive: a malformed JSON file, a missing
artifact, or a half-written checkpoint must degrade the board, never crash it
(design principle: "never block, never break").
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from backlot.read_models.common import (
    COMMERCIAL_STAGE_LABELS_ZH,
    MEDIA_AUDIO_EXT,
    MEDIA_IMAGE_EXT,
    MEDIA_VIDEO_EXT,
    canonical_video_candidate as _canonical_video_candidate,
    canonical_video_path as _canonical_video_path,
    rel as _rel,
    resolve_asset_path as _resolve_asset_path,
)
from backlot.read_models.commercial import build_commercial_board as _build_commercial_board
from lib.checkpoint import _merge_project_decision_logs
from lib.events import read_events
from lib.interaction_intents import list_safe_interaction_intents
from lib.board_advance import strip_recommend
from lib.project_export import is_completed, read_runner_status
from lib.paths import PROJECTS_DIR, REPO_ROOT  # re-exported for server compatibility

# Directories inside a project we never scan for media (build noise).
SCAN_EXCLUDE = {"node_modules", ".git", "__pycache__", "history", ".cache"}



# Stages every pipeline shares (fallback rail when the manifest is unknown).
FALLBACK_STAGES = [
    "research", "proposal", "idea", "script", "scene_plan",
    "assets", "edit", "compose", "publish",
]

# How long (seconds) without filesystem activity before a board reads "idle".
LIVE_WINDOW_SECONDS = 5 * 60

# An in_progress stage with no filesystem activity for this long is flagged
# as possibly stalled (F-05: a wedged agent must be visible, not silent —
# heartbeat checkpoints and tool events both reset the clock).
STALL_WINDOW_SECONDS = 10 * 60


def _read_json(path: Path) -> Optional[dict]:
    """Read a JSON file, returning None on any failure."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None


# ---------------------------------------------------------------------------
# Pipeline / stages
# ---------------------------------------------------------------------------

def _load_pipeline_meta(pipeline_type: Optional[str]) -> dict[str, Any]:
    """Stage order + gate flags from the manifest; graceful fallback."""
    if pipeline_type and pipeline_type != "unknown":
        try:
            from lib.pipeline_loader import load_pipeline_readonly
            manifest = load_pipeline_readonly(pipeline_type)
            stages = [
                {
                    "name": s["name"],
                    "gated": bool(s.get("human_approval_default", False)),
                    "label_zh": s.get("label_zh") or COMMERCIAL_STAGE_LABELS_ZH.get(s["name"]),
                }
                for s in manifest.get("stages", [])
                if isinstance(s, dict) and s.get("name")
            ]
            if stages:
                locale = "zh-CN" if pipeline_type == "bootstrap-commercial" else "en"
                meta = manifest.get("metadata") or {}
                if isinstance(meta, dict) and meta.get("locale"):
                    locale = meta["locale"]
                return {
                    "pipeline_type": pipeline_type,
                    "stages": stages,
                    "known": True,
                    "locale": locale,
                }
        except Exception:
            pass
    return {
        "pipeline_type": pipeline_type or "unknown",
        "stages": [{"name": s, "gated": False, "label_zh": None} for s in FALLBACK_STAGES],
        "known": False,
        "locale": "en",
    }


def _resolve_artifact(project_dir: Path, value: Any) -> Optional[dict]:
    """Checkpoint artifacts may be inline dicts or path strings — resolve both.

    Path references are only followed INSIDE the project directory: a
    checkpoint must not be able to pull arbitrary JSON from elsewhere on
    disk onto the board (F-04).
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        p = Path(value)
        if not p.is_absolute():
            p = project_dir / value
        try:
            p.resolve().relative_to(Path(project_dir).resolve())
        except (ValueError, OSError):
            return None
        return _read_json(p)
    return None


def _collect_checkpoints(project_dir: Path) -> dict[str, dict]:
    """Current checkpoint per stage (raw dicts, unvalidated by design)."""
    out: dict[str, dict] = {}
    for path in sorted(project_dir.glob("checkpoint_*.json")):
        stage = path.stem[len("checkpoint_"):]
        data = _read_json(path)
        if data is not None:
            data["_mtime"] = path.stat().st_mtime
            out[stage] = data
    return out


def _collect_history(project_dir: Path) -> dict[str, list[dict]]:
    """Archived checkpoint versions per stage (oldest first)."""
    history_dir = project_dir / "history"
    out: dict[str, list[dict]] = {}
    if not history_dir.is_dir():
        return out
    for path in sorted(history_dir.glob("checkpoint_*.json")):
        m = re.match(r"checkpoint_(.+?)_\d", path.stem)
        stage = m.group(1) if m else path.stem[len("checkpoint_"):]
        data = _read_json(path)
        if data is not None:
            out.setdefault(stage, []).append(data)
    return out


def _build_stage_rail(
    pipeline_meta: dict,
    checkpoints: dict[str, dict],
    history: dict[str, list[dict]],
) -> list[dict]:
    """One entry per manifest stage with derived status + gate audit."""
    rail = []
    manifest_stage_names = {s["name"] for s in pipeline_meta["stages"]}
    for stage_def in pipeline_meta["stages"]:
        name = stage_def["name"]
        cp = checkpoints.get(name)
        versions = history.get(name, [])
        status = cp.get("status") if cp else "pending"
        entry: dict[str, Any] = {
            "name": name,
            "label_zh": stage_def.get("label_zh"),
            "gated": stage_def["gated"],
            "status": status or "pending",
            "timestamp": cp.get("timestamp") if cp else None,
            "review": cp.get("review") if cp else None,
            "cost_snapshot": cp.get("cost_snapshot") if cp else None,
            "error": cp.get("error") if cp else None,
            "human_approved": cp.get("human_approved") if cp else None,
            "partial_progress": (cp.get("metadata") or {}).get("partial_progress") if cp else None,
            "metadata": cp.get("metadata") if cp else None,
            "versions": len(versions) + (1 if cp else 0),
            # Chronological status trail (history + current) — powers replay.
            "history_entries": (
                [{"status": v.get("status"), "timestamp": v.get("timestamp")} for v in versions]
                + ([{"status": cp.get("status"), "timestamp": cp.get("timestamp")}] if cp else [])
            ),
        }
        # Gate audit: a gated stage that completed without ever passing
        # through awaiting_human (current or archived) was gate-skipped.
        if (
            stage_def["gated"]
            and cp is not None
            and cp.get("status") == "completed"
        ):
            saw_wait = any(v.get("status") == "awaiting_human" for v in versions)
            approved = bool(cp.get("human_approved"))
            entry["gate_skipped"] = not (saw_wait or approved)
        rail.append(entry)

    # Checkpoints for stages the manifest doesn't declare (legacy runs,
    # pipeline mismatch) still deserve a slot — at their canonical position
    # in the pipeline, not dangling after publish ("idea" belongs up front).
    canon = {name: i for i, name in enumerate(FALLBACK_STAGES)}
    for name, cp in checkpoints.items():
        if name in manifest_stage_names:
            continue
        entry = {
            "name": name,
            "gated": False,
            "status": cp.get("status") or "unknown",
            "timestamp": cp.get("timestamp"),
            "review": cp.get("review"),
            "cost_snapshot": cp.get("cost_snapshot"),
            "error": cp.get("error"),
            "human_approved": cp.get("human_approved"),
            "partial_progress": None,
            "versions": 1 + len(history.get(name, [])),
            "undeclared": True,
        }
        pos = canon.get(name)
        if pos is None:
            rail.append(entry)  # truly unknown name — end of rail
            continue
        insert_at = len(rail)
        for i, existing in enumerate(rail):
            existing_pos = canon.get(existing["name"])
            if existing_pos is not None and existing_pos > pos:
                insert_at = i
                break
        rail.insert(insert_at, entry)
    return rail


def _apply_board_stop_overlay(stages: list[dict], marker: dict[str, Any]) -> None:
    stop = marker.get("board_stop") if isinstance(marker, dict) else None
    if not isinstance(stop, dict):
        return
    stage_name = str(stop.get("stage") or "").strip()
    if not stage_name:
        return
    if stop.get("needs_user_decision") is not True and not stop.get("producing_wait"):
        return
    cleaned = strip_recommend(stop)
    for stage in stages:
        if stage.get("name") != stage_name:
            continue
        meta = dict(stage.get("metadata") or {})
        for key, value in cleaned.items():
            if key != "stage":
                meta[key] = value
        stage["metadata"] = meta
        return


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

ARTIFACT_FILES = {
    "research_brief": "research_brief.json",
    "brief": "brief.json",
    "video_plan": "video_plan.json",
    "proposal_packet": "proposal_packet.json",
    "script": "script.json",
    "scene_plan": "scene_plan.json",
    "asset_manifest": "asset_manifest.json",
    "edit_decisions": "edit_decisions.json",
    "render_report": "render_report.json",
    "final_review": "final_review.json",
    "publish_log": "publish_log.json",
    "decision_log": "decision_log.json",
    "review_overview": "review_overview.json",
    "batch01_review": "batch01_review.json",
    "batch02_review": "batch02_review.json",
    "sample_reel": "sample_reel.json",
    "full_draft_pro": "full_draft_pro.json",
    "cost_log": "cost_log.json",
    "segment_cards": "segment_cards.json",
    "asset_ledger": "asset_ledger.json",
    "asset_precheck": "asset_precheck.json",
    "asset_vision": "asset_vision.json",
}


def _collect_artifacts(project_dir: Path, checkpoints: dict[str, dict]) -> dict[str, dict]:
    """Artifacts from artifacts/*.json, backfilled from checkpoint payloads."""
    artifacts: dict[str, dict] = {}
    art_dir = project_dir / "artifacts"
    for name, filename in ARTIFACT_FILES.items():
        data = _read_json(art_dir / filename)
        if data is not None:
            artifacts[name] = data
    batch_reviews: dict[str, dict] = {}
    batch_review_sources: dict[str, str] = {}
    for path in sorted(art_dir.glob("batch*_review.json")):
        data = _read_json(path)
        if data is None:
            continue
        match = re.search(r"batch[_-]?(\d+)", path.stem, flags=re.IGNORECASE)
        fallback_id = f"batch_{int(match.group(1)):02d}" if match else path.stem
        batch_id = str(data.get("batch_id") or data.get("id") or fallback_id)
        batch_reviews[batch_id] = data
        batch_review_sources[batch_id] = path.relative_to(project_dir).as_posix()
    if batch_reviews:
        artifacts["batch_reviews"] = batch_reviews
        artifacts["_batch_review_sources"] = batch_review_sources
    # decision_log historically lives in both artifacts/ and the project root.
    # Merge prefix-compatible append-only copies so the board never renders a
    # stale approval after the root log records a later withdrawal.
    decision_logs = []
    for payload in (
        artifacts.get("decision_log"),
        _read_json(project_dir / "decision_log.json"),
    ):
        if not isinstance(payload, dict):
            continue
        normalized = deepcopy(payload)
        if not str(normalized.get("project_id") or "").strip():
            normalized["project_id"] = project_dir.name
        decision_logs.append(normalized)
    if decision_logs:
        try:
            artifacts["decision_log"] = _merge_project_decision_logs(
                decision_logs,
                project_dir.name,
            )
        except Exception:  # noqa: BLE001 - board state must degrade, never crash
            artifacts["decision_log"] = {
                "version": "1.0",
                "project_id": project_dir.name,
                "decisions": [],
            }
    # Backfill from checkpoint-embedded artifacts.
    for cp in checkpoints.values():
        for name, value in (cp.get("artifacts") or {}).items():
            if name not in artifacts:
                resolved = _resolve_artifact(project_dir, value)
                if resolved is not None:
                    artifacts[name] = resolved
    # A legacy checkpoint may be the only decision-log source. Re-run the same
    # project-bound merge after backfill so embedded cross-project approvals
    # cannot bypass the validation above.
    if isinstance(artifacts.get("decision_log"), dict):
        normalized = deepcopy(artifacts["decision_log"])
        if not str(normalized.get("project_id") or "").strip():
            normalized["project_id"] = project_dir.name
        try:
            artifacts["decision_log"] = _merge_project_decision_logs(
                [normalized],
                project_dir.name,
            )
        except Exception:  # noqa: BLE001 - board state must degrade, never crash
            artifacts["decision_log"] = {
                "version": "1.0",
                "project_id": project_dir.name,
                "decisions": [],
            }
    return artifacts


# ---------------------------------------------------------------------------
# Storyboard join
# ---------------------------------------------------------------------------

def _asset_entry(project_dir: Path, asset: dict) -> dict:
    """Normalize a manifest asset entry + resolve file existence.

    A file that resolves OUTSIDE the project directory is treated as
    not-servable (exists=False): /media only serves within the project, and
    a bare-filename fallback path would 404 or hit the wrong file.
    """
    raw_path = asset.get("path") or ""
    resolved = _resolve_asset_path(project_dir, raw_path)
    if resolved is not None:
        try:
            resolved.resolve().relative_to(Path(project_dir).resolve())
        except (ValueError, OSError):
            resolved = None
    file_path = resolved if resolved is not None else (project_dir / raw_path)
    exists = resolved is not None
    kind = asset.get("type") or ""
    if not kind and file_path.suffix:
        ext = file_path.suffix.lower()
        if ext in MEDIA_IMAGE_EXT:
            kind = "image"
        elif ext in MEDIA_VIDEO_EXT:
            kind = "video"
        elif ext in MEDIA_AUDIO_EXT:
            kind = "audio"
    # A visual is only *renderable* on the board if the file it points at is
    # actually a raster image or a video. Bespoke/atelier assets (type
    # "animation" pointing at a .tsx composition) exist on disk but can't be
    # thumbnailed — routing them to <img> yields a broken image. The board
    # falls back to a per-scene snapshot or the shot-spec placeholder instead.
    ext = file_path.suffix.lower()
    renderable = exists and ext in (MEDIA_IMAGE_EXT | MEDIA_VIDEO_EXT)
    return {
        "id": asset.get("id"),
        "type": kind,
        "scene_id": asset.get("scene_id"),
        "path": _rel(project_dir, file_path) if exists else raw_path,
        "exists": exists,
        "renderable": renderable,
        "prompt": asset.get("prompt"),
        "model": asset.get("model"),
        "source_tool": asset.get("source_tool"),
        "provider": asset.get("provider"),
        "cost_usd": asset.get("cost_usd"),
        "quality_score": asset.get("quality_score"),
        "duration_seconds": asset.get("duration_seconds"),
        "resolution": asset.get("resolution"),
    }


def _find_scene_snapshot(project_dir: Path, scene_id: str) -> Optional[dict]:
    """A per-scene review still, if the run wrote one.

    Atelier/animation scenes have no thumbnailable asset file, so the
    assets-stage snapshot (`snapshots/<scene_id>.png`) is what the filmstrip
    shows. Accept exact `<scene_id>.<ext>` and `<scene_id>_*.<ext>` forms.
    """
    snap_dir = project_dir / "snapshots"
    if not scene_id or not snap_dir.is_dir():
        return None
    try:
        for f in sorted(snap_dir.iterdir()):
            if not f.is_file() or f.suffix.lower() not in MEDIA_IMAGE_EXT:
                continue
            stem = f.stem
            if stem == scene_id or stem.startswith(f"{scene_id}_"):
                return {
                    "id": f"snap_{scene_id}",
                    "type": "image",
                    "scene_id": scene_id,
                    "path": _rel(project_dir, f),
                    "exists": True,
                    "renderable": True,
                    "snapshot": True,
                }
    except OSError:
        return None
    return None


def _find_script_section(scene: dict, sections: list[dict]) -> Optional[dict]:
    """Join scene → script section by id, falling back to timing overlap."""
    sid = scene.get("script_section_id")
    if sid:
        for s in sections:
            if s.get("id") == sid:
                return s
    start = scene.get("start_seconds")
    end = scene.get("end_seconds")
    if start is None or end is None:
        return None
    best, best_overlap = None, 0.0
    for s in sections:
        s0, s1 = s.get("start_seconds"), s.get("end_seconds")
        if s0 is None or s1 is None:
            continue
        overlap = min(end, s1) - max(start, s0)
        if overlap > best_overlap:
            best, best_overlap = s, overlap
    return best


def _build_storyboard(
    project_dir: Path,
    artifacts: dict[str, dict],
    events: list[dict],
) -> Optional[dict]:
    """Scene cards: scene_plan × script × asset_manifest (+ live events)."""
    scene_plan = artifacts.get("scene_plan")
    if not scene_plan or not isinstance(scene_plan.get("scenes"), list):
        return None
    sections = (artifacts.get("script") or {}).get("sections") or []
    manifest_assets = (artifacts.get("asset_manifest") or {}).get("assets") or []

    def scene_key(value: Any) -> str:
        # 0 is a legitimate scene id — only None/absent collapses to "".
        return str(value) if value is not None else ""

    assets_by_scene: dict[str, list[dict]] = {}
    for asset in manifest_assets:
        if not isinstance(asset, dict):
            continue
        entry = _asset_entry(project_dir, asset)
        assets_by_scene.setdefault(scene_key(entry.get("scene_id")), []).append(entry)

    # A scene is "generating" if its most recent top-level event is an
    # unfinished start. Nested (depth>0) provider events inside a selector
    # call are skipped — the outer call's finish is the real completion.
    generating: dict[str, dict] = {}
    for ev in events:
        sid = ev.get("scene_id")
        if sid is None or ev.get("depth"):
            continue
        sid = scene_key(sid)
        if ev.get("event") == "start":
            generating[sid] = ev
        elif ev.get("event") in ("finish", "error"):
            generating.pop(sid, None)

    cards = []
    for scene in scene_plan["scenes"]:
        if not isinstance(scene, dict):
            continue
        sid = scene_key(scene.get("id"))
        section = _find_script_section(scene, sections)
        scene_assets = assets_by_scene.get(sid, [])
        visuals = [a for a in scene_assets if a["type"] in ("image", "video", "diagram", "animation")]
        audio = [a for a in scene_assets if a["type"] in ("audio", "narration", "music", "sfx")]
        # Only files that can actually be shown (raster/video) are takes; a
        # bespoke composition asset (.tsx animation) is real but not showable.
        renderable = [a for a in visuals if a.get("renderable")]
        # A raster/video asset whose FILE is missing stays as a "file missing"
        # indicator. But an asset that EXISTS yet can't be shown (a .tsx atelier
        # composition) is dropped — it falls back to a per-scene snapshot.
        missing = [a for a in visuals if not a.get("exists") and a["type"] in ("image", "video", "diagram")]
        active_visual = (
            renderable[-1] if renderable
            else missing[-1] if missing
            else _find_scene_snapshot(project_dir, sid)
        )
        cards.append({
            "id": sid,
            "type": scene.get("type"),
            "description": scene.get("description"),
            "start_seconds": scene.get("start_seconds"),
            "end_seconds": scene.get("end_seconds"),
            "duration_seconds": (
                max(0, (scene.get("end_seconds") or 0) - (scene.get("start_seconds") or 0))
                if scene.get("end_seconds") is not None and scene.get("start_seconds") is not None
                else None
            ),
            "hero_moment": bool(scene.get("hero_moment")),
            "shot_language": scene.get("shot_language"),
            "shot_intent": scene.get("shot_intent"),
            "framing": scene.get("framing"),
            "movement": scene.get("movement"),
            "narration": (section or {}).get("text"),
            "section_label": (section or {}).get("label"),
            "required_assets": scene.get("required_assets") or [],
            "visual": active_visual,
            "takes": renderable,
            "audio": audio,
            "generating": generating.get(sid) is not None,
            "generating_tool": (generating.get(sid) or {}).get("tool"),
        })

    total = scene_plan.get("metadata", {}).get("total_duration_seconds")
    if total is None and cards:
        ends = [c["end_seconds"] for c in cards if c["end_seconds"] is not None]
        total = max(ends) if ends else None
    return {
        "scenes": cards,
        "total_duration_seconds": total,
        "style_playbook": scene_plan.get("style_playbook"),
    }


# ---------------------------------------------------------------------------
# Media discovery
# ---------------------------------------------------------------------------

def _scan_media(project_dir: Path) -> dict[str, list[dict]]:
    """Discovered media files (renders, loose assets, snapshots)."""
    renders: list[dict] = []
    snapshots: list[dict] = []
    music: list[dict] = []

    renders_dir = project_dir / "renders"
    if renders_dir.is_dir():
        for f in sorted(renders_dir.iterdir()):
            if f.suffix.lower() in MEDIA_VIDEO_EXT and f.is_file():
                renders.append({"path": _rel(project_dir, f), "size": f.stat().st_size,
                                "mtime": f.stat().st_mtime})
    # Atelier heuristic: deliverables at project root.
    for f in sorted(project_dir.glob("*.mp4")):
        renders.append({"path": _rel(project_dir, f), "size": f.stat().st_size,
                        "mtime": f.stat().st_mtime, "at_root": True})
    for f in sorted(project_dir.glob("*.mp3")):
        music.append({"path": _rel(project_dir, f), "at_root": True})
    music_dir = project_dir / "assets" / "music"
    if music_dir.is_dir():
        for f in sorted(music_dir.iterdir()):
            if f.suffix.lower() in MEDIA_AUDIO_EXT:
                music.append({"path": _rel(project_dir, f)})

    for dirname in ("snapshots", "verify"):
        d = project_dir / dirname
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in MEDIA_IMAGE_EXT and f.is_file():
                    snapshots.append({"path": _rel(project_dir, f)})

    renders.sort(key=lambda r: r.get("mtime", 0), reverse=True)
    return {"renders": renders, "snapshots": snapshots, "music": music}




def _read_fast_track_pause(project_dir: Path) -> Optional[dict[str, str]]:
    """Newest checkpoint metadata.fast_track_pause; display-only, never invented."""
    newest: Optional[dict[str, str]] = None
    newest_mtime = -1.0
    for path in project_dir.glob("checkpoint_*.json"):
        data = _read_json(path)
        if not isinstance(data, dict):
            continue
        metadata = data.get("metadata")
        pause = metadata.get("fast_track_pause") if isinstance(metadata, dict) else None
        if not isinstance(pause, dict):
            continue
        reason_code = pause.get("reason_code")
        friendly_zh = pause.get("friendly_zh")
        if not isinstance(reason_code, str) or not isinstance(friendly_zh, str):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < newest_mtime:
            continue
        newest_mtime = mtime
        question = pause.get("current_question")
        newest = {
            "reason_code": reason_code,
            "friendly_zh": friendly_zh,
            "current_question": question if isinstance(question, str) else "",
        }
    return newest


def _read_final_video(
    project_dir: Path,
    commercial: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Playable project-relative final video, never an absolute path."""
    if _canonical_video_path(project_dir, "renders/final.mp4"):
        return {"path": "renders/final.mp4", "exists": True}
    evidence = commercial.get("stage_evidence") or {}
    for key in ("delivery", "compose"):
        raw = (evidence.get(key) or {}).get("path")
        resolved = _canonical_video_path(project_dir, raw)
        if resolved:
            return {"path": resolved, "exists": True}
    return None


def _attach_commercial_board_echo(project_dir: Path, commercial: dict[str, Any]) -> None:
    """Attach read-only interaction / pause / final echo onto commercial."""
    commercial["interaction_intents"] = list_safe_interaction_intents(project_dir)
    commercial["fast_track_pause"] = _read_fast_track_pause(project_dir)
    commercial["final_video"] = _read_final_video(project_dir, commercial)
    marker = commercial.get("project") if isinstance(commercial.get("project"), dict) else {}
    if not marker:
        try:
            raw = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
            marker = raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            marker = {}
    commercial["lifecycle_status"] = marker.get("lifecycle_status")
    commercial["export_path"] = marker.get("export_path")
    commercial["exported_at"] = marker.get("exported_at")
    commercial["completed"] = is_completed(marker)
    commercial["runner_status"] = read_runner_status(project_dir)
    try:
        from backlot.runner import active_project_id, runner_alive

        alive = bool(runner_alive())
        active = str(active_project_id() or "")
        commercial["runner_bind"] = {
            "alive": alive,
            "active_project_id": active,
            "bound": alive and active == project_dir.name,
        }
    except Exception:
        commercial["runner_bind"] = {
            "alive": False,
            "active_project_id": "",
            "bound": False,
        }
    run_error = None
    try:
        from lib.board_production_run import (
            ProductionRunError,
            read_produce_job,
            read_production_run,
        )

        commercial["production_run"] = read_production_run(project_dir)
        commercial["produce_job"] = read_produce_job(project_dir)
    except ProductionRunError:
        run_error = {
            "code": "run_state_invalid",
            "friendly_zh": "生产状态文件无效，已暂停且不会自动重试。",
        }
        commercial["production_run"] = None
        commercial["produce_job"] = None
    commercial["production_run_error"] = run_error
    stop = marker.get("board_stop") if isinstance(marker.get("board_stop"), dict) else None
    commercial["board_stop"] = stop
    runner = commercial.get("runner_status") if isinstance(commercial.get("runner_status"), dict) else {}
    paused = bool(stop and stop.get("paused")) or str(runner.get("phase") or "") == "paused"
    job = commercial.get("produce_job") if isinstance(commercial.get("produce_job"), dict) else {}
    job_busy = str(job.get("status") or "") in {"queued", "running"}
    has_final = bool(commercial.get("final_video"))
    from lib.review_interrupt import honest_user_stage_zh

    commercial["user_stage_zh"] = honest_user_stage_zh(
        {"label_zh": commercial.get("user_stage_zh")},
        has_final=has_final,
        producing=job_busy or str(runner.get("phase") or "") in {"producing", "queued"},
        paused=paused,
    )
    if stop and paused:
        commercial["decision"] = {
            "stage": stop.get("stage") or "delivery_signoff",
            "title_zh": stop.get("decision_title_zh") or "已暂停",
            "prompt_zh": stop.get("decision_prompt_zh") or runner.get("friendly_zh") or "",
            "options": [],
            "producing_wait": False,
            "paused": True,
        }
    elif run_error and not commercial.get("final_video"):
        commercial["decision"] = {
            "stage": (stop or {}).get("stage") or "delivery_signoff",
            "title_zh": "已暂停",
            "prompt_zh": run_error["friendly_zh"],
            "options": [],
            "producing_wait": False,
            "paused": True,
        }
    elif stop and stop.get("producing_wait") and not commercial.get("decision"):
        if not has_final and not job_busy:
            commercial["decision"] = {
                "stage": stop.get("stage") or "delivery_signoff",
                "title_zh": "已中断",
                "prompt_zh": stop.get("decision_prompt_zh")
                or runner.get("friendly_zh")
                or "还没有成片，已中断。可在库页继续，或回本页处理。",
                "options": [],
                "producing_wait": False,
                "paused": True,
            }
        else:
            commercial["decision"] = {
                "stage": stop.get("stage") or "delivery_signoff",
                "title_zh": stop.get("decision_title_zh") or "制作中",
                "prompt_zh": stop.get("decision_prompt_zh") or "",
                "options": [],
                "producing_wait": True,
            }


def _find_poster(project_dir: Path, state: dict) -> Optional[str]:
    """Best poster for the library card (image path, or a video path —
    the /thumb endpoint extracts a frame from videos)."""
    board = state.get("storyboard") or {}
    for card in board.get("scenes", []):
        visual = card.get("visual")
        if visual and visual.get("exists") and visual.get("type") == "image":
            return visual["path"]
    for snap in (state.get("media") or {}).get("snapshots", []):
        return snap["path"]
    # Common image homes, in order of how representative they usually are.
    for rel_dir in ("assets/images", "assets/frames", "exports", "assets", "."):
        d = (project_dir / rel_dir) if rel_dir != "." else project_dir
        if not d.is_dir():
            continue
        try:
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix.lower() in MEDIA_IMAGE_EXT:
                    return _rel(project_dir, f)
        except OSError:
            continue
    # Last resort: the newest render — /thumb extracts a poster frame.
    renders = (state.get("media") or {}).get("renders", [])
    if renders:
        return renders[0]["path"]
    return None


_EDIT_GATE_MESSAGES_ZH = {
    "wrong_stage": "初稿审查阶段起才可提交；交付确认阶段仅修订环可继续。",
    "full_draft_missing": "缺少 full_draft_pro，尚不能进入剪辑修订。",
    "full_draft_invalid": "full_draft_pro 格式无效，无法确认初稿证据。",
    "latest_render_missing": "缺少最新成片，或 canonical 成片路径无效。",
    "cuts_empty": "没有可编辑片段。",
    "cut_source_outside_assets_video": "片段源文件必须位于当前项目 assets/video 内。",
    "cut_source_not_video": "片段源文件不是合法视频格式。",
    "cut_source_missing": "片段源文件不存在。",
    "cut_source_empty": "片段源文件为空。",
    "compose_required": "cuts 已应用，需要重合成并更新 canonical 成片版本。",
}


def _cut_source_failure(project_dir: Path, raw: Any) -> Optional[str]:
    """Return a concrete edit-gate failure code for one cuts.source."""
    if not isinstance(raw, str) or not raw.strip():
        return "cut_source_outside_assets_video"
    normalized = raw.strip().replace("\\", "/")
    candidate = Path(normalized)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
        or len(candidate.parts) < 3
        or candidate.parts[:2] != ("assets", "video")
    ):
        return "cut_source_outside_assets_video"
    if candidate.suffix.lower() not in MEDIA_VIDEO_EXT:
        return "cut_source_not_video"
    try:
        resolved = (project_dir / candidate).resolve()
        resolved.relative_to((project_dir / "assets" / "video").resolve())
        if not resolved.is_file():
            return "cut_source_missing"
        if resolved.stat().st_size <= 0:
            return "cut_source_empty"
    except (OSError, ValueError):
        return "cut_source_outside_assets_video"
    return None


def _build_editing_gate(
    project_dir: Path,
    artifacts: dict[str, dict],
    stages: list[dict],
) -> dict[str, Any]:
    """Derive the single state gate consumed by both UI and POST /intents."""
    active = next(
        (
            stage for stage in stages
            if stage.get("status") in ("in_progress", "awaiting_human")
        ),
        None,
    )
    stage_name = active.get("name") if active else None
    reasons: list[dict[str, str]] = []

    def reject(code: str) -> None:
        if any(reason["code"] == code for reason in reasons):
            return
        reasons.append({"code": code, "friendly_zh": _EDIT_GATE_MESSAGES_ZH[code]})

    if stage_name not in {"draft_review", "delivery_signoff"}:
        reject("wrong_stage")

    full_draft = artifacts.get("full_draft_pro")
    if not isinstance(full_draft, dict) or not full_draft:
        reject("full_draft_missing")
        full_draft = {}
    elif (
        not isinstance(full_draft.get("path"), str)
        or not full_draft["path"].strip()
        or not isinstance(full_draft.get("issue_segments"), list)
        or not isinstance(full_draft.get("modification_list"), list)
    ):
        reject("full_draft_invalid")
    elif _canonical_video_path(project_dir, full_draft.get("path")) is None:
        reject("full_draft_invalid")

    canonical_raw = full_draft.get("path")
    if stage_name == "delivery_signoff":
        final_review = artifacts.get("final_review")
        canonical_raw = (
            final_review.get("output_path")
            if isinstance(final_review, dict)
            else None
        )
    latest_render = _canonical_video_path(project_dir, canonical_raw)
    if latest_render is None:
        reject("latest_render_missing")

    edit_decisions = artifacts.get("edit_decisions")
    cuts = (
        edit_decisions.get("cuts")
        if isinstance(edit_decisions, dict)
        and isinstance(edit_decisions.get("cuts"), list)
        else []
    )
    if not cuts:
        reject("cuts_empty")
    else:
        for cut in cuts:
            code = _cut_source_failure(
                project_dir,
                cut.get("source") if isinstance(cut, dict) else None,
            )
            if code:
                reject(code)

    if (
        isinstance(edit_decisions, dict)
        and edit_decisions.get("requires_compose") is True
        and cuts
    ):
        from lib.edit_apply import cuts_digest

        current_revision = cuts_digest(cuts)
        decisions_revision = edit_decisions.get("cuts_revision")
        render_artifact = (
            artifacts.get("final_review")
            if stage_name == "delivery_signoff"
            else full_draft
        )
        render_revision = (
            render_artifact.get("cuts_revision")
            if isinstance(render_artifact, dict)
            else None
        )
        if (
            decisions_revision != current_revision
            or render_revision != current_revision
        ):
            reject("compose_required")

    reason_codes = [reason["code"] for reason in reasons]
    enabled = not reasons
    return {
        "enabled": enabled,
        "stage": stage_name,
        "reason_codes": reason_codes,
        "reasons": reasons,
        "friendly_zh": (
            "剪辑输入已就绪，可提交轻量剪辑要求。"
            if enabled
            else "当前不可提交剪辑要求：" + "；".join(
                reason["friendly_zh"] for reason in reasons
            )
        ),
        "latest_render": {
            "path": latest_render,
            "exists": latest_render is not None,
            "artifact": (
                "final_review"
                if stage_name == "delivery_signoff"
                else "full_draft_pro"
            ),
        },
        "cut_count": len(cuts),
    }


def _last_activity(project_dir: Path) -> float:
    """Most recent mtime among state-bearing files (bounded scan)."""
    latest = 0.0
    try:
        candidates = list(project_dir.glob("checkpoint_*.json"))
        candidates.append(project_dir / "project.json")
        candidates.append(project_dir / "events.jsonl")
        art = project_dir / "artifacts"
        if art.is_dir():
            candidates.extend(art.glob("*.json"))
        for p in candidates:
            try:
                latest = max(latest, p.stat().st_mtime)
            except OSError:
                continue
    except OSError:
        pass
    return latest


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_board_state(project_dir: Path) -> dict[str, Any]:
    """Full BoardState for one project. Never raises."""
    project_dir = Path(project_dir)
    project_id = project_dir.name

    marker = _read_json(project_dir / "project.json") or {}
    meta_json = _read_json(project_dir / "meta.json") or {}

    checkpoints = _collect_checkpoints(project_dir)
    history = _collect_history(project_dir)

    pipeline_type = marker.get("pipeline_type")
    if not pipeline_type:
        for cp in checkpoints.values():
            pt = cp.get("pipeline_type")
            if pt and pt != "unknown":
                pipeline_type = pt
                break
    pipeline_meta = _load_pipeline_meta(pipeline_type)

    artifacts = _collect_artifacts(project_dir, checkpoints)
    events = read_events(project_dir, limit=250)
    storyboard = _build_storyboard(project_dir, artifacts, events)
    media = _scan_media(project_dir)

    stages = _build_stage_rail(pipeline_meta, checkpoints, history)
    _apply_board_stop_overlay(stages, marker)
    legacy_checkpoints: list[dict] = []
    if pipeline_type == "bootstrap-commercial":
        legacy_checkpoints = [
            {
                "stage": stage["name"],
                "status": stage.get("status"),
                "timestamp": stage.get("timestamp"),
            }
            for stage in stages
            if stage.get("undeclared")
        ]
        stages = [stage for stage in stages if not stage.get("undeclared")]

    # Cost: latest checkpoint snapshot wins; fall back to manifest total.
    cost = None
    for cp in sorted(checkpoints.values(), key=lambda c: c.get("_mtime", 0), reverse=True):
        if cp.get("cost_snapshot"):
            cost = cp["cost_snapshot"]
            break
    if cost is None:
        total = (artifacts.get("asset_manifest") or {}).get("total_cost_usd")
        if total is not None:
            cost = {"total_spent_usd": total}

    import time
    last_activity = _last_activity(project_dir)
    now = time.time()
    live = bool(last_activity and (now - last_activity) < LIVE_WINDOW_SECONDS)
    if pipeline_type == "bootstrap-commercial":
        try:
            from backlot.runner import active_project_id, runner_alive

            live = bool(runner_alive()) and str(active_project_id() or "") == project_id
        except Exception:
            live = False

    # Stall detection: an in_progress stage that stopped writing anything.
    for stage_entry in stages:
        if (
            stage_entry["status"] == "in_progress"
            and last_activity
            and (now - last_activity) > STALL_WINDOW_SECONDS
        ):
            stage_entry["stalled"] = True
            stage_entry["stalled_minutes"] = int((now - last_activity) / 60)

    state: dict[str, Any] = {
        "project_id": project_id,
        "title": marker.get("title") or meta_json.get("name") or project_id.replace("-", " ").title(),
        "pipeline": pipeline_meta,
        "locale": pipeline_meta.get("locale") or (
            "zh-CN" if pipeline_type == "bootstrap-commercial" else "en"
        ),
        "style_playbook": marker.get("style_playbook"),
        "created_at": marker.get("created_at"),
        "has_marker": bool(marker),
        "has_pipeline_state": bool(checkpoints),
        "stages": stages,
        "artifacts": artifacts,
        "storyboard": storyboard,
        "media": media,
        "events": events,
        "cost": cost,
        "last_activity": last_activity,
        "live": live,
        "production_profile": marker.get("production_profile"),
    }
    if pipeline_type == "bootstrap-commercial":
        state["commercial"] = _build_commercial_board(
            project_dir, marker, artifacts, stages, media, cost, legacy_checkpoints,
        )
        _attach_commercial_board_echo(project_dir, state["commercial"])
        state["editing_gate"] = _build_editing_gate(project_dir, artifacts, stages)
        state["commercial"]["editing_gate"] = state["editing_gate"]
    artifacts.pop("_batch_review_sources", None)
    state["poster"] = _find_poster(project_dir, state)
    return state


def summarize_project(project_dir: Path) -> dict[str, Any]:
    """Cheap library-card summary (no full artifact parse of big files)."""
    state = load_board_state(project_dir)
    active = next((s for s in state["stages"] if s["status"] in ("in_progress", "awaiting_human")), None)
    done = [s for s in state["stages"] if s["status"] == "completed"]
    commercial = state.get("commercial") or {}
    confirm_ids = commercial.get("confirm_stop_ids") or []
    allowed = set(confirm_ids)
    visible_stages = [
        s for s in state["stages"]
        if not s.get("undeclared") and (not allowed or s["name"] in allowed)
    ]
    brief = commercial.get("brief_summary") or {}
    lifecycle = str(commercial.get("lifecycle_status") or "")
    return {
        "project_id": state["project_id"],
        "title": state["title"],
        "pipeline_type": state["pipeline"]["pipeline_type"],
        "has_pipeline_state": state["has_pipeline_state"],
        "poster": state["poster"],
        "live": state["live"],
        "last_activity": state["last_activity"],
        "active_stage": active["name"] if active else None,
        "awaiting_human": bool(active and active["status"] == "awaiting_human"),
        "stage_states": [
            {"name": s["name"], "status": s["status"]}
            for s in visible_stages
        ],
        "completed_count": len(done),
        "render_count": len(state["media"]["renders"]),
        "scene_count": len((state["storyboard"] or {}).get("scenes", [])),
        "review_mode_preset": commercial.get("review_mode_preset"),
        "review_mode_zh": brief.get("review_mode_zh"),
        "user_stage_zh": commercial.get("user_stage_zh"),
        "production_tier_zh": brief.get("production_tier"),
        "imported_asset_count": brief.get("imported_asset_count"),
        "lifecycle_status": lifecycle,
        "completed": bool(commercial.get("completed")),
        "export_path": str(commercial.get("export_path") or ""),
    }


def list_projects(projects_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    """Library view: every project directory, live-first then recency."""
    root = Path(projects_dir) if projects_dir else PROJECTS_DIR
    if not root.is_dir():
        return []
    summaries = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        try:
            summaries.append(summarize_project(entry))
        except Exception:
            summaries.append({
                "project_id": entry.name,
                "title": entry.name.replace("-", " ").title(),
                "pipeline_type": "unknown",
                "has_pipeline_state": False,
                "poster": None,
                "live": False,
                "last_activity": 0,
                "active_stage": None,
                "awaiting_human": False,
                "stage_states": [],
                "completed_count": 0,
                "render_count": 0,
                "scene_count": 0,
                "error": "unreadable",
            })
    summaries.sort(key=lambda s: (not s["live"], -(s["last_activity"] or 0)))
    return summaries

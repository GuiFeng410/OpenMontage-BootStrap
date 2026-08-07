"""BoardState derivation — turn a project directory into renderable state.

Everything here is read-only and defensive: a malformed JSON file, a missing
artifact, or a half-written checkpoint must degrade the board, never crash it
(design principle: "never block, never break").
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from lib.events import read_events
from lib.paths import PROJECTS_DIR, REPO_ROOT  # single source of truth (env-overridable)

MEDIA_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
MEDIA_VIDEO_EXT = {".mp4", ".webm", ".mov"}
MEDIA_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg"}

# Directories inside a project we never scan for media (build noise).
SCAN_EXCLUDE = {"node_modules", ".git", "__pycache__", "history", ".cache"}

# Chinese labels for bootstrap-commercial stages (fallback if manifest omits label_zh).
COMMERCIAL_STAGE_LABELS_ZH = {
    "brief_locked": "方案确认",
    "assets_gate": "素材检查",
    "sample_review": "试片确认",
    "segment_build": "分段制作",
    "draft_review": "初稿审查",
    "final_compose": "合成终稿",
    "delivery_signoff": "交付确认",
}

ROLE_LABELS_ZH = {
    "product_identity_anchor": "身份基准",
    "product_angle": "角度图",
    "product_hero": "主图（仅运镜）",
    "product_detail": "细节图",
    "on_body": "佩戴图",
    "hand": "手持图",
}

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


def _rel(project_dir: Path, path: Path) -> str:
    """Project-relative POSIX path for media URLs."""
    try:
        return path.resolve().relative_to(Path(project_dir).resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


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
    for path in sorted(art_dir.glob("batch*_review.json")):
        data = _read_json(path)
        if data is None:
            continue
        match = re.search(r"batch[_-]?(\d+)", path.stem, flags=re.IGNORECASE)
        fallback_id = f"batch_{int(match.group(1)):02d}" if match else path.stem
        batch_id = str(data.get("batch_id") or data.get("id") or fallback_id)
        batch_reviews[batch_id] = data
    if batch_reviews:
        artifacts["batch_reviews"] = batch_reviews
    # decision_log historically also lives at project root
    if "decision_log" not in artifacts:
        data = _read_json(project_dir / "decision_log.json")
        if data is not None:
            artifacts["decision_log"] = data
    # Backfill from checkpoint-embedded artifacts.
    for cp in checkpoints.values():
        for name, value in (cp.get("artifacts") or {}).items():
            if name not in artifacts:
                resolved = _resolve_artifact(project_dir, value)
                if resolved is not None:
                    artifacts[name] = resolved
    return artifacts


# ---------------------------------------------------------------------------
# Storyboard join
# ---------------------------------------------------------------------------

def _resolve_asset_path(project_dir: Path, raw_path: str) -> Optional[Path]:
    """Manifest paths appear in several real-world flavors — try them all.

    Observed on disk: project-relative ("assets/images/x.png"),
    repo-relative ("projects/<id>/assets/images/x.png"), and absolute.
    """
    if not raw_path:
        return None
    p = Path(raw_path)
    candidates = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(project_dir / raw_path)
        candidates.append(REPO_ROOT / raw_path)
        # repo-relative with the project prefix repeated
        parts = p.parts
        if len(parts) > 2 and parts[0] == "projects":
            candidates.append(project_dir.parent / Path(*parts[1:]))
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


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


def _resolve_commercial_asset(project_dir: Path, raw: str) -> Optional[str]:
    """Resolve a beat asset filename to a project-relative media path."""
    if not raw:
        return None
    if "/" in raw or "\\" in raw:
        candidates = [project_dir / raw]
    else:
        candidates = [
            project_dir / "assets" / "video" / raw,
            project_dir / "assets" / "video" / "stills" / raw,
            project_dir / raw,
        ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return _rel(project_dir, candidate)
        except OSError:
            continue
    return raw


def _parse_time_span(raw: str) -> tuple[Optional[float], Optional[float]]:
    """Parse '00:00-00:04' or '0-4' into start/end seconds."""
    if not raw or not isinstance(raw, str):
        return None, None
    parts = raw.replace("–", "-").split("-")
    if len(parts) != 2:
        return None, None

    def to_sec(token: str) -> Optional[float]:
        token = token.strip()
        if not token:
            return None
        if ":" in token:
            bits = token.split(":")
            try:
                if len(bits) == 2:
                    return int(bits[0]) * 60 + float(bits[1])
                if len(bits) == 3:
                    return int(bits[0]) * 3600 + int(bits[1]) * 60 + float(bits[2])
            except ValueError:
                return None
        try:
            return float(token)
        except ValueError:
            return None

    return to_sec(parts[0]), to_sec(parts[1])


def _commercial_card_mode(stages: list[dict]) -> str:
    """plan | assets | produce — drives segment card field set."""
    by_name = {s.get("name"): s for s in stages}
    awaiting = next((s for s in stages if s.get("status") == "awaiting_human"), None)
    if awaiting is None:
        awaiting = next(
            (
                s for s in stages
                if s.get("status") == "in_progress"
                and (s.get("metadata") or {}).get("needs_user_decision") is True
            ),
            None,
        )
    if awaiting:
        name = awaiting.get("name")
        if name == "brief_locked":
            return "plan"
        if name == "assets_gate":
            return "assets"
        return "produce"
    order = [
        "brief_locked", "assets_gate", "sample_review", "segment_build",
        "draft_review", "final_compose", "delivery_signoff",
    ]
    # Farthest incomplete stage; if all done → produce (show results).
    for name in order:
        st = by_name.get(name) or {}
        status = st.get("status") or "pending"
        if status in ("pending", "in_progress", "failed"):
            if name == "brief_locked":
                return "plan"
            if name == "assets_gate":
                return "assets"
            return "produce"
    return "produce"


def _build_commercial_board(
    project_dir: Path,
    marker: dict[str, Any],
    artifacts: dict[str, dict],
    stages: list[dict],
    media: dict[str, list],
    cost: Optional[dict],
) -> dict[str, Any]:
    """Chinese evidence panel for bootstrap-commercial (P1 + P1.1)."""
    profile = marker.get("production_profile") or {}
    brief = artifacts.get("brief") or {}
    budget = brief.get("budget") or {}
    overview_doc = artifacts.get("review_overview") or {}
    segment_doc = artifacts.get("segment_cards") or {}
    ledger_doc = artifacts.get("asset_ledger") or {}
    precheck_doc = artifacts.get("asset_precheck") or {}
    review_mode = profile.get("review_mode") or overview_doc.get("review_mode") or "normal"
    usd_cny = float(profile.get("usd_cny_rate") or budget.get("usd_cny_rate") or 7.2)
    card_mode = _commercial_card_mode(stages)
    show_preview = card_mode == "produce"
    show_players = show_preview

    images: list[dict[str, Any]] = []
    for filename, meta in (brief.get("images") or {}).items():
        if not isinstance(meta, dict):
            continue
        role = meta.get("role") or ""
        rel = meta.get("path") or f"assets/images/{filename}"
        resolved = _resolve_asset_path(project_dir, rel)
        images.append({
            "file": filename,
            "role": role,
            "role_zh": ROLE_LABELS_ZH.get(role, role or "素材"),
            "path": _rel(project_dir, resolved) if resolved else rel,
            "exists": resolved is not None,
            "hero_only_motion": role == "product_hero",
        })

    seg_by_beat = {
        row.get("beat"): row
        for row in (segment_doc.get("segments") or [])
        if isinstance(row, dict) and row.get("beat")
    }
    ledger_by_beat: dict[str, list[dict]] = {}
    for entry in ledger_doc.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        beat_id = entry.get("beat") or ""
        path = entry.get("path") or ""
        resolved = _resolve_asset_path(project_dir, path) if path else None
        item = {
            "label": entry.get("label"),
            "label_zh": entry.get("label_zh") or entry.get("label") or "",
            "kind": entry.get("kind"),
            "file": entry.get("file"),
            "path": _rel(project_dir, resolved) if resolved else path,
            "exists": resolved is not None if path else False,
            "selected": bool(entry.get("selected")),
            "note_zh": entry.get("note_zh") or "",
        }
        ledger_by_beat.setdefault(beat_id, []).append(item)

    beats: list[dict[str, Any]] = []
    overview_rows = overview_doc.get("overview") or []
    if not overview_rows and seg_by_beat:
        overview_rows = [
            {"beat": b, "time": seg_by_beat[b].get("time"), "status": seg_by_beat[b].get("status")}
            for b in seg_by_beat
        ]
    for row in overview_rows:
        if not isinstance(row, dict):
            continue
        beat_id = row.get("beat") or ""
        plan = seg_by_beat.get(beat_id) or {}
        asset = row.get("asset") or ""
        asset_alt = row.get("asset_alt") or ""
        t0 = plan.get("t_start")
        t1 = plan.get("t_end")
        if t0 is None or t1 is None:
            t0, t1 = _parse_time_span(row.get("time") or plan.get("time") or "")
        beats.append({
            "beat": beat_id,
            "time": row.get("time") or plan.get("time"),
            "t_start": t0,
            "t_end": t1,
            "method": row.get("method"),
            "angle_use": row.get("angle_use"),
            "status": row.get("status") or plan.get("status"),
            "ref": row.get("ref"),
            "asset_path": _resolve_commercial_asset(project_dir, asset) if asset else None,
            "asset_alt_path": _resolve_commercial_asset(project_dir, asset_alt) if asset_alt else None,
            "asset_plan_zh": plan.get("asset_plan_zh"),
            "copy_plan_zh": plan.get("copy_plan_zh"),
            "shot_plan_zh": plan.get("shot_plan_zh"),
            "need_count": plan.get("need_count"),
            "have_count": plan.get("have_count"),
            "gap_status": plan.get("gap_status"),
            "need_detail_zh": plan.get("need_detail_zh"),
            "ledger": ledger_by_beat.get(beat_id) or [],
        })

    duration = (
        segment_doc.get("duration_seconds")
        or profile.get("duration_seconds")
        or brief.get("duration_seconds")
        or 0
    )
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = 0.0
    if not duration and beats:
        ends = [b["t_end"] for b in beats if b.get("t_end") is not None]
        duration = max(ends) if ends else 0.0

    beat_marks: list[dict[str, Any]] = []
    batch_seconds: set[float] = set()
    if review_mode == "pro":
        for batch in overview_doc.get("batches") or []:
            if not isinstance(batch, dict):
                continue
            _a, b_end = _parse_time_span(batch.get("span") or "")
            if b_end is None or not duration:
                continue
            if 0 < b_end < duration:
                batch_seconds.add(float(b_end))

    for b in beats:
        if b.get("t_end") is not None and duration and b["t_end"] < duration:
            sec = float(b["t_end"])
            # Skip beat tick when a batch boundary already sits on this second.
            if sec in batch_seconds:
                continue
            beat_marks.append({
                "seconds": sec,
                "kind": "beat",
                "label": f"{sec:g}s",
                "beat": b.get("beat"),
            })

    batch_marks: list[dict[str, Any]] = []
    if review_mode == "pro":
        for batch in overview_doc.get("batches") or []:
            if not isinstance(batch, dict):
                continue
            _a, b_end = _parse_time_span(batch.get("span") or "")
            if b_end is None or not duration:
                continue
            if 0 < b_end < duration:
                batch_marks.append({
                    "seconds": float(b_end),
                    "kind": "batch",
                    "label": f"{float(b_end):g}s",
                    "batch_id": batch.get("id"),
                })

    awaiting = next((s for s in stages if s.get("status") == "awaiting_human"), None)
    if awaiting is None:
        awaiting = next(
            (
                s for s in stages
                if s.get("status") == "in_progress"
                and (s.get("metadata") or {}).get("needs_user_decision") is True
            ),
            None,
        )
    decision = None
    if awaiting:
        meta = awaiting.get("metadata") or {}
        name = awaiting.get("name") or ""
        decision = {
            "stage": name,
            "stage_label_zh": awaiting.get("label_zh") or COMMERCIAL_STAGE_LABELS_ZH.get(name, name),
            "title_zh": meta.get("decision_title_zh"),
            "prompt_zh": meta.get("decision_prompt_zh"),
            "context_zh": meta.get("decision_context_zh"),
            "recommendation_zh": meta.get("recommendation_zh"),
            "options": meta.get("decision_options") if isinstance(meta.get("decision_options"), list) else [],
            "approval_note": meta.get("approval_note"),
            "examples_zh": meta.get("examples_zh"),
        }

    players: list[dict[str, str]] = []
    if show_players:
        for render in media.get("renders") or []:
            fname = Path(render.get("path") or "").name
            lower = fname.lower()
            batch_match = re.search(r"batch[_-]?(\d+)", lower)
            if "sample" in lower:
                label = "试片"
            elif "full_draft" in lower or "draft" in lower:
                label = "完整初稿"
            elif batch_match:
                label = f"第{int(batch_match.group(1))}批预览"
            elif "final" in lower:
                label = "终稿"
            else:
                label = fname
            players.append({"label": label, "path": render["path"]})

    spent_usd = None
    if cost and cost.get("total_spent_usd") is not None:
        spent_usd = float(cost["total_spent_usd"])
    elif artifacts.get("cost_log"):
        spent_usd = float((artifacts["cost_log"] or {}).get("budget_spent_usd") or 0)
    budget_cny = profile.get("budget_cny") or budget.get("budget_cny")
    spent_cny = round(spent_usd * usd_cny, 3) if spent_usd is not None else None
    remaining_cny = (
        round(float(budget_cny) - spent_cny, 3)
        if budget_cny is not None and spent_cny is not None
        else None
    )

    motion_mix = profile.get("motion_mix") or brief.get("motion_mix")
    motion_mix_zh = "运镜约 50% / AI 约 50%" if motion_mix == "1:1" else str(motion_mix or "")

    tier_labels = {"heavy": "重", "medium": "中", "light": "轻"}
    mode_labels = {"pro": "专业", "normal": "普通"}
    candidate_labels = {"stable_dual": "稳定双候选", "adaptive": "自适应"}

    return {
        "review_mode": review_mode,
        "card_mode": card_mode,
        "show_preview": show_preview,
        "show_players": show_players,
        "overall_prompt_zh": segment_doc.get("overall_prompt_zh"),
        "brief_summary": {
            "theme": brief.get("theme") or marker.get("title"),
            "duration_seconds": profile.get("duration_seconds") or brief.get("duration_seconds") or duration,
            "production_tier": tier_labels.get(profile.get("production_tier"), profile.get("production_tier")),
            "video_channel": (profile.get("video_channel") or brief.get("channel", {}).get("video_channel") or "").upper(),
            "review_mode_zh": mode_labels.get(review_mode, review_mode),
            "motion_mix_zh": motion_mix_zh,
            "budget_cny": budget_cny,
            "style_label_zh": profile.get("style_label_zh"),
            "video_model": profile.get("video_model") or brief.get("channel", {}).get("video_model"),
            "candidate_mode_zh": candidate_labels.get(profile.get("candidate_mode")),
        },
        "assets": images,
        "asset_precheck": {
            "summary": precheck_doc.get("summary") or {},
            "entries": precheck_doc.get("entries") or [],
        },
        "beats": beats,
        "timeline": {
            "duration_seconds": duration,
            "beat_marks": beat_marks,
            "batch_marks": batch_marks,
        },
        "batches": overview_doc.get("batches") or [],
        "batch_reviews": artifacts.get("batch_reviews") or {
            key: value
            for key, value in {
                "batch_01": artifacts.get("batch01_review"),
                "batch_02": artifacts.get("batch02_review"),
            }.items()
            if value is not None
        },
        "decision": decision,
        "players": players,
        "cost_cny": {
            "spent_cny": spent_cny,
            "spent_usd": spent_usd,
            "budget_cny": budget_cny,
            "remaining_cny": remaining_cny,
            "usd_cny_rate": usd_cny,
        },
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


def _last_activity(project_dir: Path) -> float:
    """Most recent mtime among state-bearing files (bounded scan)."""
    latest = 0.0
    try:
        candidates = list(project_dir.glob("checkpoint_*.json"))
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
        "live": bool(last_activity and (now - last_activity) < LIVE_WINDOW_SECONDS),
        "production_profile": marker.get("production_profile"),
    }
    if pipeline_type == "bootstrap-commercial":
        state["commercial"] = _build_commercial_board(
            project_dir, marker, artifacts, stages, media, cost,
        )
    state["poster"] = _find_poster(project_dir, state)
    return state


def summarize_project(project_dir: Path) -> dict[str, Any]:
    """Cheap library-card summary (no full artifact parse of big files)."""
    state = load_board_state(project_dir)
    active = next((s for s in state["stages"] if s["status"] in ("in_progress", "awaiting_human")), None)
    done = [s for s in state["stages"] if s["status"] == "completed"]
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
            for s in state["stages"] if not s.get("undeclared")
        ],
        "completed_count": len(done),
        "render_count": len(state["media"]["renders"]),
        "scene_count": len((state["storyboard"] or {}).get("scenes", [])),
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

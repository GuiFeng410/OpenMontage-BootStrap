"""Error capture / classify / plan / apply for BootStrap Error-Handling Skill.

Phase 3: safe auto apply (max 3) + zero-key ``replace_bgm`` /
``synthesize_replacement_bgm`` when confirm=true. Also ``probe_audio_loudness``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openmontage.mcp.common.errors import ConfigError, DoctorError
from openmontage.mcp.common.sandbox import project_dir, require_projects_root, resolve_under_projects

PLAYBOOKS_PATH = Path(__file__).resolve().parent / "error_playbooks.yaml"
RECOVERY_FILENAME = "error_recovery.json"
DEFAULT_MAX_RETRIES = 3

# Actions that always require confirm=true even if listed
HIGH_RISK_ACTION_IDS = frozenset(
    {
        "replace_bgm",
        "overwrite_or_delete_source_bgm",
        "restock_download",
        "synthesize_replacement_bgm",
        "overwrite_final_mp4",
        "any_recovery",
        "report_to_user",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_playbooks() -> dict[str, Any]:
    if not PLAYBOOKS_PATH.exists():
        raise DoctorError(f"playbooks missing: {PLAYBOOKS_PATH}", code="not_found")
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise DoctorError(
            "PyYAML required to load error_playbooks.yaml. pip install pyyaml",
            code="missing_dep",
        ) from exc
    data = yaml.safe_load(PLAYBOOKS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "playbooks" not in data:
        raise DoctorError("invalid error_playbooks.yaml structure", code="bad_config")
    return data


def _recovery_path(project_id: str) -> Path:
    require_projects_root()
    pdir = project_dir(project_id)
    if not pdir.exists():
        raise DoctorError(f"Project not found: {project_id}", code="not_found")
    art = pdir / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    return art / RECOVERY_FILENAME


def _load_state(project_id: str) -> dict[str, Any]:
    path = _recovery_path(project_id)
    if not path.exists():
        return {"version": 1, "project_id": project_id, "incidents": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DoctorError(f"corrupt {RECOVERY_FILENAME}: {exc}", code="bad_state") from exc
    if not isinstance(data, dict):
        raise DoctorError(f"invalid {RECOVERY_FILENAME}", code="bad_state")
    data.setdefault("incidents", {})
    data["project_id"] = project_id
    data.setdefault("version", 1)
    return data


def _save_state(project_id: str, state: dict[str, Any]) -> Path:
    path = _recovery_path(project_id)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _compile_flags(flags: str) -> int:
    result = 0
    for ch in (flags or ""):
        if ch == "i":
            result |= re.IGNORECASE
        elif ch == "m":
            result |= re.MULTILINE
        elif ch == "s":
            result |= re.DOTALL
    return result


def _haystack(stderr: str, stdout: str = "", tool_name: str = "", stage: str = "") -> str:
    parts = [stderr or "", stdout or "", tool_name or "", stage or ""]
    return "\n".join(parts)


def _score_playbook(pb: dict[str, Any], text: str) -> int:
    score = 0
    for rule in pb.get("match_any") or []:
        if not isinstance(rule, dict):
            continue
        pat = rule.get("pattern") or ""
        if not pat:
            continue
        try:
            if re.search(pat, text, _compile_flags(rule.get("flags") or "")):
                score += 2
        except re.error:
            continue
    for rule in pb.get("match_boost_if") or []:
        if not isinstance(rule, dict):
            continue
        pat = rule.get("pattern") or ""
        if not pat:
            continue
        try:
            if re.search(pat, text, _compile_flags(rule.get("flags") or "")):
                score += 1
        except re.error:
            continue
    return score


def classify_text(stderr: str, stdout: str = "", tool_name: str = "", stage: str = "") -> dict[str, Any]:
    """Match stderr against playbooks. Returns best playbook or E00_unknown."""
    catalog = _load_playbooks()
    text = _haystack(stderr, stdout, tool_name, stage)
    best: dict[str, Any] | None = None
    best_score = 0
    for pb in catalog.get("playbooks") or []:
        if not isinstance(pb, dict) or not pb.get("id"):
            continue
        sc = _score_playbook(pb, text)
        if sc > best_score:
            best_score = sc
            best = pb

    # Prefer E01 over E04 when loudness-specific signals present and both score.
    if best and best.get("id") == "E04_amix_aac_bitrate_collapse":
        loud_hit = bool(
            re.search(r"mean_volume:\s*-9\d|input_i:\s*-inf", text, re.IGNORECASE)
        )
        if loud_hit:
            for pb in catalog.get("playbooks") or []:
                if isinstance(pb, dict) and pb.get("id") == "E01_silent_bgm":
                    if _score_playbook(pb, text) > 0:
                        best = pb
                        best_score = max(best_score, 2)
                    break

    unknown = catalog.get("unknown") or {
        "id": "E00_unknown",
        "title_zh": "未匹配已知 playbook",
        "summary_zh": "未命中文档内已知错误",
        "risk_level": "high",
        "auto_allowed": False,
        "needs_confirm_for": ["any_recovery"],
        "planned_actions": [],
    }

    if not best or best_score <= 0:
        return {
            "playbook_id": unknown.get("id", "E00_unknown"),
            "confidence": 0.0,
            "risk_level": unknown.get("risk_level", "high"),
            "title_zh": unknown.get("title_zh", ""),
            "summary_zh": unknown.get("summary_zh", ""),
            "auto_allowed": False,
            "matched": False,
            "score": 0,
            "playbook": unknown,
        }

    # Confidence: crude but stable for phase 1
    confidence = min(0.95, 0.4 + 0.15 * best_score)
    return {
        "playbook_id": best["id"],
        "confidence": round(confidence, 2),
        "risk_level": best.get("risk_level", "medium"),
        "title_zh": best.get("title_zh", ""),
        "summary_zh": best.get("summary_zh", ""),
        "auto_allowed": bool(best.get("auto_allowed")),
        "matched": True,
        "score": best_score,
        "playbook": best,
    }


def error_capture_context(
    project_id: str,
    tool_name: str,
    stage: str,
    stderr: str,
    stdout: str = "",
    paths_json: str = "",
) -> dict[str, Any]:
    """Persist a new incident from tool stderr and return incident_id."""
    if not (stderr or "").strip() and not (stdout or "").strip():
        raise DoctorError("stderr or stdout required for error_capture_context", code="bad_request")

    paths: dict[str, Any] | list[Any] = {}
    if paths_json and paths_json.strip():
        try:
            parsed = json.loads(paths_json)
        except json.JSONDecodeError as exc:
            raise DoctorError(f"paths_json invalid: {exc}", code="bad_request") from exc
        if isinstance(parsed, (dict, list)):
            paths = parsed

    catalog = _load_playbooks()
    max_retries = int(catalog.get("max_retries") or DEFAULT_MAX_RETRIES)

    incident_id = f"inc_{uuid.uuid4().hex[:12]}"
    classification = classify_text(stderr, stdout=stdout, tool_name=tool_name, stage=stage)

    incident = {
        "incident_id": incident_id,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "tool_name": tool_name or "",
        "stage": stage or "",
        "stderr": (stderr or "")[:8000],
        "stdout": (stdout or "")[:4000],
        "paths": paths,
        "playbook_id": classification["playbook_id"],
        "classification": {
            "confidence": classification["confidence"],
            "risk_level": classification["risk_level"],
            "matched": classification["matched"],
            "score": classification["score"],
            "title_zh": classification["title_zh"],
        },
        "retry_count": 0,
        "max_retries": max_retries,
        "attempts": [],
        "status": "captured",
        "phase_note": "Phase 2: use error_plan_recovery then error_apply_recovery for safe auto actions.",
    }

    state = _load_state(project_id)
    state["incidents"][incident_id] = incident
    path = _save_state(project_id, state)

    return {
        "project_id": project_id,
        "incident_id": incident_id,
        "playbook_id": classification["playbook_id"],
        "matched": classification["matched"],
        "confidence": classification["confidence"],
        "title_zh": classification["title_zh"],
        "risk_level": classification["risk_level"],
        "auto_allowed": classification["auto_allowed"],
        "retry_count": 0,
        "max_retries": max_retries,
        "error_recovery_path": str(path),
        "next_step": "Call error_classify(incident_id) or error_plan_recovery(incident_id).",
    }


def error_classify(project_id: str, incident_id: str) -> dict[str, Any]:
    """Re-classify a stored incident (or return cached classification)."""
    state = _load_state(project_id)
    incident = state["incidents"].get(incident_id)
    if not incident:
        raise DoctorError(f"incident not found: {incident_id}", code="not_found")

    classification = classify_text(
        incident.get("stderr") or "",
        stdout=incident.get("stdout") or "",
        tool_name=incident.get("tool_name") or "",
        stage=incident.get("stage") or "",
    )
    incident["playbook_id"] = classification["playbook_id"]
    incident["classification"] = {
        "confidence": classification["confidence"],
        "risk_level": classification["risk_level"],
        "matched": classification["matched"],
        "score": classification["score"],
        "title_zh": classification["title_zh"],
    }
    incident["updated_at"] = _utc_now()
    incident["status"] = "classified"
    path = _save_state(project_id, state)

    return {
        "project_id": project_id,
        "incident_id": incident_id,
        "playbook_id": classification["playbook_id"],
        "confidence": classification["confidence"],
        "risk_level": classification["risk_level"],
        "title_zh": classification["title_zh"],
        "summary_zh": classification["summary_zh"],
        "auto_allowed": classification["auto_allowed"],
        "matched": classification["matched"],
        "score": classification["score"],
        "retry_count": incident.get("retry_count", 0),
        "max_retries": incident.get("max_retries", DEFAULT_MAX_RETRIES),
        "error_recovery_path": str(path),
        "next_step": "Call error_plan_recovery(incident_id).",
    }


def error_plan_recovery(
    project_id: str,
    incident_id: str,
    playbook_id: str = "",
) -> dict[str, Any]:
    """Build a recovery plan for an incident. Does not execute (phase 1)."""
    catalog = _load_playbooks()
    state = _load_state(project_id)
    incident = state["incidents"].get(incident_id)
    if not incident:
        raise DoctorError(f"incident not found: {incident_id}", code="not_found")

    # Ensure classification is fresh
    classification = classify_text(
        incident.get("stderr") or "",
        stdout=incident.get("stdout") or "",
        tool_name=incident.get("tool_name") or "",
        stage=incident.get("stage") or "",
    )
    chosen_id = (playbook_id or "").strip() or classification["playbook_id"]

    pb: dict[str, Any] | None = None
    for item in catalog.get("playbooks") or []:
        if isinstance(item, dict) and item.get("id") == chosen_id:
            pb = item
            break
    if pb is None and chosen_id == (catalog.get("unknown") or {}).get("id", "E00_unknown"):
        pb = catalog.get("unknown")
    if pb is None and chosen_id == "E00_unknown":
        pb = catalog.get("unknown")
    if pb is None:
        # override requested but missing → unknown
        pb = catalog.get("unknown") or {"id": "E00_unknown", "planned_actions": [], "auto_allowed": False}
        chosen_id = pb.get("id", "E00_unknown")

    retry_count = int(incident.get("retry_count") or 0)
    max_retries = int(incident.get("max_retries") or catalog.get("max_retries") or DEFAULT_MAX_RETRIES)
    retries_left = max(0, max_retries - retry_count)

    needs_confirm_for = list(pb.get("needs_confirm_for") or [])
    actions = []
    for act in pb.get("planned_actions") or []:
        if not isinstance(act, dict):
            continue
        auto = bool(act.get("auto")) and bool(pb.get("auto_allowed")) and chosen_id != "E00_unknown"
        actions.append(
            {
                "id": act.get("id"),
                "description_zh": act.get("description_zh", ""),
                "auto": auto,
                "needs_confirm": not auto,
            }
        )

    # Exhausted retries → force stop auto
    exhausted = retries_left <= 0
    auto_allowed = bool(pb.get("auto_allowed")) and not exhausted and chosen_id != "E00_unknown"
    if exhausted:
        for a in actions:
            a["auto"] = False
            a["needs_confirm"] = True

    plan = {
        "playbook_id": chosen_id,
        "title_zh": pb.get("title_zh", classification.get("title_zh", "")),
        "summary_zh": pb.get("summary_zh", classification.get("summary_zh", "")),
        "risk_level": pb.get("risk_level", classification.get("risk_level", "high")),
        "auto_allowed": auto_allowed,
        "needs_confirm_for": needs_confirm_for,
        "actions": actions,
        "post_check": pb.get("post_check") or {},
        "retry_count": retry_count,
        "max_retries": max_retries,
        "retries_left": retries_left,
        "exhausted": exhausted,
        "phase": 2,
        "apply_available": True,
        "user_message_zh": (
            f"已匹配 {chosen_id}：{pb.get('title_zh', '')}。"
            + (
                " 重试次数已用尽，请人工处理。"
                if exhausted
                else (
                    " 可对 auto 动作调用 error_apply_recovery；高危动作须 confirm=true。"
                    if auto_allowed
                    else " 需用户确认后再 apply（付费/覆盖素材等高危项）。"
                )
            )
        ),
    }

    incident["playbook_id"] = chosen_id
    incident["last_plan"] = plan
    incident["status"] = "planned"
    incident["updated_at"] = _utc_now()
    path = _save_state(project_id, state)

    return {
        "project_id": project_id,
        "incident_id": incident_id,
        "plan": plan,
        "error_recovery_path": str(path),
        "next_step": (
            "Stop auto-recovery; show plan to user."
            if exhausted or not auto_allowed
            else "Call error_apply_recovery(incident_id) for safe auto actions, then retry the original tool."
        ),
    }


def error_list_incidents(project_id: str) -> dict[str, Any]:
    """List stored incidents for a project (debug / Skill)."""
    state = _load_state(project_id)
    rows = []
    for iid, inc in (state.get("incidents") or {}).items():
        rows.append(
            {
                "incident_id": iid,
                "tool_name": inc.get("tool_name"),
                "stage": inc.get("stage"),
                "playbook_id": inc.get("playbook_id"),
                "status": inc.get("status"),
                "retry_count": inc.get("retry_count", 0),
                "created_at": inc.get("created_at"),
            }
        )
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {
        "project_id": project_id,
        "count": len(rows),
        "incidents": rows,
        "error_recovery_path": str(_recovery_path(project_id)),
    }


def probe_audio_loudness(path: str) -> dict[str, Any]:
    """Run ffmpeg volumedetect on a sandboxed audio file."""
    resolved = resolve_under_projects(path)
    if not resolved.exists():
        raise DoctorError(f"Media not found: {resolved}", code="not_found")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ConfigError("ffmpeg not found on PATH (needed for volumedetect)")

    proc = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(resolved),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    # volumedetect logs to stderr
    log = (proc.stderr or "") + "\n" + (proc.stdout or "")
    mean_m = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", log, re.IGNORECASE)
    max_m = re.search(r"max_volume:\s*([-\d.]+)\s*dB", log, re.IGNORECASE)
    mean_db = float(mean_m.group(1)) if mean_m else None
    max_db = float(max_m.group(1)) if max_m else None
    silent = mean_db is not None and mean_db <= -40.0
    return {
        "path": str(resolved),
        "mean_volume_db": mean_db,
        "max_volume_db": max_db,
        "likely_silent": silent,
        "ffmpeg_returncode": proc.returncode,
        "stderr_tail": log[-2000:],
    }


def _playbook_by_id(catalog: dict[str, Any], playbook_id: str) -> dict[str, Any]:
    for item in catalog.get("playbooks") or []:
        if isinstance(item, dict) and item.get("id") == playbook_id:
            return item
    unknown = catalog.get("unknown") or {"id": "E00_unknown", "planned_actions": [], "auto_allowed": False}
    if playbook_id in {unknown.get("id"), "E00_unknown"}:
        return unknown
    raise DoctorError(f"unknown playbook_id: {playbook_id}", code="not_found")


def _parse_action_ids(action_ids: str) -> list[str] | None:
    raw = (action_ids or "").strip()
    if not raw:
        return None
    if raw.startswith("["):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DoctorError(f"action_ids JSON invalid: {exc}", code="bad_request") from exc
        if not isinstance(data, list):
            raise DoctorError("action_ids JSON must be a list", code="bad_request")
        return [str(x).strip() for x in data if str(x).strip()]
    return [p.strip() for p in raw.split(",") if p.strip()]


def _incident_paths(incident: dict[str, Any]) -> dict[str, Any]:
    paths = incident.get("paths") or {}
    return paths if isinstance(paths, dict) else {}


def _find_project_subtitle(project_id: str, paths: dict[str, Any]) -> Path | None:
    pdir = project_dir(project_id)
    candidates: list[Path] = []
    for key in ("subtitle", "subtitle_path", "srt", "subs"):
        val = paths.get(key)
        if isinstance(val, str) and val.strip():
            try:
                candidates.append(resolve_under_projects(val))
            except Exception:  # noqa: BLE001
                # Absolute path outside sandbox: only accept if under project via string check
                p = Path(val)
                if p.exists() and p.is_file():
                    try:
                        p.resolve().relative_to(pdir.resolve())
                        candidates.append(p.resolve())
                    except ValueError:
                        pass
    subs = pdir / "assets" / "subs"
    if subs.exists():
        for p in sorted(subs.rglob("*")):
            if p.is_file() and p.suffix.lower() in {".srt", ".vtt"} and "_work" not in p.parts:
                candidates.append(p)
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def _find_project_music(project_id: str, paths: dict[str, Any]) -> Path | None:
    pdir = project_dir(project_id)
    for key in ("music", "music_path", "bgm", "secondary_audio"):
        val = paths.get(key)
        if isinstance(val, str) and val.strip():
            try:
                p = resolve_under_projects(val)
                if p.exists():
                    return p
            except Exception:  # noqa: BLE001
                continue
    music_dir = pdir / "assets" / "music"
    if music_dir.exists():
        for p in sorted(music_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}:
                return p
    return None


def _action_copy_srt_to_work(project_id: str, incident: dict[str, Any]) -> dict[str, Any]:
    paths = _incident_paths(incident)
    src = _find_project_subtitle(project_id, paths)
    if src is None:
        raise DoctorError(
            "No subtitle file found under project assets/subs or paths.subtitle. "
            "Put an SRT in the project sandbox and re-capture with paths_json.",
            code="not_found",
        )
    pdir = project_dir(project_id)
    work = pdir / "assets" / "subs" / "_work"
    work.mkdir(parents=True, exist_ok=True)
    dest = work / "captions.srt"
    # Always write as .srt name for filter simplicity
    if src.suffix.lower() != ".srt":
        dest = work / f"captions{src.suffix.lower()}"
    shutil.copy2(src, dest)
    rel = dest.relative_to(pdir).as_posix()
    # Update manifest subtitle path if present
    try:
        from openmontage.mcp.common.asset_manifest import load_asset_manifest, save_asset_manifest

        manifest = load_asset_manifest(project_id)
        changed = False
        for a in manifest.get("assets") or []:
            if isinstance(a, dict) and a.get("type") == "subtitle":
                a["path"] = rel
                a["path_note"] = "relocated to relative path for FFmpeg Windows colon fix (E02)"
                changed = True
        if changed:
            save_asset_manifest(project_id, manifest)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": True,
            "action": "copy_srt_to_work_relpath",
            "source": str(src),
            "work_path": str(dest),
            "relative_path": rel,
            "ffmpeg_subtitles_arg": f"subtitles={rel}",
            "manifest_update_error": str(exc),
        }
    return {
        "ok": True,
        "action": "copy_srt_to_work_relpath",
        "source": str(src),
        "work_path": str(dest),
        "relative_path": rel,
        "ffmpeg_subtitles_arg": f"subtitles={rel}",
        "hint": "Retry compose using relative_path (no drive letter).",
    }


def _action_retry_compose_hint(project_id: str, prior: dict[str, Any] | None) -> dict[str, Any]:
    rel = None
    if prior and prior.get("relative_path"):
        rel = prior["relative_path"]
    else:
        pdir = project_dir(project_id)
        work = pdir / "assets" / "subs" / "_work" / "captions.srt"
        if work.exists():
            rel = work.relative_to(pdir).as_posix()
    return {
        "ok": True,
        "action": "retry_compose_with_relpath",
        "relative_path": rel,
        "hint": (
            "Agent should call produce_compose_preflight/start with subtitle path "
            f"{rel!r} (relative, no D:)."
            if rel
            else "Run copy_srt_to_work_relpath first."
        ),
    }


def _action_rerun_python_subprocess(incident: dict[str, Any]) -> dict[str, Any]:
    paths = _incident_paths(incident)
    cmd = paths.get("command") or paths.get("argv")
    if isinstance(cmd, str) and cmd.strip().startswith("["):
        try:
            cmd = json.loads(cmd)
        except json.JSONDecodeError:
            cmd = None
    if not isinstance(cmd, list) or not cmd:
        return {
            "ok": True,
            "action": "rerun_via_python_subprocess_list",
            "executed": False,
            "hint": (
                "No paths.command list provided. Do NOT use PowerShell string invocation; "
                "re-run FFmpeg via Python subprocess.run([...], shell=False). "
                "Re-capture with paths_json={\"command\":[\"ffmpeg\",...]} to auto-execute."
            ),
        }
    # Safety: only allow ffmpeg/ffprobe style commands
    bin0 = str(cmd[0]).lower()
    if not any(x in bin0 for x in ("ffmpeg", "ffprobe", "python")):
        raise DoctorError(
            f"Refusing to auto-run non-media command: {cmd[0]!r}",
            code="unsafe_command",
        )
    proc = subprocess.run(
        [str(c) for c in cmd],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        shell=False,
    )
    return {
        "ok": proc.returncode == 0,
        "action": "rerun_via_python_subprocess_list",
        "executed": True,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-1500:],
    }


def _action_loudness_check(project_id: str, incident: dict[str, Any]) -> dict[str, Any]:
    music = _find_project_music(project_id, _incident_paths(incident))
    if music is None:
        raise DoctorError("No music file found for loudness_check", code="not_found")
    try:
        rel = music.relative_to(require_projects_root()).as_posix()
    except ValueError:
        rel = str(music)
    loud = probe_audio_loudness(rel)
    return {"ok": True, "action": "loudness_check", **loud}


def _action_mark_manifest_invalid(project_id: str, incident: dict[str, Any]) -> dict[str, Any]:
    from openmontage.mcp.common.asset_manifest import load_asset_manifest, save_asset_manifest

    manifest = load_asset_manifest(project_id)
    marked: list[str] = []
    for a in manifest.get("assets") or []:
        if not isinstance(a, dict):
            continue
        if a.get("type") in {"music", "audio"} or a.get("subtype") in {"stock", "bgm"}:
            # Prefer music-typed or music_bgm id
            if a.get("type") == "music" or str(a.get("id", "")).startswith("music"):
                a["invalid"] = True
                a["invalid_reason"] = "E01_silent_bgm: loudness/bitrate collapse"
                marked.append(str(a.get("id")))
    if not marked:
        for a in manifest.get("assets") or []:
            if isinstance(a, dict) and a.get("type") == "music":
                a["invalid"] = True
                a["invalid_reason"] = "E01_silent_bgm"
                marked.append(str(a.get("id")))
    save_asset_manifest(project_id, manifest)
    return {
        "ok": True,
        "action": "mark_manifest_invalid",
        "marked_ids": marked,
        "hint": "Call produce_build_compose_inputs(include_music=false) or replace BGM after confirm.",
    }


def _action_skip_bgm(project_id: str) -> dict[str, Any]:
    pdir = project_dir(project_id)
    art = pdir / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    hint_path = art / "recovery_hints.json"
    data = {"include_music": False, "reason": "E01_silent_bgm", "updated_at": _utc_now()}
    hint_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "action": "skip_bgm_continue",
        "hints_path": str(hint_path),
        "hint": "Retry compose with produce_build_compose_inputs(..., include_music=false).",
    }


def _action_two_step_encode(project_id: str, incident: dict[str, Any]) -> dict[str, Any]:
    paths = _incident_paths(incident)
    pdir = project_dir(project_id)
    src: Path | None = None
    for key in ("mixed_path", "input_audio", "wav", "primary_audio"):
        val = paths.get(key)
        if isinstance(val, str) and val.strip():
            try:
                cand = resolve_under_projects(val)
                if cand.exists():
                    src = cand
                    break
            except Exception:  # noqa: BLE001
                continue
    if src is None:
        audio_dir = pdir / "assets" / "audio"
        if audio_dir.exists():
            for name in ("mixed.wav", "narration.wav"):
                cand = audio_dir / name
                if cand.exists():
                    src = cand
                    break
            if src is None:
                waves = sorted(audio_dir.glob("*.wav"))
                if waves:
                    src = waves[0]
    if src is None:
        raise DoctorError(
            "two_step_encode needs a WAV/PCM input under assets/audio or paths.mixed_path",
            code="not_found",
        )
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ConfigError("ffmpeg not found on PATH")
    out_dir = pdir / "assets" / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "mixed_128k.m4a"
    # If source is already wav, encode AAC; if not wav, first ensure pcm via intermediate
    mid = out_dir / "_e04_mid.wav"
    if src.suffix.lower() != ".wav":
        proc1 = subprocess.run(
            [ffmpeg, "-y", "-i", str(src), "-c:a", "pcm_s16le", str(mid)],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if proc1.returncode != 0:
            raise DoctorError(
                f"E04 step1 wav failed: {(proc1.stderr or '')[-1500:]}",
                code="encode_failed",
            )
        encode_in = mid
    else:
        encode_in = src
    proc2 = subprocess.run(
        [ffmpeg, "-y", "-i", str(encode_in), "-c:a", "aac", "-b:a", "128k", str(out)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if proc2.returncode != 0 or not out.exists():
        raise DoctorError(
            f"E04 step2 aac failed: {(proc2.stderr or '')[-1500:]}",
            code="encode_failed",
        )
    rel = out.relative_to(pdir).as_posix()
    return {
        "ok": True,
        "action": "two_step_encode",
        "input": str(src),
        "output": str(out),
        "relative_path": rel,
        "bitrate": "128k",
        "stderr_tail": (proc2.stderr or "")[-800:],
    }


def _action_verify_bitrate(project_id: str, prior: dict[str, Any] | None, incident: dict[str, Any]) -> dict[str, Any]:
    pdir = project_dir(project_id)
    target: Path | None = None
    if prior and prior.get("output"):
        target = Path(str(prior["output"]))
    if target is None or not target.exists():
        cand = pdir / "assets" / "audio" / "mixed_128k.m4a"
        if cand.exists():
            target = cand
    if target is None or not target.exists():
        paths = _incident_paths(incident)
        for key in ("output", "mixed_path"):
            val = paths.get(key)
            if isinstance(val, str) and val.strip():
                try:
                    p = resolve_under_projects(val)
                    if p.exists():
                        target = p
                        break
                except Exception:  # noqa: BLE001
                    continue
    if target is None or not target.exists():
        raise DoctorError("verify_bitrate: no output media found", code="not_found")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise ConfigError("ffprobe not found on PATH")
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=bit_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    raw = (proc.stdout or "").strip().splitlines()
    bitrate = None
    if raw and raw[0].isdigit():
        bitrate = int(raw[0])
    kbps = round(bitrate / 1000.0, 1) if bitrate else None
    ok = kbps is not None and kbps >= 64
    return {
        "ok": ok,
        "action": "verify_bitrate",
        "path": str(target),
        "bit_rate": bitrate,
        "bit_rate_kbps": kbps,
        "passed": ok,
        "stderr_tail": (proc.stderr or "")[-500:],
    }


def _action_replace_or_synth_bgm(
    project_id: str,
    action_id: str,
    *,
    duration_seconds: float = 64.0,
) -> dict[str, Any]:
    """E01 high-risk: synthesize ambient BGM and re-register (confirm already gated)."""
    from openmontage.mcp.common.synth_bgm import synthesize_and_register_bgm

    out = synthesize_and_register_bgm(
        project_id,
        duration_seconds=duration_seconds,
        filename="synth_ambient.wav",
        asset_id="music_bgm",
        archive_invalid=True,
    )
    return {
        "ok": True,
        "action": action_id,
        **out,
        "hint": (
            "BGM replaced with zero-key synth_ambient.wav. "
            "Retry produce_build_compose_inputs / mix / compose."
        ),
    }


def _run_action(
    project_id: str,
    action_id: str,
    incident: dict[str, Any],
    results_so_far: list[dict[str, Any]],
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    prior = next((r for r in reversed(results_so_far) if r.get("ok")), None)
    if action_id == "copy_srt_to_work_relpath":
        return _action_copy_srt_to_work(project_id, incident)
    if action_id == "retry_compose_with_relpath":
        return _action_retry_compose_hint(project_id, prior)
    if action_id == "rerun_via_python_subprocess_list":
        return _action_rerun_python_subprocess(incident)
    if action_id == "loudness_check":
        return _action_loudness_check(project_id, incident)
    if action_id == "mark_manifest_invalid":
        return _action_mark_manifest_invalid(project_id, incident)
    if action_id == "skip_bgm_continue":
        return _action_skip_bgm(project_id)
    if action_id == "two_step_encode":
        return _action_two_step_encode(project_id, incident)
    if action_id == "verify_bitrate":
        return _action_verify_bitrate(project_id, prior, incident)
    if action_id in {"replace_bgm", "synthesize_replacement_bgm"}:
        if not confirm:
            raise ConfigError(
                f"{action_id} requires confirm=true after the user approved replacing BGM."
            )
        paths = _incident_paths(incident)
        dur = 64.0
        if isinstance(paths.get("duration_seconds"), (int, float)):
            dur = float(paths["duration_seconds"])
        return _action_replace_or_synth_bgm(project_id, action_id, duration_seconds=dur)
    if action_id in HIGH_RISK_ACTION_IDS:
        return {
            "ok": False,
            "action": action_id,
            "skipped": True,
            "reason": (
                "High-risk action not auto-implemented here "
                "(restock_download / overwrite_final_mp4). Handle via Stock/produce Skill with confirm."
            ),
        }
    raise DoctorError(f"Unsupported action_id for apply: {action_id}", code="bad_request")


def error_apply_recovery(
    project_id: str,
    incident_id: str,
    confirm: bool = False,
    action_ids: str = "",
) -> dict[str, Any]:
    """Execute safe recovery actions for an incident. Increments retry_count (max 3)."""
    from openmontage.mcp.doctor.tools import require_p1_writes

    require_p1_writes()
    catalog = _load_playbooks()
    state = _load_state(project_id)
    incident = state["incidents"].get(incident_id)
    if not incident:
        raise DoctorError(f"incident not found: {incident_id}", code="not_found")

    retry_count = int(incident.get("retry_count") or 0)
    max_retries = int(incident.get("max_retries") or catalog.get("max_retries") or DEFAULT_MAX_RETRIES)
    if retry_count >= max_retries:
        raise DoctorError(
            f"Retry budget exhausted ({retry_count}/{max_retries}). Manual intervention required.",
            code="retries_exhausted",
        )

    playbook_id = incident.get("playbook_id") or "E00_unknown"
    pb = _playbook_by_id(catalog, playbook_id)
    if playbook_id == "E00_unknown" or not pb.get("auto_allowed"):
        if not confirm:
            raise ConfigError(
                "This playbook is not auto_allowed. Set confirm=true only after user approved a manual plan."
            )

    planned = [a for a in (pb.get("planned_actions") or []) if isinstance(a, dict) and a.get("id")]
    requested = _parse_action_ids(action_ids)
    if requested is None:
        to_run = [str(a["id"]) for a in planned if a.get("auto")]
    else:
        known = {str(a["id"]) for a in planned}
        unknown = [x for x in requested if x not in known]
        if unknown:
            raise DoctorError(f"action_ids not in playbook: {unknown}", code="bad_request")
        to_run = requested

    if not to_run:
        raise DoctorError("No actions to apply", code="bad_request")

    auto_map = {str(a["id"]): bool(a.get("auto")) for a in planned}
    needs_confirm = any(
        (aid in HIGH_RISK_ACTION_IDS) or (not auto_map.get(aid, False)) for aid in to_run
    )
    if needs_confirm and not confirm:
        raise ConfigError(
            "error_apply_recovery requires confirm=true for high-risk or non-auto actions: "
            + ", ".join(to_run)
        )

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for aid in to_run:
        try:
            results.append(_run_action(project_id, aid, incident, results, confirm=confirm))
        except Exception as exc:  # noqa: BLE001
            err = {"ok": False, "action": aid, "error": str(exc)}
            results.append(err)
            errors.append(f"{aid}: {exc}")

    incident["retry_count"] = retry_count + 1
    attempt = {
        "at": _utc_now(),
        "actions": to_run,
        "confirm": confirm,
        "results": results,
        "errors": errors,
    }
    incident.setdefault("attempts", []).append(attempt)
    incident["updated_at"] = _utc_now()
    all_ok = all(bool(r.get("ok")) for r in results) if results else False
    incident["status"] = "applied_ok" if all_ok and not errors else "applied_partial"
    if incident["retry_count"] >= max_retries and not all_ok:
        incident["status"] = "exhausted"
    path = _save_state(project_id, state)

    return {
        "project_id": project_id,
        "incident_id": incident_id,
        "playbook_id": playbook_id,
        "actions_run": to_run,
        "results": results,
        "errors": errors,
        "all_ok": all_ok,
        "retry_count": incident["retry_count"],
        "max_retries": max_retries,
        "retries_left": max(0, max_retries - incident["retry_count"]),
        "status": incident["status"],
        "error_recovery_path": str(path),
        "next_step": (
            "Retry the original tool (compose/mix) using recovered paths from results."
            if all_ok
            else "Inspect results/errors; confirm high-risk actions or stop after budget."
        ),
    }

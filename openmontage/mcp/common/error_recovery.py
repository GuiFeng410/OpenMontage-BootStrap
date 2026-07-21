"""Error capture / classify / plan for BootStrap Error-Handling Skill (phase 1).

Phase 1 does NOT auto-apply recoveries. It persists incidents under
``<project>/artifacts/error_recovery.json`` and returns a recovery plan.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openmontage.mcp.common.errors import DoctorError
from openmontage.mcp.common.sandbox import project_dir, require_projects_root

PLAYBOOKS_PATH = Path(__file__).resolve().parent / "error_playbooks.yaml"
RECOVERY_FILENAME = "error_recovery.json"
DEFAULT_MAX_RETRIES = 3


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
        "phase1_note": "Phase 1: classify/plan only; error_apply_recovery not implemented yet.",
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
        "phase": 1,
        "apply_available": False,
        "user_message_zh": (
            f"已匹配 {chosen_id}：{pb.get('title_zh', '')}。"
            + (
                " 重试次数已用尽，请人工处理。"
                if exhausted
                else (
                    " 阶段一仅给出修复计划，请按 Skill 指引手动执行安全步骤；"
                    "阶段二将支持 error_apply_recovery 自动重试。"
                    if auto_allowed
                    else " 需用户确认后再执行（付费/覆盖素材等高危项）。"
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
        "phase1_note": (
            "error_apply_recovery is not available in phase 1. "
            "Agent should follow planned_actions manually within Skill guidance, "
            "respect needs_confirm_for, and increment retry_count via a future apply call."
        ),
        "next_step": (
            "Stop auto-recovery; show plan to user."
            if exhausted or not auto_allowed
            else "Follow Skill openmontage-bootstrap-error-handling: execute safe planned_actions manually, then retry original tool."
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

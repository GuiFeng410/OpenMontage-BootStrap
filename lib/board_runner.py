"""Local Backlot-side consumer for pending interaction intents.

The browser only writes intents. This runner applies panel decisions and
end-and-export requests, then records board-visible progress. It does not
call paid generate APIs and does not silently switch providers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import lib.approval_bundle as approval_bundle
import lib.board_advance as board_advance
import lib.interaction_intents as intents
import lib.project_export as project_export
from lib.paths import PROJECTS_DIR

PHASE_IDLE = "idle"
PHASE_QUEUED = "queued"
PHASE_APPLYING = "applying"
PHASE_PRODUCING = "producing"
PHASE_PAUSED = "paused"
PHASE_READY = "ready"
PHASE_EXPORTED = "exported"
PHASE_NEEDS_CHAT = "needs_chat"


def _list_pending(project_id: str) -> list[dict[str, Any]]:
    listed = []
    for item in approval_bundle.list_interaction_intents(project_id):
        if item.get("status") == "pending":
            listed.append(item)
    return listed


def _has_final(project_id: str) -> bool:
    path = project_export._final_path(project_id)
    return path.is_file() and path.stat().st_size > 0


def _consume_export(project_id: str, pending: list[dict[str, Any]]) -> dict[str, Any] | None:
    exports = [item for item in pending if item.get("intent_type") == "project_export"]
    if not exports:
        return None
    latest = exports[-1]
    return project_export.apply_project_export(
        project_id,
        intent_id=str(latest["intent_id"]),
    )


def _peek_intent(project_id: str, intent_id: str) -> dict[str, Any]:
    path = intents._intent_path(intents._project_dir(project_id), intent_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _complete_brief_locked(
    project_id: str,
    artifacts: dict[str, Any],
) -> None:
    from lib.checkpoint import merge_write_checkpoint

    merge_write_checkpoint(
        PROJECTS_DIR,
        project_id,
        "brief_locked",
        "completed",
        {
            "brief": artifacts["brief"],
            "asset_precheck": artifacts["asset_precheck"],
            "video_plan": artifacts["video_plan"],
            "segment_cards": artifacts["segment_cards"],
        },
        pipeline_type="bootstrap-commercial",
        human_approval_required=True,
        human_approved=True,
        metadata_patch={
            "needs_user_decision": False,
            "approval_source": "panel_intent",
        },
        metadata_remove_keys=board_advance.DECISION_STALE_KEYS,
    )


def _consume_decision(
    project_id: str,
    pending: list[dict[str, Any]],
    *,
    append_decision: Callable[[str, str], Any],
) -> dict[str, Any] | None:
    decisions = [
        item
        for item in pending
        if item.get("intent_type") in {"decision", "approval_bundle"}
    ]
    if not decisions:
        return None
    item = decisions[-1]
    intent_id = str(item["intent_id"])
    revision = str(item["revision"])
    raw = _peek_intent(project_id, intent_id)
    stage = str(raw.get("stage") or item.get("stage") or "")
    lock_result: dict[str, Any] | None = None
    if stage == "brief_locked":
        from lib.board_gap_plan import GapPlanError, lock_gap_plan_from_intent

        try:
            lock_result = lock_gap_plan_from_intent(
                project_id,
                raw,
                projects_dir=PROJECTS_DIR,
            )
        except GapPlanError as exc:
            raise approval_bundle.ApprovalBundleError(
                str(exc),
                code=exc.code,
                safe_message=exc.safe_message,
            ) from exc
        if lock_result.get("action") == "continue" and lock_result.get("artifacts"):
            try:
                _complete_brief_locked(project_id, lock_result["artifacts"])
            except Exception as exc:
                raise approval_bundle.ApprovalBundleError(
                    str(exc),
                    code="brief_lock_failed",
                    safe_message="方案已选出，但本机无法写入合法规划。请留在本页刷新后重试。",
                ) from exc
    planned = approval_bundle.plan_approval_bundle(
        project_id,
        intent_id,
        checkpoint_revision=revision,
    )
    applied = approval_bundle.apply_approval_bundle(
        project_id,
        intent_id,
        confirm_phrase=approval_bundle.CONFIRM_PHRASE,
        checkpoint_revision=revision,
        append_decision=append_decision,
    )
    return {
        "planned": planned,
        "applied": applied,
        "intent_id": intent_id,
        "stop_action": (lock_result or {}).get("action") or "continue",
    }


def tick(
    project_id: str,
    *,
    append_decision: Callable[[str, str], Any],
    runner_alive: bool = True,
) -> dict[str, Any]:
    """Consume one round of pending intents for a project. Never calls paid generate."""
    marker = project_export.read_marker(project_id)
    if project_export.is_completed(marker):
        status = {
            "phase": PHASE_EXPORTED,
            "runner_alive": runner_alive,
            "friendly_zh": "项目已结束并导出，不再自动续做。",
            "export_path": marker.get("export_path"),
        }
        project_export.write_runner_status(project_id, status)
        return {"project_id": project_id, **status, "actions": []}

    pending = _list_pending(project_id)
    actions: list[str] = []

    export_result = _consume_export(project_id, pending)
    if export_result is not None:
        actions.append("project_export")
        phase = PHASE_EXPORTED if export_result.get("ok") else PHASE_PAUSED
        status = {
            "phase": phase,
            "runner_alive": runner_alive,
            "friendly_zh": export_result.get("friendly_zh"),
            "export_path": export_result.get("export_path"),
        }
        if phase != PHASE_EXPORTED:
            project_export.write_runner_status(project_id, status)
        return {"project_id": project_id, **status, "actions": actions, "export": export_result}

    if pending:
        project_export.write_runner_status(
            project_id,
            {
                "phase": PHASE_APPLYING,
                "runner_alive": runner_alive,
                "friendly_zh": "已收到看板选择，本机正在处理，请留在本页。",
            },
        )
        try:
            applied = _consume_decision(
                project_id,
                pending,
                append_decision=append_decision,
            )
        except approval_bundle.ApprovalBundleError as exc:
            status = {
                "phase": PHASE_PAUSED,
                "runner_alive": runner_alive,
                "friendly_zh": getattr(exc, "safe_message", None)
                or "本机无法自动确认这笔选择。请留在本页，或点刷新重试。",
                "current_question": "请留在本页，或点刷新重试。",
            }
            project_export.write_runner_status(project_id, status)
            return {
                "project_id": project_id,
                **status,
                "actions": actions,
                "error": str(exc),
            }
        if applied:
            actions.append("approval_bundle")
            applied_stage = str((applied.get("applied") or {}).get("intent", {}).get("stage") or "")
            if not applied_stage:
                applied_stage = str((applied.get("planned") or {}).get("intent", {}).get("stage") or "")
            next_stop = None
            try:
                marker = board_advance.read_marker(
                    project_id, projects_dir=PROJECTS_DIR
                ) or marker
                stop_action = str(applied.get("stop_action") or "continue")
                if stop_action != "revise":
                    next_stop = board_advance.advance_after_apply(
                        project_id,
                        applied_stage or "brief_locked",
                        marker,
                        projects_dir=PROJECTS_DIR,
                    )
            except Exception:
                next_stop = None
            if next_stop:
                actions.append("next_stop")

    seeded = None
    if "approval_bundle" not in actions:
        try:
            marker = board_advance.read_marker(
                project_id, projects_dir=PROJECTS_DIR
            ) or marker
            profile = (
                marker.get("production_profile")
                if isinstance(marker.get("production_profile"), dict)
                else {}
            )
            if profile.get("production_start_requested_at") or profile.get(
                "runner_start_pending"
            ):
                seeded = board_advance.ensure_current_stop_card(
                    project_id,
                    marker,
                    projects_dir=PROJECTS_DIR,
                )
                if seeded:
                    actions.append("seed_stop")
        except Exception:
            seeded = None

    if _has_final(project_id):
        status = {
            "phase": PHASE_READY,
            "runner_alive": runner_alive,
            "friendly_zh": "成片已在本页。要结束这单，请点「结束并导出项目」。",
        }
        project_export.write_runner_status(project_id, status)
        return {"project_id": project_id, **status, "actions": actions}

    remaining = _list_pending(project_id)
    if remaining:
        status = {
            "phase": PHASE_QUEUED,
            "runner_alive": runner_alive,
            "friendly_zh": "选择已提交，本机排队处理中，请留在本页。",
        }
    elif "next_stop" in actions:
        status = {
            "phase": PHASE_PRODUCING,
            "runner_alive": runner_alive,
            "friendly_zh": "面板选择已生效。下一停点已在本页，请点「进入下一步」。本机不会静默付费生视频。",
        }
    elif "seed_stop" in actions or seeded:
        status = {
            "phase": PHASE_PRODUCING,
            "runner_alive": runner_alive,
            "friendly_zh": "已锁定制作档。请在本页确认当前停点后点「进入下一步」。本机不会静默付费生视频。",
        }
    elif actions:
        status = {
            "phase": PHASE_PRODUCING,
            "runner_alive": runner_alive,
            "friendly_zh": "面板选择已生效。请留在本页查看下一停点。本机不会静默付费生视频。",
        }
    else:
        status = {
            "phase": PHASE_IDLE,
            "runner_alive": runner_alive,
            "friendly_zh": "本机 runner 空闲。点选后请留在本页等待。",
        }
    project_export.write_runner_status(project_id, status)
    return {"project_id": project_id, **status, "actions": actions}


def list_project_ids(projects_dir: Path | None = None) -> list[str]:
    root = Path(projects_dir or PROJECTS_DIR)
    if not root.is_dir():
        return []
    found: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "project.json").is_file():
            found.append(child.name)
    return found


def tick_all(
    *,
    append_decision: Callable[[str, str], Any],
    project_id: str = "",
    runner_alive: bool = True,
) -> dict[str, Any]:
    ids = [project_id] if project_id.strip() else list_project_ids()
    results = []
    for item in ids:
        try:
            results.append(
                tick(item, append_decision=append_decision, runner_alive=runner_alive)
            )
        except intents.UnknownProjectError as exc:
            results.append({"project_id": item, "phase": PHASE_PAUSED, "error": str(exc)})
        except project_export.ProjectExportError as exc:
            results.append(
                {
                    "project_id": item,
                    "phase": PHASE_PAUSED,
                    "friendly_zh": exc.safe_message,
                    "error": str(exc),
                }
            )
    return {"projects": results, "count": len(results)}

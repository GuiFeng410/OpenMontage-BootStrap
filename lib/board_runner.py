"""Local Backlot-side consumer for pending interaction intents.

The browser only writes intents. This runner applies panel decisions and
end-and-export requests, then records board-visible progress. It does not
call paid generate APIs and does not silently switch providers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import lib.approval_bundle as approval_bundle
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
                "phase": PHASE_NEEDS_CHAT,
                "runner_alive": runner_alive,
                "friendly_zh": getattr(exc, "safe_message", None)
                or "本机无法自动确认这笔选择，请回聊天发送：确认面板选择",
                "current_question": "请回聊天发送：确认面板选择",
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
    elif actions:
        status = {
            "phase": PHASE_PRODUCING,
            "runner_alive": runner_alive,
            "friendly_zh": "面板选择已生效。本机不会静默付费生视频；缺画面时请在聊天说「继续出片」。",
            "current_question": "若还没有成片，请回聊天继续出片。",
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

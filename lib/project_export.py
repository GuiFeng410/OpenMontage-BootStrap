"""End-and-export a project: copy final.mp4 to exports/ and mark completed."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import lib.interaction_intents as intents
from lib.paths import PROJECTS_DIR

EXPORT_PHRASE = "结束导出"
FINAL_REL = Path("renders") / "final.mp4"
EXPORTS_SUBDIR = "exports"
EXPORT_FILENAME = "final.mp4"
LIFECYCLE_COMPLETED = "completed"
RUNNER_STATUS_NAME = "runner_status.json"


class ProjectExportError(intents.IntentError):
    def __init__(self, message: str, *, code: str, safe_message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = safe_message


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _project_dir(project_id: str) -> Path:
    return intents._project_dir(project_id)


def _marker_path(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"


def read_marker(project_id: str) -> dict[str, Any]:
    path = _marker_path(project_id)
    if not path.is_file():
        raise ProjectExportError(
            f"unknown project: {project_id}",
            code="unknown_project",
            safe_message="未找到该项目",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectExportError(
            f"invalid project.json: {project_id}",
            code="invalid_project_marker",
            safe_message="项目标记文件无效",
        ) from exc
    if not isinstance(data, dict):
        raise ProjectExportError(
            "project.json must be an object",
            code="invalid_project_marker",
            safe_message="项目标记文件无效",
        )
    return data


def is_completed(marker: dict[str, Any] | None) -> bool:
    if not isinstance(marker, dict):
        return False
    return str(marker.get("lifecycle_status") or "") == LIFECYCLE_COMPLETED


def write_runner_status(project_id: str, payload: dict[str, Any]) -> Path:
    project = _project_dir(project_id)
    path = project / RUNNER_STATUS_NAME
    body = {
        "version": "1.0",
        "updated_at": _now_iso(),
        **payload,
    }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_runner_status(project_dir: Path) -> dict[str, Any] | None:
    path = Path(project_dir) / RUNNER_STATUS_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_marker(project_id: str, marker: dict[str, Any]) -> None:
    path = _marker_path(project_id)
    path.write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _final_path(project_id: str) -> Path:
    return _project_dir(project_id) / FINAL_REL


def _persist_intent(project_id: str, intent: dict[str, Any]) -> None:
    path = intents._intent_path(_project_dir(project_id), intent["intent_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    intents._atomic_write_json(path, intent)


def _finish_intent(intent: dict[str, Any]) -> dict[str, Any]:
    current = intent
    if current["status"] == "pending":
        current = intents.transition(current, "planned")
    if current["status"] == "planned":
        current = intents.transition(current, "approved")
    if current["status"] == "approved":
        current = intents.transition(current, "applied")
    return current


def _fail_intent(intent: dict[str, Any]) -> dict[str, Any]:
    if intent["status"] in {"applied", "failed", "superseded", "rejected"}:
        return intent
    if intent["status"] == "approved":
        return intents.transition(intent, "failed")
    if intent["status"] == "planned":
        return intents.transition(intent, "failed")
    return intents.transition(intent, "failed")


def _make_chat_intent(project_id: str) -> dict[str, Any]:
    summary = "结束并导出项目"
    intent = {
        "version": "1.0",
        "intent_type": "project_export",
        "intent_id": f"export-{uuid4()}",
        "project_id": project_id,
        "stage": "delivery_signoff",
        "revision": "export-v1",
        "summary": summary,
        "summary_sha256": hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        "payload": {"action": "end_and_export", "source": "chat"},
        "expires_at": "2099-01-01T00:00:00+00:00",
        "created_at": _now_iso(),
        "status": "pending",
    }
    intents.validate_interaction_intent(intent)
    return intent


def _load_intent(project_id: str, intent_id: str) -> dict[str, Any]:
    path = intents._intent_path(_project_dir(project_id), intent_id)
    if not path.is_file():
        raise ProjectExportError(
            f"intent not found: {intent_id}",
            code="intent_not_found",
            safe_message="未找到结束导出请求",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectExportError(
            f"intent cannot be read: {intent_id}",
            code="intent_invalid",
            safe_message="结束导出请求无效",
        ) from exc
    intents.validate_interaction_intent(data)
    if data.get("intent_type") != "project_export":
        raise ProjectExportError(
            "intent is not project_export",
            code="intent_type_mismatch",
            safe_message="这不是结束导出请求",
        )
    return intents.expire_if_needed(data)


def _latest_pending_export(project_id: str) -> dict[str, Any] | None:
    directory = _project_dir(project_id) / intents.INTENTS_SUBDIR
    if not directory.is_dir():
        return None
    pending: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            intents.validate_interaction_intent(data)
        except (OSError, json.JSONDecodeError, intents.IntentError):
            continue
        data = intents.expire_if_needed(data)
        if data.get("intent_type") == "project_export" and data.get("status") == "pending":
            pending.append(data)
    if not pending:
        return None
    pending.sort(key=lambda item: str(item.get("created_at") or ""))
    return pending[-1]


def apply_project_export(
    project_id: str,
    *,
    intent_id: str = "",
    confirm_phrase: str = "",
) -> dict[str, Any]:
    """Copy renders/final.mp4 to exports/ and mark the project completed.

    Browser clicks only create a pending ``project_export`` intent. This
    function (MCP / runner / chat phrase) performs the copy.
    """
    phrase = (confirm_phrase or "").strip()
    if phrase and phrase != EXPORT_PHRASE:
        raise ProjectExportError(
            "confirm_phrase must exactly equal 结束导出",
            code="confirmation_required",
            safe_message="请输入结束导出",
        )

    marker = read_marker(project_id)
    if is_completed(marker):
        export_rel = str(marker.get("export_path") or f"{EXPORTS_SUBDIR}/{EXPORT_FILENAME}")
        return {
            "ok": True,
            "already_completed": True,
            "project_id": project_id,
            "export_path": export_rel,
            "friendly_zh": "这个项目已经结束并导出过了。",
        }

    intent: dict[str, Any] | None = None
    if intent_id.strip():
        intent = _load_intent(project_id, intent_id.strip())
    elif phrase == EXPORT_PHRASE:
        intent = _latest_pending_export(project_id) or _make_chat_intent(project_id)
    else:
        intent = _latest_pending_export(project_id)
    if intent is None:
        raise ProjectExportError(
            "no project_export intent and no confirm phrase",
            code="export_intent_required",
            safe_message="请先在看板点「结束并导出项目」，或在聊天发送：结束导出",
        )
    if intent.get("status") in {"applied", "superseded", "rejected"}:
        raise ProjectExportError(
            f"export intent cannot run from {intent['status']}",
            code="intent_status_invalid",
            safe_message="这条结束导出请求已经处理过了",
        )

    source = _final_path(project_id)
    if not source.is_file() or source.stat().st_size <= 0:
        failed = _fail_intent(intent)
        failed["note"] = "还没有成片，不能结束导出。"
        _persist_intent(project_id, failed)
        write_runner_status(
            project_id,
            {
                "phase": "paused",
                "friendly_zh": "还没有成片，不能结束导出。出片后再点「结束并导出项目」。",
                "current_question": "成片好了再结束导出，或回聊天继续出片。",
            },
        )
        return {
            "ok": False,
            "code": "missing_final",
            "project_id": project_id,
            "intent_id": failed["intent_id"],
            "friendly_zh": "还没有成片，不能结束导出。画面签收或补字幕都不算结束。",
        }

    dest_dir = _project_dir(project_id) / EXPORTS_SUBDIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / EXPORT_FILENAME
    shutil.copy2(source, dest)
    export_rel = f"{EXPORTS_SUBDIR}/{EXPORT_FILENAME}"
    marker["lifecycle_status"] = LIFECYCLE_COMPLETED
    marker["exported_at"] = _now_iso()
    marker["export_path"] = export_rel
    _write_marker(project_id, marker)

    try:
        from lib.library_create import remember_machine_seen
        from lib.paths import REPO_ROOT

        remember_machine_seen(repo_root=REPO_ROOT, latest_project_id=project_id)
    except Exception:
        pass

    applied = _finish_intent(intent)
    _persist_intent(project_id, applied)
    write_runner_status(
        project_id,
        {
            "phase": "exported",
            "friendly_zh": f"已结束并导出到 {export_rel}。请回库页查看。这个项目不会再自动续做。",
            "export_path": export_rel,
            "library_path": "/",
            "stop_runner": True,
        },
    )
    try:
        from backlot.runner import stop_runner

        stop_runner()
    except Exception:
        pass
    return {
        "ok": True,
        "already_completed": False,
        "project_id": project_id,
        "intent_id": applied["intent_id"],
        "export_path": export_rel,
        "source_path": str(FINAL_REL).replace("\\", "/"),
        "library_path": "/",
        "friendly_zh": f"已拷贝成片到 {export_rel}，项目已结束。请回库页。",
    }

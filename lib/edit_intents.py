"""Edit intents — user light-weight editing marks on a rendered version.

An edit intent is a small, append-only request record written by the Backlot
board (via ``POST /intents``) or by the Agent. It lives under
``projects/<project_id>/intents/<intent_id>.json`` — an *intent layer* that is
deliberately separate from checkpoint / artifact "truth" (see
``Agent-ReadMe/回复/05-Backlot边界-L0L1L2.md``: L1-B 「禁止写真相，允许写 intent」).

Only the Agent may consume an intent and, after chat confirmation, apply it
to ``edit_decisions`` (cuts only — see ``Plan/04-Omniclip融入剪辑POC方案.md``).

Status flow::

    pending → planned → confirmed → applied
                  └→ rejected / superseded   (never applied)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from lib.paths import PROJECTS_DIR
from schemas.artifacts import validate_artifact

INTENTS_SUBDIR = "intents"

VALID_STATUSES = ("pending", "planned", "confirmed", "applied", "rejected", "superseded")

# Allowed transitions per current status.
_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"planned", "rejected", "superseded", "applied"}),
    "planned": frozenset({"confirmed", "rejected", "superseded"}),
    "confirmed": frozenset({"applied"}),
    "applied": frozenset(),
    "rejected": frozenset(),
    "superseded": frozenset(),
}

# Characters that would let a project_id / intent_id escape the projects root
# on Windows (drive letters / separators) or resolve to a parent path.
_FORBIDDEN_IN_ID = frozenset("/\\:")


class IntentError(Exception):
    """Raised for validation or state-transition violations."""


class UnknownProjectError(IntentError):
    """Raised when the referenced project directory does not exist."""


class IntentConflictError(IntentError):
    """Raised when an intent id already exists with different content."""


def _check_id(what: str, value: str) -> None:
    if not value or value in (".", "..") or _FORBIDDEN_IN_ID.intersection(value):
        raise IntentError(f"invalid {what}: {value!r}")


def intents_dir(project_id: str) -> Path:
    _check_id("project id", project_id)
    return PROJECTS_DIR / project_id / INTENTS_SUBDIR


def intent_path(project_id: str, intent_id: str) -> Path:
    _check_id("project id", project_id)
    _check_id("intent id", intent_id)
    return intents_dir(project_id) / f"{intent_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_semantics(data: dict[str, Any]) -> None:
    actions = data.get("actions") or []
    note = data.get("note") or ""
    if not actions and not str(note).strip():
        raise IntentError("intent must contain at least one action or a note")
    for action in actions:
        if action.get("type") == "trim":
            if action["in_seconds"] >= action["out_seconds"]:
                raise IntentError(
                    "trim in_seconds must be < out_seconds "
                    f"({action['in_seconds']} >= {action['out_seconds']})"
                )
        elif action.get("type") == "reorder":
            order = action["order"]
            if len(set(order)) != len(order):
                raise IntentError("reorder order must contain unique cut ids")


def validate_intent(data: dict[str, Any]) -> None:
    """Validate intent structure + semantic rules. Raises ``IntentError``."""
    try:
        validate_artifact("edit_intents", data)
    except Exception as exc:  # jsonschema.ValidationError et al.
        raise IntentError(f"intent schema validation failed: {exc}") from exc
    _check_semantics(data)


def create_intent(project_id: str, data: dict[str, Any]) -> dict:
    """Write a new pending intent. Idempotent on identical ``intent_id``.

    Returns the stored record with a ``duplicate`` flag (True when the id
    already existed with identical content; content collision raises).
    """
    _check_id("project id", project_id)
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.is_dir():
        raise UnknownProjectError(f"unknown project: {project_id}")

    data = dict(data)
    data.setdefault("created_at", _now_iso())
    data.setdefault("status", "pending")
    if data.get("project_id") != project_id:
        raise IntentError("project_id mismatch between path and body")
    validate_intent(data)

    target = intent_path(project_id, data["intent_id"])
    if target.is_file():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing == data:
            return {**existing, "duplicate": True}
        raise IntentConflictError(f"intent already exists with different content: {data['intent_id']}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**data, "duplicate": False}


def get_intent(project_id: str, intent_id: str) -> Optional[dict]:
    """Return the intent record, or None when it does not exist."""
    path = intent_path(project_id, intent_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_intents(project_id: str) -> list[dict]:
    """List all intents for a project, oldest first."""
    d = intents_dir(project_id)
    if not d.is_dir():
        return []
    items: list[dict] = []
    for p in sorted(d.glob("*.json")):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    items.sort(key=lambda i: (i.get("created_at", ""), i.get("intent_id", "")))
    return items


def update_status(project_id: str, intent_id: str, new_status: str) -> dict:
    """Transition an intent's status. Returns the updated record."""
    if new_status not in VALID_STATUSES:
        raise IntentError(f"unknown status: {new_status}")
    intent = get_intent(project_id, intent_id)
    if intent is None:
        raise IntentError(f"intent not found: {intent_id}")
    current = intent.get("status", "pending")
    if new_status not in _TRANSITIONS.get(current, frozenset()):
        raise IntentError(f"illegal transition: {current} -> {new_status}")
    intent["status"] = new_status
    intent["updated_at"] = _now_iso()
    path = intent_path(project_id, intent_id)
    path.write_text(json.dumps(intent, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return intent

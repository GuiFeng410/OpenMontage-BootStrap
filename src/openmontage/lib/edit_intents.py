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

from lib.persistence.json_store import JsonStore

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


class CodedIntentError(IntentError):
    """Intent failure with a stable, safe external error code."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


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


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    JsonStore.write_atomic(path, data)


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


def source_render_matches(project_dir: Path, raw: Any, current: str) -> bool:
    """Return whether a project-relative source points at the canonical render."""
    if not isinstance(raw, str) or not raw.strip():
        return False
    candidate = Path(raw.strip().replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    if candidate.parts and candidate.parts[0] == "projects":
        if len(candidate.parts) < 3 or candidate.parts[1] != project_dir.name:
            return False
        candidate = Path(*candidate.parts[2:])
    try:
        expected = (project_dir / candidate).resolve()
        expected.relative_to(project_dir.resolve())
        actual = (project_dir / current).resolve()
    except (OSError, ValueError):
        return False
    return expected == actual


def _validate_new_source_render(
    project_dir: Path,
    data: dict[str, Any],
    canonical_source_render: Optional[str],
) -> None:
    source_render = (data.get("base") or {}).get("source_render")
    if not isinstance(source_render, str) or not source_render.strip():
        raise CodedIntentError(
            "missing_source_render",
            code="missing_source_render",
        )
    if canonical_source_render is None:
        from backlot.state import load_board_state

        gate = load_board_state(project_dir).get("editing_gate") or {}
        canonical_source_render = (gate.get("latest_render") or {}).get("path")
    if (
        not isinstance(canonical_source_render, str)
        or not canonical_source_render.strip()
        or not source_render_matches(
            project_dir,
            source_render,
            canonical_source_render,
        )
    ):
        raise CodedIntentError(
            "source_render_mismatch",
            code="source_render_mismatch",
        )


def create_intent(
    project_id: str,
    data: dict[str, Any],
    *,
    canonical_source_render: Optional[str] = None,
) -> dict:
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
    _validate_new_source_render(project_dir, data, canonical_source_render)

    target = intent_path(project_id, data["intent_id"])
    if target.is_file():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing == data:
            return {**existing, "duplicate": True}
        raise IntentConflictError(f"intent already exists with different content: {data['intent_id']}")

    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(target, data)
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


def transition_status(intent: dict[str, Any], new_status: str) -> dict[str, Any]:
    """Build a validated status transition without writing it."""
    if new_status not in VALID_STATUSES:
        raise IntentError(f"unknown status: {new_status}")
    current = intent.get("status", "pending")
    if new_status not in _TRANSITIONS.get(current, frozenset()):
        raise IntentError(f"illegal transition: {current} -> {new_status}")
    updated = dict(intent)
    updated["status"] = new_status
    updated["updated_at"] = _now_iso()
    return updated


def update_status(project_id: str, intent_id: str, new_status: str) -> dict:
    """Transition an intent's status. Returns the updated record."""
    intent = get_intent(project_id, intent_id)
    if intent is None:
        raise IntentError(f"intent not found: {intent_id}")
    intent = transition_status(intent, new_status)
    path = intent_path(project_id, intent_id)
    _atomic_write_json(path, intent)
    return intent

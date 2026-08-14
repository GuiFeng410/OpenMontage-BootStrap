"""Versioned interaction intents and their pure status transitions.

Interaction intents are side-channel user requests. Persistence is deliberately
limited to ``PROJECTS_DIR/<project_id>/intents``; canonical production artifacts
remain owned by the Agent/checkpoint flow.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from lib.paths import PROJECTS_DIR
from schemas.artifacts import validate_artifact

INTENTS_SUBDIR = "intents"

INTERACTION_INTENT_TYPES = frozenset(
    {
        "preference",
        "decision",
        "asset_review",
        "revision_request",
        "approval_bundle",
    }
)

TRANSITIONS: dict[str, set[str]] = {
    "pending": {"planned", "superseded", "rejected", "failed"},
    "planned": {"approved", "superseded", "rejected", "failed"},
    "approved": {"applied", "superseded", "rejected", "failed"},
    "applied": set(),
    "superseded": set(),
    "rejected": set(),
    "failed": set(),
}

_ACTIVE_STATUSES = frozenset({"pending", "planned", "approved"})
_FORBIDDEN_IN_ID = frozenset("/\\:")
_BROWSER_ONLY_FIELDS = frozenset({"risk_level"})


class IntentError(Exception):
    """Raised for interaction-intent validation or transition violations."""


class UnknownProjectError(IntentError):
    """Raised when the project marker does not exist."""


class IntentConflictError(IntentError):
    """Raised when an intent id already stores different normalized content."""


def _check_id(label: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or _FORBIDDEN_IN_ID.intersection(value)
    ):
        raise IntentError(f"invalid {label}: {value!r}")
    return value


def _clean_browser_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key not in _BROWSER_ONLY_FIELDS}


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise IntentError(f"{field} must be an ISO-8601 date-time")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise IntentError(f"{field} must be an ISO-8601 date-time") from exc
    if parsed.tzinfo is None:
        raise IntentError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _coerce_now(now: datetime | str | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, str):
        return _parse_datetime(now, "now")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise IntentError("now must be a timezone-aware datetime or ISO-8601 string")
    return now.astimezone(timezone.utc)


def validate_interaction_intent(data: dict[str, Any]) -> None:
    """Validate schema and semantic invariants.

    Approval-bundle intents are validated against their stricter specialized
    schema so incomplete authorization payloads fail closed.
    """

    if not isinstance(data, dict):
        raise IntentError("interaction intent must be an object")

    schema_name = (
        "approval_bundle"
        if data.get("intent_type") == "approval_bundle"
        else "interaction_intent"
    )
    try:
        validate_artifact(schema_name, data)
    except Exception as exc:
        raise IntentError(f"interaction intent schema validation failed: {exc}") from exc

    if data["intent_type"] not in INTERACTION_INTENT_TYPES:
        raise IntentError(f"unknown intent_type: {data['intent_type']}")

    expected_hash = hashlib.sha256(data["summary"].encode("utf-8")).hexdigest()
    if data["summary_sha256"] != expected_hash:
        raise IntentError("summary_sha256 does not match UTF-8 summary")

    _parse_datetime(data["created_at"], "created_at")
    _parse_datetime(data["expires_at"], "expires_at")


def normalize_for_idempotency(data: dict[str, Any]) -> str:
    """Return canonical JSON used to compare two create requests."""

    if not isinstance(data, dict):
        raise IntentError("interaction intent must be an object")
    cleaned = _clean_browser_fields(data)
    return json.dumps(
        cleaned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def expire_if_needed(
    data: dict[str, Any],
    *,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    """Return a copy, superseding an active intent at or after its expiry."""

    validate_interaction_intent(data)
    updated = dict(data)
    if (
        updated["status"] in _ACTIVE_STATUSES
        and _coerce_now(now) >= _parse_datetime(updated["expires_at"], "expires_at")
    ):
        updated["status"] = "superseded"
    return updated


def transition(
    data: dict[str, Any],
    new_status: str,
    *,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    """Return a validated copy advanced through one legal status edge."""

    if new_status not in TRANSITIONS:
        raise IntentError(f"unknown status: {new_status}")

    current = expire_if_needed(data, now=now)
    old_status = current["status"]
    if new_status not in TRANSITIONS[old_status]:
        raise IntentError(f"illegal transition: {old_status} -> {new_status}")

    current["status"] = new_status
    validate_interaction_intent(current)
    return current


def _project_dir(project_id: str) -> Path:
    project_id = _check_id("project id", project_id)
    root = PROJECTS_DIR.resolve()
    candidate = (root / project_id).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise IntentError(f"invalid project id: {project_id!r}") from exc
    if not (candidate / "project.json").is_file():
        raise UnknownProjectError(f"unknown project: {project_id}")
    return candidate


def _intent_path(project_dir: Path, intent_id: str) -> Path:
    intent_id = _check_id("intent id", intent_id)
    return project_dir / INTENTS_SUBDIR / f"{intent_id}.json"


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def create_or_conflict(project_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Persist a new intent or report an identical request as a duplicate."""

    project_dir = _project_dir(project_id)
    cleaned = _clean_browser_fields(dict(data))
    if cleaned.get("project_id") != project_id:
        raise IntentError("project_id mismatch between path and body")

    validate_interaction_intent(cleaned)
    target = _intent_path(project_dir, cleaned["intent_id"])
    normalized = normalize_for_idempotency(cleaned)

    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntentConflictError(
                f"existing intent cannot be compared safely: {cleaned['intent_id']}"
            ) from exc
        if normalize_for_idempotency(existing) == normalized:
            return {"duplicate": True, "intent": existing}
        raise IntentConflictError(
            f"intent already exists with different content: {cleaned['intent_id']}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(target, cleaned)
    return {"duplicate": False, "intent": cleaned}


SAFE_LIST_FIELDS = (
    "intent_id",
    "intent_type",
    "stage",
    "status",
    "summary",
    "expires_at",
    "revision",
)


def list_safe_interaction_intents(project_dir: Path) -> list[dict[str, Any]]:
    """Read interaction intents for display. Never writes. Skips edit/corrupt files."""

    intents_dir = Path(project_dir) / INTENTS_SUBDIR
    if not intents_dir.is_dir():
        return []

    intents: list[dict[str, Any]] = []
    for path in intents_dir.glob("*.json"):
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(stored, dict)
                or stored.get("intent_type") not in INTERACTION_INTENT_TYPES
            ):
                continue
            current = expire_if_needed(stored)
        except (OSError, json.JSONDecodeError, IntentError):
            continue
        intents.append({field: current[field] for field in SAFE_LIST_FIELDS})
    intents.sort(key=lambda item: (item["intent_id"], item["revision"]))
    return intents

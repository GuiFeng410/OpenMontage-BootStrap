"""Tests for the FastAPI-free interaction-intent state machine."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

import lib.interaction_intents as ii


def _valid_intent(**overrides):
    summary = overrides.pop("summary", "采用轻度档并等待素材评审")
    data = {
        "version": "1.0",
        "intent_type": "decision",
        "intent_id": "intent-001",
        "project_id": "demo-pro",
        "stage": "brief_locked",
        "revision": "revision-001",
        "summary": summary,
        "summary_sha256": hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        "payload": {"production_tier": "light", "review_mode": "guided"},
        "expires_at": "2099-08-14T12:00:00+00:00",
        "created_at": "2026-08-14T01:00:00+00:00",
        "status": "pending",
    }
    data.update(overrides)
    return data


@pytest.fixture
def projects(monkeypatch, tmp_path):
    root = tmp_path / "user-projects"
    project = root / "demo-pro"
    project.mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps({"version": "1.0", "project_id": "demo-pro"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(ii, "PROJECTS_DIR", root)
    return root


def test_validate_accepts_valid_intent():
    ii.validate_interaction_intent(_valid_intent())


def test_validate_rejects_summary_hash_mismatch():
    with pytest.raises(ii.IntentError, match="summary_sha256"):
        ii.validate_interaction_intent(_valid_intent(summary_sha256="0" * 64))


def test_transition_follows_approved_state_flow():
    intent = _valid_intent()
    intent = ii.transition(intent, "planned")
    intent = ii.transition(intent, "approved")
    intent = ii.transition(intent, "applied")
    assert intent["status"] == "applied"


def test_transition_rejects_pending_directly_to_applied():
    with pytest.raises(ii.IntentError, match="pending -> applied"):
        ii.transition(_valid_intent(), "applied")


def test_expire_if_needed_supersedes_active_intent_without_mutating_input():
    intent = _valid_intent(expires_at="2026-08-14T02:00:00+00:00")
    expired = ii.expire_if_needed(
        intent,
        now=datetime(2026, 8, 14, 2, 0, 1, tzinfo=timezone.utc),
    )
    assert expired["status"] == "superseded"
    assert intent["status"] == "pending"


def test_expire_if_needed_leaves_unexpired_intent_pending():
    intent = _valid_intent(expires_at="2026-08-14T02:00:00+00:00")
    current = ii.expire_if_needed(
        intent,
        now=datetime(2026, 8, 14, 1, 59, 59, tzinfo=timezone.utc),
    )
    assert current["status"] == "pending"


def test_normalize_is_order_independent_and_strips_browser_risk_level():
    first = _valid_intent(payload={"review_mode": "guided", "production_tier": "light"})
    second = _valid_intent(payload={"production_tier": "light", "review_mode": "guided"})
    second["risk_level"] = "safe"
    assert ii.normalize_for_idempotency(first) == ii.normalize_for_idempotency(second)


def test_create_or_conflict_is_idempotent_and_persists_only_under_intents(projects):
    first = _valid_intent(risk_level="browser-declared-low")
    created = ii.create_or_conflict("demo-pro", first)
    duplicate = ii.create_or_conflict(
        "demo-pro",
        _valid_intent(payload={"review_mode": "guided", "production_tier": "light"}),
    )

    target = projects / "demo-pro" / "intents" / "intent-001.json"
    assert created == {"duplicate": False, "intent": json.loads(target.read_text(encoding="utf-8"))}
    assert duplicate["duplicate"] is True
    assert "risk_level" not in duplicate["intent"]
    assert list((projects / "demo-pro").glob("**/*.json")) == [
        projects / "demo-pro" / "project.json",
        target,
    ]


def test_create_or_conflict_rejects_different_content(projects):
    ii.create_or_conflict("demo-pro", _valid_intent())
    with pytest.raises(ii.IntentConflictError):
        ii.create_or_conflict(
            "demo-pro",
            _valid_intent(payload={"production_tier": "heavy"}),
        )


def test_create_or_conflict_requires_project_marker(projects):
    (projects / "folder-only").mkdir()
    with pytest.raises(ii.UnknownProjectError):
        ii.create_or_conflict(
            "folder-only",
            _valid_intent(project_id="folder-only"),
        )


def test_create_or_conflict_rejects_project_mismatch(projects):
    with pytest.raises(ii.IntentError, match="project_id mismatch"):
        ii.create_or_conflict(
            "demo-pro",
            _valid_intent(project_id="other-pro"),
        )


@pytest.mark.parametrize("bad_id", ["..", "a/b", "a\\b", "C:"])
def test_create_or_conflict_rejects_path_escape(projects, bad_id):
    with pytest.raises(ii.IntentError):
        ii.create_or_conflict(bad_id, _valid_intent(project_id=bad_id))

"""Contract tests for B2 interaction-intent artifacts."""

from __future__ import annotations

import hashlib

import pytest
from jsonschema import ValidationError

from schemas.artifacts import ARTIFACT_NAMES, load_schema, validate_artifact


def _summary_hash(summary: str) -> str:
    return hashlib.sha256(summary.encode("utf-8")).hexdigest()


def _interaction_intent(**overrides):
    summary = overrides.pop("summary", "采用轻度档并等待素材评审")
    data = {
        "version": "1.0",
        "intent_type": "decision",
        "intent_id": "intent-001",
        "project_id": "demo-pro",
        "stage": "brief_locked",
        "revision": "revision-001",
        "summary": summary,
        "summary_sha256": _summary_hash(summary),
        "payload": {"production_tier": "light"},
        "expires_at": "2026-08-15T01:00:00+00:00",
        "created_at": "2026-08-14T01:00:00+00:00",
        "status": "pending",
    }
    data.update(overrides)
    return data


def _approval_payload():
    return {
        "theme": "翡翠手镯",
        "duration_seconds": 15,
        "production_tier": "light",
        "review_mode": "guided",
        "provider": "local",
        "model": "deterministic",
        "runtime": "remotion",
        "asset_strategy": "reuse-approved",
        "allow_deterministic_reuse": True,
        "max_generations": 2,
        "unit_price_cny": 0,
        "total_budget_cny": 0,
        "resolution": "1080x1920",
        "quality_target": "draft",
        "auto_retry_count": 1,
        "auto_stages": ["brief_locked", "sample_review"],
        "pause_conditions": ["generated_image_review", "budget_exceeded"],
        "expires_at": "2026-08-15T01:00:00+00:00",
        "revoke_method": "聊天发送撤销快速模式",
    }


def _fast_track_policy():
    return {
        "version": "1.0",
        "provider": "local",
        "model": "deterministic",
        "runtime": "remotion",
        "call_cap": 2,
        "cost_cap_cny": 0,
        "unit_price_cny": 0,
        "resolution": "1080x1920",
        "quality_target": "draft",
        "auto_retry_count": 1,
        "auto_stages": ["brief_locked", "sample_review"],
        "expires_at": "2026-08-15T01:00:00+00:00",
        "revoke_method": "聊天发送撤销快速模式",
    }


def test_interaction_intent_fixture_validates():
    validate_artifact("interaction_intent", _interaction_intent())


@pytest.mark.parametrize("field", ["revision", "expires_at", "summary_sha256"])
def test_interaction_intent_rejects_missing_required_field(field):
    intent = _interaction_intent()
    del intent[field]
    with pytest.raises(ValidationError):
        validate_artifact("interaction_intent", intent)


def test_interaction_intent_rejects_unknown_type():
    with pytest.raises(ValidationError):
        validate_artifact(
            "interaction_intent",
            _interaction_intent(intent_type="browser_magic"),
        )


def test_project_export_intent_validates():
    validate_artifact(
        "interaction_intent",
        _interaction_intent(
            intent_type="project_export",
            payload={"action": "end_and_export"},
        ),
    )


def test_interaction_intent_rejects_browser_risk_level():
    with pytest.raises(ValidationError):
        validate_artifact(
            "interaction_intent",
            _interaction_intent(risk_level="safe"),
        )


def test_b2_schemas_are_registered():
    assert {
        "interaction_intent",
        "approval_bundle",
        "fast_track_policy",
    }.issubset(ARTIFACT_NAMES)


def test_approval_bundle_fixture_validates():
    validate_artifact(
        "approval_bundle",
        _interaction_intent(
            intent_type="approval_bundle",
            payload=_approval_payload(),
        ),
    )


@pytest.mark.parametrize("field", list(_approval_payload()))
def test_approval_bundle_rejects_every_missing_payload_field(field):
    payload = _approval_payload()
    del payload[field]
    with pytest.raises(ValidationError):
        validate_artifact(
            "approval_bundle",
            _interaction_intent(
                intent_type="approval_bundle",
                payload=payload,
            ),
        )


def test_fast_track_policy_fixture_validates():
    validate_artifact("fast_track_policy", _fast_track_policy())


@pytest.mark.parametrize(
    ("schema_name", "fixture"),
    [
        ("interaction_intent", _interaction_intent),
        (
            "approval_bundle",
            lambda: _interaction_intent(
                intent_type="approval_bundle",
                payload=_approval_payload(),
            ),
        ),
        ("fast_track_policy", _fast_track_policy),
    ],
)
def test_b2_schema_version_is_const_1_0(schema_name, fixture):
    artifact = fixture()
    artifact["version"] = "2.0"
    with pytest.raises(ValidationError):
        validate_artifact(schema_name, artifact)


def test_fast_track_policy_rejects_unknown_fields():
    policy = _fast_track_policy()
    policy["risk_level"] = "safe"
    with pytest.raises(ValidationError):
        validate_artifact("fast_track_policy", policy)


def test_edit_intents_status_contract_is_unchanged():
    statuses = load_schema("edit_intents")["properties"]["status"]["enum"]
    assert statuses == [
        "pending",
        "planned",
        "confirmed",
        "applied",
        "rejected",
        "superseded",
    ]

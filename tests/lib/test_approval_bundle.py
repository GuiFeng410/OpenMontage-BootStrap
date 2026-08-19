"""Unit tests for FastAPI-free approval-bundle helpers."""

from __future__ import annotations

import hashlib
import json

import pytest

import lib.approval_bundle as approval_bundle
import lib.interaction_intents as interaction_intents


@pytest.fixture
def approval_project(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = root / "demo-pro"
    project.mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": "demo-pro",
                "title": "Approval bundle",
                "pipeline_type": "bootstrap-commercial",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(interaction_intents, "PROJECTS_DIR", root)
    monkeypatch.setattr(approval_bundle, "PROJECTS_DIR", root)
    return project


def _payload() -> dict:
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
        "expires_at": "2099-08-15T01:00:00+00:00",
        "revoke_method": "聊天发送撤销快速模式",
    }


def _intent(**overrides) -> dict:
    summary = overrides.pop("summary", "确认轻度档审批包")
    data = {
        "version": "1.0",
        "intent_type": "approval_bundle",
        "intent_id": "approval-001",
        "project_id": "demo-pro",
        "stage": "brief_locked",
        "revision": "revision-001",
        "summary": summary,
        "summary_sha256": hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        "payload": _payload(),
        "expires_at": "2099-08-15T01:00:00+00:00",
        "created_at": "2026-08-14T01:00:00+00:00",
        "status": "pending",
    }
    data.update(overrides)
    return data


def _write_intent(project, intent: dict) -> None:
    intents_dir = project / "intents"
    intents_dir.mkdir(exist_ok=True)
    (intents_dir / f"{intent['intent_id']}.json").write_text(
        json.dumps(intent, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _stored(project, intent_id: str = "approval-001") -> dict:
    return json.loads(
        (project / "intents" / f"{intent_id}.json").read_text(encoding="utf-8")
    )


def test_list_excludes_edit_intents_and_corrupt_json(approval_project) -> None:
    _write_intent(approval_project, _intent())
    _write_intent(
        approval_project,
        {
            "intent_id": "edit-001",
            "project_id": "demo-pro",
            "status": "pending",
            "actions": [{"type": "delete", "cut_id": "c01"}],
        },
    )
    (approval_project / "intents" / "corrupt.json").write_text(
        "{not-json",
        encoding="utf-8",
    )

    listed = approval_bundle.list_interaction_intents("demo-pro")

    assert [item["intent_id"] for item in listed] == ["approval-001"]


def test_list_does_not_hide_expiry_persistence_failure(
    approval_project, monkeypatch
) -> None:
    _write_intent(
        approval_project,
        _intent(expires_at="2020-08-15T01:00:00+00:00"),
    )

    def fail_persist(_path, _data) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(approval_bundle, "_persist", fail_persist)

    with pytest.raises(OSError, match="disk unavailable"):
        approval_bundle.list_interaction_intents("demo-pro")


def test_plan_transitions_pending_to_planned(approval_project) -> None:
    _write_intent(approval_project, _intent())

    result = approval_bundle.plan_approval_bundle(
        "demo-pro",
        "approval-001",
        checkpoint_revision="revision-001",
    )

    assert result["intent"]["status"] == "planned"
    assert result["summary_zh"].count("\n") == 0
    assert _stored(approval_project)["status"] == "planned"


def test_plan_drift_persists_superseded_not_planned(approval_project) -> None:
    _write_intent(approval_project, _intent())

    with pytest.raises(interaction_intents.IntentError, match="revision"):
        approval_bundle.plan_approval_bundle(
            "demo-pro",
            "approval-001",
            checkpoint_revision="revision-old",
        )

    assert _stored(approval_project)["status"] == "superseded"


def test_apply_without_exact_phrase_does_not_write(approval_project) -> None:
    _write_intent(approval_project, _intent(status="planned"))
    path = approval_project / "intents" / "approval-001.json"
    before = path.read_bytes()
    called = []

    with pytest.raises(interaction_intents.IntentError, match="确认面板选择"):
        approval_bundle.apply_approval_bundle(
            "demo-pro",
            "approval-001",
            confirm_phrase="确认面板",
            checkpoint_revision="revision-001",
            append_decision=lambda *args: called.append(args),
        )

    assert path.read_bytes() == before
    assert called == []


def test_apply_success_appends_once_and_persists_applied(approval_project) -> None:
    _write_intent(approval_project, _intent(status="planned"))
    calls = []

    result = approval_bundle.apply_approval_bundle(
        "demo-pro",
        "approval-001",
        confirm_phrase="确认面板选择",
        checkpoint_revision="revision-001",
        append_decision=lambda project_id, decision_json: calls.append(
            (project_id, json.loads(decision_json))
        ),
    )

    assert result["intent"]["status"] == "applied"
    assert _stored(approval_project)["status"] == "applied"
    assert len(calls) == 1
    assert calls[0][0] == "demo-pro"
    assert calls[0][1]["user_response_text"] == "确认面板选择"


def test_append_decision_failure_rolls_back_intent_bytes(approval_project) -> None:
    _write_intent(approval_project, _intent(status="planned"))
    path = approval_project / "intents" / "approval-001.json"
    before = path.read_bytes()

    def fail_append(_project_id: str, _decision_json: str) -> None:
        raise RuntimeError("decision store unavailable")

    with pytest.raises(RuntimeError, match="decision store unavailable"):
        approval_bundle.apply_approval_bundle(
            "demo-pro",
            "approval-001",
            confirm_phrase="确认面板选择",
            checkpoint_revision="revision-001",
            append_decision=fail_append,
        )

    assert path.read_bytes() == before
    assert _stored(approval_project)["status"] == "planned"


def test_pending_cannot_apply_without_plan(approval_project) -> None:
    _write_intent(approval_project, _intent())

    with pytest.raises(interaction_intents.IntentError, match="plan"):
        approval_bundle.apply_approval_bundle(
            "demo-pro",
            "approval-001",
            confirm_phrase="确认面板选择",
            checkpoint_revision="revision-001",
            append_decision=lambda *_args: None,
        )

    assert _stored(approval_project)["status"] == "pending"


def _decision_intent(**overrides) -> dict:
    summary = overrides.pop("summary", "面板选择轻度档")
    data = {
        "version": "1.0",
        "intent_type": "decision",
        "intent_id": "decision-001",
        "project_id": "demo-pro",
        "stage": "brief_locked",
        "revision": "revision-001",
        "summary": summary,
        "summary_sha256": hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        "payload": {
            "selections": [
                {
                    "decision_key": "brief_locked::current",
                    "option_id": "light",
                    "label_zh": "轻度",
                }
            ],
            "note": "用现有素材",
        },
        "expires_at": "2099-08-15T01:00:00+00:00",
        "created_at": "2026-08-14T01:00:00+00:00",
        "status": "pending",
    }
    data.update(overrides)
    return data


def _write_profile(project, profile: dict) -> None:
    marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
    marker["production_profile"] = profile
    (project / "project.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_plan_promotes_pending_decision_to_approval_bundle(approval_project) -> None:
    _write_profile(
        approval_project,
        {
            "production_tier": "light",
            "duration_seconds": 15,
            "review_mode": "guided",
            "budget_cny": 0,
            "visual_source": "template",
        },
    )
    _write_intent(approval_project, _decision_intent())

    result = approval_bundle.plan_approval_bundle(
        "demo-pro",
        "decision-001",
        checkpoint_revision="revision-001",
    )

    intent = result["intent"]
    stored = _stored(approval_project, "decision-001")
    assert intent["intent_id"] == "decision-001"
    assert intent["intent_type"] == "approval_bundle"
    assert intent["status"] == "planned"
    assert stored["intent_type"] == "approval_bundle"
    assert stored["status"] == "planned"
    assert stored["payload"]["theme"] == "Approval bundle"
    assert stored["payload"]["duration_seconds"] == 15
    assert stored["payload"]["production_tier"] == "light"
    assert stored["payload"]["provider"] == "local"
    assert stored["payload"]["model"] == "deterministic"
    assert stored["payload"]["runtime"] == "remotion"
    assert stored["note"] == "用现有素材"


def test_plan_heavy_board_decision_uses_commercial_runtime_default(
    approval_project,
) -> None:
    _write_profile(
        approval_project,
        {
            "production_tier": "heavy",
            "duration_seconds": 5,
            "review_mode": "normal",
            "budget_cny": 1,
            "video_channel": "agnes",
            "video_model": "agnes-video-v2.0",
        },
    )
    _write_intent(
        approval_project,
        _decision_intent(
            payload={
                "selections": [
                    {
                        "decision_key": "brief_locked::current",
                        "option_id": "continue",
                        "label_zh": "同意，进入下一步",
                    }
                ],
                "note": "",
            }
        ),
    )

    result = approval_bundle.plan_approval_bundle(
        "demo-pro",
        "decision-001",
        checkpoint_revision="revision-001",
    )

    payload = result["intent"]["payload"]
    assert payload["production_tier"] == "heavy"
    assert payload["provider"] == "agnes"
    assert payload["model"] == "agnes-video-v2.0"
    assert payload["runtime"] == "remotion"
    assert payload["total_budget_cny"] == 1


def test_plan_decision_without_evidence_fails_closed(approval_project) -> None:
    _write_intent(approval_project, _decision_intent())

    with pytest.raises(approval_bundle.ApprovalBundleError) as excinfo:
        approval_bundle.plan_approval_bundle(
            "demo-pro",
            "decision-001",
            checkpoint_revision="revision-001",
        )

    assert excinfo.value.code == "missing_project_evidence"
    assert _stored(approval_project, "decision-001")["intent_type"] == "decision"
    assert _stored(approval_project, "decision-001")["status"] == "pending"


def test_plan_rejects_preference_type(approval_project) -> None:
    _write_intent(
        approval_project,
        _decision_intent(intent_type="preference", intent_id="pref-001"),
    )

    with pytest.raises(approval_bundle.ApprovalBundleError) as excinfo:
        approval_bundle.plan_approval_bundle(
            "demo-pro",
            "pref-001",
            checkpoint_revision="revision-001",
        )

    assert excinfo.value.code == "intent_type_mismatch"


def test_apply_writes_fast_track_v2_authorization(approval_project) -> None:
    _write_intent(approval_project, _intent(status="planned"))
    calls = []

    approval_bundle.apply_approval_bundle(
        "demo-pro",
        "approval-001",
        confirm_phrase="确认面板选择",
        checkpoint_revision="revision-001",
        append_decision=lambda project_id, decision_json: calls.append(
            json.loads(decision_json)
        ),
    )

    decision = calls[0]
    assert decision["selected"] == "fast_track_v2"
    assert decision["options_considered"][0]["option_id"] == "fast_track_v2"
    assert decision["subject"] == "Commercial fast-track production"
    assert decision["category"] == "approval_policy"


def test_apply_persists_applied_once_before_append(approval_project, monkeypatch) -> None:
    _write_intent(approval_project, _intent(status="planned"))
    order = []
    real_persist = approval_bundle._persist

    def tracking_persist(path, data) -> None:
        order.append(data["status"])
        real_persist(path, data)

    monkeypatch.setattr(approval_bundle, "_persist", tracking_persist)

    approval_bundle.apply_approval_bundle(
        "demo-pro",
        "approval-001",
        confirm_phrase="确认面板选择",
        checkpoint_revision="revision-001",
        append_decision=lambda *_args: order.append("append"),
    )

    assert "approved" not in order
    assert order == ["applied", "append"]
    assert _stored(approval_project)["status"] == "applied"


def test_persist_applied_failure_does_not_append_decision(
    approval_project, monkeypatch
) -> None:
    _write_intent(approval_project, _intent(status="planned"))
    called = []

    def fail_persist(_path, _data) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(approval_bundle, "_persist", fail_persist)

    with pytest.raises(OSError, match="disk unavailable"):
        approval_bundle.apply_approval_bundle(
            "demo-pro",
            "approval-001",
            confirm_phrase="确认面板选择",
            checkpoint_revision="revision-001",
            append_decision=lambda *args: called.append(args),
        )

    assert called == []
    assert _stored(approval_project)["status"] == "planned"

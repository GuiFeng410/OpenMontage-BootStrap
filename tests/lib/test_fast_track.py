"""Tests for the read-only fast-track v2 comparator."""

from __future__ import annotations

from copy import deepcopy

import pytest

from lib.fast_track import evaluate_fast_track


def valid_policy_fixture() -> dict:
    return {
        "version": "1.0",
        "provider": "local",
        "model": "deterministic",
        "runtime": "remotion",
        "call_cap": 2,
        "cost_cap_cny": 10.0,
        "unit_price_cny": 1.0,
        "resolution": "1080x1920",
        "quality_target": "draft",
        "auto_retry_count": 1,
        "auto_stages": ["sample_review", "delivery_signoff"],
        "expires_at": "2099-08-15T01:00:00+00:00",
        "revoke_method": "聊天发送撤销快速模式",
    }


def legal_snapshot() -> dict:
    return {
        "policy": valid_policy_fixture(),
        "now": "2026-08-14T01:00:00+00:00",
        "current_stage": "sample_review",
        "asset_matrix_closed": True,
        "generated_images_pending_review": False,
        "provider": "local",
        "model": "deterministic",
        "runtime": "remotion",
        "cost_cny_used": 1.0,
        "calls_used": 1,
        "unit_price_cny": 1.0,
        "identity_qa_pass": True,
        "structure_qa_pass": True,
        "technical_qa_pass": True,
        "new_cloud_upload_authorization": False,
        "new_cross_beat_reuse": False,
        "product_downgrade_or_hero_replace": False,
        "revision_list_nonempty": False,
        "user_paused": False,
        "user_revoked": False,
        "user_revision_submitted": False,
        "intent_expired": False,
        "revision_drift": False,
        "artifact_revision": "revision-001",
        "bundle_baseline_revision": "revision-001",
        "final_video_ready": False,
    }


def assert_pause(snapshot: dict, reason_code: str) -> None:
    result = evaluate_fast_track(snapshot)
    assert result["action"] == "pause"
    assert result["reason_code"] == reason_code
    assert isinstance(result["friendly_zh"], str) and result["friendly_zh"]
    assert isinstance(result["current_question"], str) and result["current_question"]


def test_legal_sample_review_continues() -> None:
    result = evaluate_fast_track(legal_snapshot())

    assert result == {
        "action": "continue",
        "reason_code": None,
        "friendly_zh": "当前条件满足，可继续下一阶段。",
        "current_question": None,
    }


def test_open_asset_matrix_pauses() -> None:
    snapshot = legal_snapshot()
    snapshot["asset_matrix_closed"] = False

    assert_pause(snapshot, "asset_matrix_open")


def test_non_dict_snapshot_pauses_as_missing_field() -> None:
    result = evaluate_fast_track([])  # type: ignore[arg-type]

    assert result["action"] == "pause"
    assert result["reason_code"] == "missing_field"


@pytest.mark.parametrize("field", ["policy", "now", "provider", "final_video_ready"])
def test_missing_or_none_required_field_pauses(field: str) -> None:
    missing = legal_snapshot()
    del missing[field]
    assert_pause(missing, "missing_field")

    none_value = legal_snapshot()
    none_value[field] = None
    assert_pause(none_value, "missing_field")


@pytest.mark.parametrize(
    "field",
    [
        "asset_matrix_closed",
        "generated_images_pending_review",
        "identity_qa_pass",
        "new_cloud_upload_authorization",
        "final_video_ready",
    ],
)
@pytest.mark.parametrize("invalid", [1, "true"])
def test_boolean_fields_require_real_booleans(field: str, invalid: object) -> None:
    snapshot = legal_snapshot()
    snapshot[field] = invalid

    assert_pause(snapshot, "missing_field")


@pytest.mark.parametrize("field", ["cost_cny_used", "calls_used", "unit_price_cny"])
@pytest.mark.parametrize("invalid", [True, "1"])
def test_numeric_fields_require_non_boolean_numbers(field: str, invalid: object) -> None:
    snapshot = legal_snapshot()
    snapshot[field] = invalid

    assert_pause(snapshot, "missing_field")


def test_generated_images_pause_before_budget() -> None:
    snapshot = legal_snapshot()
    snapshot["generated_images_pending_review"] = True
    snapshot["cost_cny_used"] = 99.0

    assert_pause(snapshot, "generated_image_review")


@pytest.mark.parametrize(
    ("field", "value", "reason_code"),
    [
        ("provider", "other", "provider_changed"),
        ("model", "other", "model_changed"),
        ("runtime", "hyperframes", "runtime_changed"),
        ("cost_cny_used", 10.01, "budget_exceeded"),
        ("calls_used", 3, "call_cap_exceeded"),
        ("identity_qa_pass", False, "identity_qa_failed"),
        ("structure_qa_pass", False, "structure_qa_failed"),
        ("technical_qa_pass", False, "technical_qa_failed"),
        ("new_cloud_upload_authorization", True, "pixverse_cloud_upload"),
        ("new_cross_beat_reuse", True, "new_cross_beat_reuse"),
        (
            "product_downgrade_or_hero_replace",
            True,
            "product_expression_downgrade",
        ),
        ("user_paused", True, "user_paused"),
        ("user_revoked", True, "user_revoked"),
        ("user_revision_submitted", True, "user_revision"),
        ("revision_list_nonempty", True, "user_revision"),
        ("intent_expired", True, "intent_expired"),
        ("revision_drift", True, "revision_drift"),
    ],
)
def test_pause_conditions(field: str, value: object, reason_code: str) -> None:
    snapshot = legal_snapshot()
    snapshot[field] = value

    assert_pause(snapshot, reason_code)


def test_revision_mismatch_pauses() -> None:
    snapshot = legal_snapshot()
    snapshot["artifact_revision"] = "revision-002"

    assert_pause(snapshot, "revision_drift")


def test_expired_policy_pauses() -> None:
    snapshot = legal_snapshot()
    snapshot["now"] = snapshot["policy"]["expires_at"]

    assert_pause(snapshot, "policy_expired")


def test_invalid_policy_pauses() -> None:
    snapshot = legal_snapshot()
    del snapshot["policy"]["provider"]

    assert_pause(snapshot, "policy_invalid")


def test_stage_outside_policy_pauses() -> None:
    snapshot = legal_snapshot()
    snapshot["current_stage"] = "compose"

    assert_pause(snapshot, "stage_not_authorized")


def test_zero_cost_policy_rejects_paid_unit_price() -> None:
    snapshot = legal_snapshot()
    snapshot["policy"]["cost_cap_cny"] = 0
    snapshot["cost_cny_used"] = 0

    assert_pause(snapshot, "unit_price_exceeded")


def test_next_unit_price_must_fit_remaining_budget() -> None:
    snapshot = legal_snapshot()
    snapshot["cost_cny_used"] = 9.5
    snapshot["unit_price_cny"] = 1.0

    assert_pause(snapshot, "unit_price_exceeded")


def test_locked_unit_price_rise_pauses_even_if_budget_remains() -> None:
    snapshot = legal_snapshot()
    snapshot["unit_price_cny"] = 2.0
    snapshot["cost_cny_used"] = 1.0

    assert_pause(snapshot, "unit_price_exceeded")


def test_pause_checkpoint_metadata_shape() -> None:
    from lib.fast_track import pause_checkpoint_metadata

    result = evaluate_fast_track(legal_snapshot())
    pause = pause_checkpoint_metadata(
        {
            "reason_code": "generated_image_review",
            "friendly_zh": "生成图片仍待人工审核，已暂停。",
            "current_question": "请先完成当前生成图片的审核。",
        }
    )

    assert result["action"] == "continue"
    assert pause == {
        "fast_track_pause": {
            "reason_code": "generated_image_review",
            "friendly_zh": "生成图片仍待人工审核，已暂停。",
            "current_question": "请先完成当前生成图片的审核。",
        }
    }


def test_delivery_signoff_ready() -> None:
    snapshot = legal_snapshot()
    snapshot["current_stage"] = "delivery_signoff"
    snapshot["final_video_ready"] = True

    result = evaluate_fast_track(snapshot)

    assert result["action"] == "signoff_ready"
    assert result["reason_code"] == "awaiting_signoff"
    assert isinstance(result["current_question"], str) and result["current_question"]


def test_delivery_signoff_not_ready_pauses() -> None:
    snapshot = legal_snapshot()
    snapshot["current_stage"] = "delivery_signoff"

    assert_pause(snapshot, "missing_field")


def test_evaluate_is_read_only_and_does_not_mutate_snapshot(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    snapshot = legal_snapshot()
    original = deepcopy(snapshot)

    evaluate_fast_track(snapshot)

    assert snapshot == original
    assert list(tmp_path.iterdir()) == []

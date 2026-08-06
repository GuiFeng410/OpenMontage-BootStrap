"""Tests for candidate review state transitions and deterministic fallback."""

from __future__ import annotations

from lib.candidate_review import apply_fallback, get_pending_candidates, review_candidate


def _manifest() -> dict:
    return {
        "i2i_candidates": [],
        "i2v_candidates": [
            {"path": "candidate.mp4", "scene_id": "beat_09", "status": "pending"},
        ],
        "review_log": [],
    }


def test_pending_is_visible_until_human_decision():
    manifest = _manifest()
    assert get_pending_candidates(manifest)[0]["path"] == "candidate.mp4"

    record = review_candidate(
        "candidate.mp4",
        ["anchor.png"],
        "satisfied",
        product_manifest=manifest,
        scene_id="beat_09",
    )

    assert record["decision"] == "satisfied"
    assert get_pending_candidates(manifest) == []
    assert manifest["i2v_candidates"][0]["status"] == "satisfied"
    assert manifest["review_log"][-1]["action"] == "candidate_review"


def test_rejected_candidate_uses_deterministic_fallback():
    manifest = _manifest()
    review_candidate("candidate.mp4", [], "rejected", product_manifest=manifest)
    plan = {
        "beats": [
            {"id": "beat_09", "type": "agnes_insert", "i2v_candidate": "candidate.mp4"},
            {"id": "beat_10", "type": "deterministic", "source": "Remotion deterministic static frame"},
        ]
    }

    fallback = apply_fallback(plan, manifest)

    assert fallback["beats"][0]["type"] == "deterministic"
    assert fallback["beats"][0]["fallback_applied"] is True
    assert plan["beats"][0]["type"] == "agnes_insert"

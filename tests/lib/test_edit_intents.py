"""Tests for edit intents: schema validation, persistence, status flow."""

from __future__ import annotations

import json

import pytest

import lib.edit_intents as ei


def _valid_intent(**overrides):
    data = {
        "version": "1.0",
        "intent_id": "intent-001",
        "project_id": "demo-pro",
        "created_at": "2026-08-11T14:30:00+00:00",
        "status": "pending",
        "base": {
            "artifact": "edit_decisions",
            "cuts_revision": "v2",
            "source_render": "renders/draft_v2.mp4",
        },
        "actions": [
            {"type": "trim", "cut_id": "c02", "in_seconds": 1.5, "out_seconds": 7.0, "note": "开场太慢"},
            {"type": "delete", "cut_id": "c04"},
            {"type": "reorder", "order": ["c01", "c03", "c02", "c05"]},
        ],
    }
    data.update(overrides)
    return data


@pytest.fixture
def projects(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = root / "demo-pro"
    (project / "artifacts").mkdir(parents=True)
    (project / "assets" / "video").mkdir(parents=True)
    (project / "renders").mkdir(parents=True)
    (project / "project.json").write_text(json.dumps({
        "version": "1.0",
        "project_id": "demo-pro",
        "pipeline_type": "bootstrap-commercial",
    }), encoding="utf-8")
    (project / "assets" / "video" / "cut.mp4").write_bytes(b"video")
    (project / "renders" / "draft_v2.mp4").write_bytes(b"video")
    (project / "artifacts" / "edit_decisions.json").write_text(json.dumps({
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "cuts": [{
            "id": "c01",
            "source": "assets/video/cut.mp4",
            "in_seconds": 0,
            "out_seconds": 2,
        }],
    }), encoding="utf-8")
    (project / "artifacts" / "full_draft_pro.json").write_text(json.dumps({
        "version": "1.0",
        "path": "renders/draft_v2.mp4",
        "issue_segments": [],
        "modification_list": [],
    }), encoding="utf-8")
    for index, stage in enumerate((
        "brief_locked",
        "assets_gate",
        "sample_review",
        "segment_build",
    )):
        (project / f"checkpoint_{stage}.json").write_text(json.dumps({
            "stage": stage,
            "status": "completed",
            "timestamp": f"2026-08-12T00:0{index}:00Z",
            "human_approved": True,
            "artifacts": {},
        }), encoding="utf-8")
    (project / "checkpoint_draft_review.json").write_text(json.dumps({
        "stage": "draft_review",
        "status": "in_progress",
        "timestamp": "2026-08-12T00:04:00Z",
        "artifacts": {"full_draft_pro": "artifacts/full_draft_pro.json"},
    }), encoding="utf-8")
    monkeypatch.setattr(ei, "PROJECTS_DIR", root)
    return root


# ---- schema validation -------------------------------------------------


def test_valid_intent_passes(projects):
    ei.validate_intent(_valid_intent())


def test_unknown_action_type_rejected(projects):
    data = _valid_intent(actions=[{"type": "fade", "cut_id": "c01"}])
    with pytest.raises(ei.IntentError):
        ei.validate_intent(data)


def test_missing_required_field_rejected(projects):
    data = _valid_intent()
    del data["base"]
    with pytest.raises(ei.IntentError):
        ei.validate_intent(data)


def test_bad_status_rejected(projects):
    with pytest.raises(ei.IntentError):
        ei.validate_intent(_valid_intent(status="bogus"))


def test_trim_in_gte_out_rejected(projects):
    data = _valid_intent(actions=[{"type": "trim", "cut_id": "c01", "in_seconds": 8.0, "out_seconds": 3.0}])
    with pytest.raises(ei.IntentError):
        ei.validate_intent(data)


def test_reorder_duplicate_cut_rejected(projects):
    data = _valid_intent(actions=[{"type": "reorder", "order": ["c01", "c01", "c02"]}])
    with pytest.raises(ei.IntentError):
        ei.validate_intent(data)


# ---- persistence --------------------------------------------------------


def test_create_and_get(projects):
    intent = ei.create_intent("demo-pro", _valid_intent())
    assert intent["duplicate"] is False
    assert intent["status"] == "pending"
    stored = ei.get_intent("demo-pro", "intent-001")
    assert stored is not None
    assert stored["intent_id"] == "intent-001"
    assert (projects / "demo-pro" / "intents" / "intent-001.json").is_file()


@pytest.mark.parametrize("source_render", [None, "", "   "])
def test_create_rejects_missing_source_render(projects, source_render):
    data = _valid_intent()
    if source_render is None:
        data["base"].pop("source_render")
    else:
        data["base"]["source_render"] = source_render

    with pytest.raises(ei.IntentError) as caught:
        ei.create_intent("demo-pro", data)

    assert getattr(caught.value, "code", None) == "missing_source_render"
    assert not (
        projects / "demo-pro" / "intents" / "intent-001.json"
    ).exists()


def test_create_rejects_noncanonical_source_render(projects):
    data = _valid_intent()
    data["base"]["source_render"] = "renders/other.mp4"

    with pytest.raises(ei.IntentError) as caught:
        ei.create_intent("demo-pro", data)

    assert getattr(caught.value, "code", None) == "source_render_mismatch"


def test_create_unknown_project_rejected(projects):
    with pytest.raises(ei.IntentError):
        ei.create_intent("nope", _valid_intent())


def test_create_idempotent_identical(projects):
    ei.create_intent("demo-pro", _valid_intent())
    result = ei.create_intent("demo-pro", _valid_intent())
    assert result["duplicate"] is True


def test_create_collision_different_content_rejected(projects):
    ei.create_intent("demo-pro", _valid_intent())
    with pytest.raises(ei.IntentError):
        ei.create_intent("demo-pro", _valid_intent(actions=[{"type": "delete", "cut_id": "c99"}]))


def test_project_id_mismatch_rejected(projects):
    with pytest.raises(ei.IntentError):
        ei.create_intent("demo-pro", _valid_intent(project_id="other-pro"))


def test_path_escape_rejected(projects):
    for bad in ("..", "a/b", "a\\b", "C:"):
        with pytest.raises(ei.IntentError):
            ei.intent_path(bad, "x")
        with pytest.raises(ei.IntentError):
            ei.intent_path("demo-pro", bad)


def test_list_oldest_first(projects):
    ei.create_intent("demo-pro", _valid_intent(intent_id="b", created_at="2026-08-11T10:00:00+00:00"))
    ei.create_intent("demo-pro", _valid_intent(intent_id="a", created_at="2026-08-11T09:00:00+00:00"))
    ids = [i["intent_id"] for i in ei.list_intents("demo-pro")]
    assert ids == ["a", "b"]


# ---- status flow --------------------------------------------------------


def test_status_flow_happy_path(projects):
    ei.create_intent("demo-pro", _valid_intent())
    assert ei.update_status("demo-pro", "intent-001", "planned")["status"] == "planned"
    assert ei.update_status("demo-pro", "intent-001", "confirmed")["status"] == "confirmed"
    assert ei.update_status("demo-pro", "intent-001", "applied")["status"] == "applied"


def test_illegal_transition_rejected(projects):
    ei.create_intent("demo-pro", _valid_intent())
    with pytest.raises(ei.IntentError):
        ei.update_status("demo-pro", "intent-001", "confirmed")  # pending → confirmed is illegal


def test_rejected_never_applied(projects):
    ei.create_intent("demo-pro", _valid_intent())
    ei.update_status("demo-pro", "intent-001", "rejected")
    with pytest.raises(ei.IntentError):
        ei.update_status("demo-pro", "intent-001", "applied")


def test_update_missing_intent_rejected(projects):
    with pytest.raises(ei.IntentError):
        ei.update_status("demo-pro", "ghost", "applied")


# ---- note-only intent (no actions) --------------------------------------


def test_note_only_intent_allowed(projects):
    ei.validate_intent(_valid_intent(actions=[], note="字幕换中文"))


def test_note_only_intent_writes(projects):
    intent = ei.create_intent("demo-pro", _valid_intent(actions=[], note="节奏放慢一点"))
    assert intent["duplicate"] is False
    stored = ei.get_intent("demo-pro", "intent-001")
    assert stored["note"] == "节奏放慢一点"
    assert stored["actions"] == []


def test_empty_intent_rejected(projects):
    with pytest.raises(ei.IntentError):
        ei.validate_intent(_valid_intent(actions=[]))

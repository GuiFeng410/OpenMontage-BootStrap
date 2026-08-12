"""Tests for the board's sole write exception: POST /intents."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import lib.edit_intents as ei
from backlot import server as server_mod
from backlot.server import app
from lib.edit_apply import cuts_digest


@pytest.fixture
def client(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = root / "demo-pro"
    (project / "artifacts").mkdir(parents=True)
    (project / "assets" / "video").mkdir(parents=True)
    (project / "project.json").write_text(json.dumps({
        "version": "1.0",
        "project_id": "demo-pro",
        "title": "Intent API gate",
        "pipeline_type": "bootstrap-commercial",
    }), encoding="utf-8")
    source_path = project / "assets" / "video" / "cut_01.mp4"
    source_path.write_bytes(b"video")
    draft_path = project / "renders" / "draft.mp4"
    draft_path.parent.mkdir(parents=True)
    draft_path.write_bytes(b"video")
    (project / "artifacts" / "edit_decisions.json").write_text(json.dumps({
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "cuts": [{
            "id": "c04",
            "source": "assets/video/cut_01.mp4",
            "in_seconds": 0,
            "out_seconds": 2,
        }],
    }), encoding="utf-8")
    (project / "artifacts" / "full_draft_pro.json").write_text(json.dumps({
        "version": "1.0",
        "path": "renders/draft.mp4",
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
    monkeypatch.setattr(server_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(ei, "PROJECTS_DIR", root)
    with TestClient(app) as c:
        yield c


def _intent(**overrides):
    data = {
        "version": "1.0",
        "intent_id": "intent-001",
        "project_id": "demo-pro",
        "created_at": "2026-08-11T14:30:00+00:00",
        "status": "pending",
        "base": {
            "artifact": "edit_decisions",
            "cuts_revision": "v2",
            "source_render": "renders/draft.mp4",
        },
        "actions": [{"type": "delete", "cut_id": "c04"}],
    }
    data.update(overrides)
    return data


def test_create_returns_201_and_writes(client, tmp_path):
    resp = client.post("/intents", json=_intent())
    assert resp.status_code == 201
    body = resp.json()
    assert body["intent_id"] == "intent-001"
    assert body["status"] == "pending"
    assert body["duplicate"] is False
    stored = json.loads(
        (tmp_path / "projects" / "demo-pro" / "intents" / "intent-001.json").read_text(encoding="utf-8")
    )
    assert stored["project_id"] == "demo-pro"


def test_duplicate_identical_returns_200(client):
    client.post("/intents", json=_intent())
    resp = client.post("/intents", json=_intent())
    assert resp.status_code == 200
    assert resp.json()["duplicate"] is True


def test_duplicate_conflict_returns_409(client):
    client.post("/intents", json=_intent())
    resp = client.post("/intents", json=_intent(actions=[{"type": "delete", "cut_id": "c99"}]))
    assert resp.status_code == 409


def test_unknown_project_returns_404(client):
    resp = client.post("/intents", json=_intent(project_id="nope"))
    assert resp.status_code == 404


def test_invalid_json_returns_400(client):
    resp = client.post("/intents", content="{not-json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 400


def test_non_dict_body_returns_400(client):
    resp = client.post("/intents", json=[1, 2, 3])
    assert resp.status_code == 400


def test_missing_project_id_returns_400(client):
    payload = _intent()
    del payload["project_id"]
    resp = client.post("/intents", json=payload)
    assert resp.status_code == 400


def test_empty_project_id_returns_400_before_project_lookup(client):
    resp = client.post("/intents", json=_intent(project_id=""))

    assert resp.status_code == 400
    assert resp.json()["detail"] == "missing project_id"


def test_schema_violation_returns_400(client):
    resp = client.post("/intents", json=_intent(status="bogus"))
    assert resp.status_code == 400


def test_missing_source_render_returns_400_without_writing(client, tmp_path):
    payload = _intent()
    payload["base"].pop("source_render")

    resp = client.post("/intents", json=payload)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "missing_source_render"
    assert not (
        tmp_path / "projects" / "demo-pro" / "intents" / "intent-001.json"
    ).exists()


def test_noncanonical_source_render_returns_400_without_writing(client, tmp_path):
    payload = _intent()
    payload["base"]["source_render"] = "renders/other.mp4"

    resp = client.post("/intents", json=payload)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "source_render_mismatch"
    assert not (
        tmp_path / "projects" / "demo-pro" / "intents" / "intent-001.json"
    ).exists()


def test_trim_semantic_violation_returns_400(client):
    payload = _intent(actions=[{"type": "trim", "cut_id": "c1", "in_seconds": 8, "out_seconds": 3}])
    resp = client.post("/intents", json=payload)
    assert resp.status_code == 400


def test_path_escape_returns_400(client):
    resp = client.post("/intents", json=_intent(project_id="../evil"))
    assert resp.status_code == 400


def test_locked_edit_gate_rejects_direct_post_without_writing(client, tmp_path):
    source = (
        tmp_path
        / "projects"
        / "demo-pro"
        / "assets"
        / "video"
        / "cut_01.mp4"
    )
    source.unlink()

    resp = client.post("/intents", json=_intent())

    assert resp.status_code == 409
    assert "cut_source_missing" in resp.json()["detail"]["reason_codes"]
    assert not (
        tmp_path
        / "projects"
        / "demo-pro"
        / "intents"
        / "intent-001.json"
    ).exists()


def test_dirty_cuts_reject_new_intent_until_canonical_render_matches(
    client, tmp_path
):
    project = tmp_path / "projects" / "demo-pro"
    decisions_path = project / "artifacts" / "edit_decisions.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    decisions["requires_compose"] = True
    decisions["cuts_revision"] = cuts_digest(decisions["cuts"])
    decisions_path.write_text(json.dumps(decisions), encoding="utf-8")

    locked = client.post("/intents", json=_intent())

    assert locked.status_code == 409
    detail = locked.json()["detail"]
    assert detail["kind"] == "editing_gate"
    assert "compose_required" in detail["reason_codes"]
    assert not (project / "intents" / "intent-001.json").exists()

    draft_path = project / "artifacts" / "full_draft_pro.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["cuts_revision"] = decisions["cuts_revision"]
    draft_path.write_text(json.dumps(draft), encoding="utf-8")

    assert client.post("/intents", json=_intent()).status_code == 201

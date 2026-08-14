"""API tests for interaction intents sharing POST /intents."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

import lib.interaction_intents as ii
from backlot import server as server_mod
from backlot.server import app


@pytest.fixture
def interaction_client(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = root / "demo-pro"
    project.mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": "demo-pro",
                "title": "Interaction intent API",
                "pipeline_type": "bootstrap-commercial",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(server_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(ii, "PROJECTS_DIR", root)
    with TestClient(app) as client:
        yield client, project


def _interaction(**overrides):
    summary = overrides.pop("summary", "采用轻度档并等待素材评审")
    data = {
        "version": "1.0",
        "intent_type": "decision",
        "intent_id": "interaction-001",
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


def _edit_intent():
    return {
        "version": "1.0",
        "intent_id": "edit-001",
        "project_id": "demo-pro",
        "created_at": "2026-08-14T01:00:00+00:00",
        "status": "pending",
        "base": {
            "artifact": "edit_decisions",
            "cuts_revision": "v1",
            "source_render": "renders/draft.mp4",
        },
        "actions": [{"type": "delete", "cut_id": "c01"}],
    }


def test_interaction_post_writes_only_intent_file(interaction_client):
    client, project = interaction_client

    response = client.post("/intents", json=_interaction(risk_level="browser-low"))

    assert response.status_code == 201
    assert response.json() == {
        "intent_id": "interaction-001",
        "status": "pending",
        "duplicate": False,
    }
    stored = json.loads(
        (project / "intents" / "interaction-001.json").read_text(encoding="utf-8")
    )
    assert stored["intent_type"] == "decision"
    assert "risk_level" not in stored
    assert list(project.glob("checkpoint_*.json")) == []
    assert list(project.glob("artifacts/*.json")) == []


def test_interaction_post_never_loads_editing_gate(
    interaction_client, monkeypatch
):
    client, _project = interaction_client

    def fail_if_loaded(_project_dir):
        raise AssertionError("interaction path must split before editing_gate")

    monkeypatch.setattr(server_mod, "load_board_state", fail_if_loaded)

    response = client.post(
        "/intents",
        json=_interaction(intent_id="interaction-no-gate"),
    )

    assert response.status_code == 201


def test_interaction_duplicate_identical_returns_200(interaction_client):
    client, _project = interaction_client
    payload = _interaction()
    assert client.post("/intents", json=payload).status_code == 201

    response = client.post("/intents", json=payload)

    assert response.status_code == 200
    assert response.json()["duplicate"] is True


def test_interaction_same_id_different_body_returns_409(interaction_client):
    client, _project = interaction_client
    assert client.post("/intents", json=_interaction()).status_code == 201

    response = client.post(
        "/intents",
        json=_interaction(payload={"production_tier": "heavy"}),
    )

    assert response.status_code == 409


def test_missing_intent_type_still_hits_editing_gate(interaction_client):
    client, project = interaction_client

    response = client.post("/intents", json=_edit_intent())

    assert response.status_code == 409
    assert response.json()["detail"]["kind"] == "editing_gate"
    assert not (project / "intents" / "edit-001.json").exists()


def test_unknown_intent_type_returns_400_before_editing_gate(interaction_client):
    client, _project = interaction_client

    response = client.post(
        "/intents",
        json=_interaction(intent_type="mystery"),
    )

    assert response.status_code == 400
    assert "unknown intent_type" in response.json()["detail"]


def test_get_lists_only_interaction_intents(interaction_client):
    client, project = interaction_client
    intents_dir = project / "intents"
    intents_dir.mkdir()
    (intents_dir / "edit-001.json").write_text(
        json.dumps(_edit_intent()),
        encoding="utf-8",
    )
    assert client.post("/intents", json=_interaction()).status_code == 201

    response = client.get("/api/project/demo-pro/interaction-intents")

    assert response.status_code == 200
    assert response.json()["project_id"] == "demo-pro"
    assert [item["intent_id"] for item in response.json()["intents"]] == [
        "interaction-001"
    ]
    assert "risk_level" not in response.json()["intents"][0]


def test_expired_interaction_is_superseded_on_post_and_get(interaction_client):
    client, project = interaction_client
    payload = _interaction(
        intent_id="interaction-expired",
        expires_at="2026-08-14T02:00:00+00:00",
    )

    response = client.post("/intents", json=payload)

    assert response.status_code == 201
    assert response.json()["status"] == "superseded"
    stored = json.loads(
        (project / "intents" / "interaction-expired.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["status"] == "superseded"

    listed = client.get("/api/project/demo-pro/interaction-intents")
    assert listed.status_code == 200
    assert listed.json()["intents"][0]["status"] == "superseded"


def test_approval_bundle_empty_payload_returns_400(interaction_client):
    client, project = interaction_client

    response = client.post(
        "/intents",
        json=_interaction(
            intent_id="approval-empty",
            intent_type="approval_bundle",
            payload={},
        ),
    )

    assert response.status_code == 400
    assert not (project / "intents" / "approval-empty.json").exists()


def test_get_unknown_project_returns_404(interaction_client):
    client, project = interaction_client
    (project.parent / "folder-only").mkdir()

    response = client.get("/api/project/missing/interaction-intents")
    folder_only = client.get("/api/project/folder-only/interaction-intents")

    assert response.status_code == 404
    assert folder_only.status_code == 404

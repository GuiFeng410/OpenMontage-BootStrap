"""Tests for the board's sole write exception: POST /intents."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import lib.edit_intents as ei
from backlot import server as server_mod
from backlot.server import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    (root / "demo-pro").mkdir(parents=True)
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
        "base": {"artifact": "edit_decisions", "cuts_revision": "v2"},
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


def test_schema_violation_returns_400(client):
    resp = client.post("/intents", json=_intent(status="bogus"))
    assert resp.status_code == 400


def test_trim_semantic_violation_returns_400(client):
    payload = _intent(actions=[{"type": "trim", "cut_id": "c1", "in_seconds": 8, "out_seconds": 3}])
    resp = client.post("/intents", json=payload)
    assert resp.status_code == 400


def test_path_escape_returns_400(client):
    resp = client.post("/intents", json=_intent(project_id="../evil"))
    assert resp.status_code == 400

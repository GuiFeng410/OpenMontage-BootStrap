"""End-and-export copies final.mp4 and marks the project completed."""

from __future__ import annotations

import hashlib
import json

import pytest

import lib.interaction_intents as ii
import lib.project_export as pe


def _write_project(root, project_id="demo-pro", **marker):
    project = root / project_id
    project.mkdir(parents=True)
    (project / "renders").mkdir()
    payload = {
        "version": "1.0",
        "project_id": project_id,
        "title": "Demo",
        "pipeline_type": "bootstrap-commercial",
        **marker,
    }
    (project / "project.json").write_text(json.dumps(payload), encoding="utf-8")
    return project


def _export_intent(project_id="demo-pro"):
    summary = "结束并导出项目"
    return {
        "version": "1.0",
        "intent_type": "project_export",
        "intent_id": "export-001",
        "project_id": project_id,
        "stage": "delivery_signoff",
        "revision": "export-v1",
        "summary": summary,
        "summary_sha256": hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        "payload": {"action": "end_and_export"},
        "expires_at": "2099-01-01T00:00:00+00:00",
        "created_at": "2026-08-17T01:00:00+00:00",
        "status": "pending",
    }


@pytest.fixture
def project(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = _write_project(root)
    monkeypatch.setattr(ii, "PROJECTS_DIR", root)
    monkeypatch.setattr(pe, "PROJECTS_DIR", root)
    return project


def test_missing_final_does_not_complete(project):
    ii.create_or_conflict("demo-pro", _export_intent())
    result = pe.apply_project_export("demo-pro", intent_id="export-001")
    assert result["ok"] is False
    assert result["code"] == "missing_final"
    marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert marker.get("lifecycle_status") != "completed"
    stored = json.loads((project / "intents" / "export-001.json").read_text(encoding="utf-8"))
    assert stored["status"] == "failed"


def test_copy_and_complete(project, monkeypatch):
    monkeypatch.setattr("backlot.runner.stop_runner", lambda **_k: True)
    (project / "renders" / "final.mp4").write_bytes(b"fake-mp4")
    ii.create_or_conflict("demo-pro", _export_intent())
    result = pe.apply_project_export("demo-pro", intent_id="export-001")
    assert result["ok"] is True
    dest = project / "exports" / "final.mp4"
    assert dest.read_bytes() == b"fake-mp4"
    marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert marker["lifecycle_status"] == "completed"
    assert marker["export_path"] == "exports/final.mp4"
    stored = json.loads((project / "intents" / "export-001.json").read_text(encoding="utf-8"))
    assert stored["status"] == "applied"


def test_chat_phrase_without_intent(project):
    (project / "renders" / "final.mp4").write_bytes(b"ok")
    result = pe.apply_project_export("demo-pro", confirm_phrase="结束导出")
    assert result["ok"] is True
    assert (project / "exports" / "final.mp4").is_file()

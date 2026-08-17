"""Board runner consumes pending export intents without paid generate."""

from __future__ import annotations

import json

import lib.board_runner as runner
import lib.interaction_intents as ii
import lib.project_export as pe
from tests.lib.test_project_export import _export_intent, _write_project


def test_tick_exports_when_final_exists(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = _write_project(root)
    (project / "renders" / "final.mp4").write_bytes(b"film")
    monkeypatch.setattr(ii, "PROJECTS_DIR", root)
    monkeypatch.setattr(pe, "PROJECTS_DIR", root)
    monkeypatch.setattr(runner, "PROJECTS_DIR", root)
    ii.create_or_conflict("demo-pro", _export_intent())

    result = runner.tick("demo-pro", append_decision=lambda *_: {})
    assert result["phase"] == "exported"
    assert "project_export" in result["actions"]
    marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert marker["lifecycle_status"] == "completed"

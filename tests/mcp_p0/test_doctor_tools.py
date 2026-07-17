"""P0 doctor tool smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

from openmontage.mcp.common.envelope import ok
from openmontage.mcp.doctor.tools import run_doctor, run_list_pipelines


def test_envelope_has_versions() -> None:
    payload = ok({"x": 1})
    assert payload["ok"] is True
    assert payload["contract_version"]
    assert payload["openmontage_version"]


def test_doctor_marks_no_video_production() -> None:
    data = run_doctor(deep=False)
    assert data["can_produce_video_now"] is False
    assert data["p0_write_policy"]["default_agent_writes"] is False
    assert "binaries" in data
    assert "registry" in data
    assert isinstance(data["registry"].get("tool_count"), int)


def test_list_pipelines_sees_animated_explainer() -> None:
    data = run_list_pipelines()
    assert "animated-explainer" in data["pipeline_defs_present"]
    packs = data["skill_packs_present"]
    assert "openmontage-router" in packs
    assert "openmontage-gates-intro" in packs


def test_validate_artifact_under_sandbox(monkeypatch, tmp_path: Path) -> None:
    from openmontage.mcp.doctor.tools import run_validate_artifact

    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    # Minimal research_brief may fail schema — we only assert path sandbox + response shape
    sample = tmp_path / "artifacts"
    sample.mkdir()
    path = sample / "noop.json"
    path.write_text(json.dumps({"hello": 1}), encoding="utf-8")
    result = run_validate_artifact(str(path), artifact_type="research_brief")
    assert result["path"] == str(path.resolve())
    assert "validated" in result

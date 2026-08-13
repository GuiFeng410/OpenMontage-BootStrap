"""P0 doctor tool smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openmontage.mcp.common.envelope import ok
from openmontage.mcp.doctor.tools import run_doctor, run_list_pipelines


def test_envelope_has_versions() -> None:
    payload = ok({"x": 1})
    assert payload["ok"] is True
    assert payload["contract_version"]
    assert payload["openmontage_version"]


def test_doctor_default_write_policy() -> None:
    data = run_doctor(deep=False)
    assert data["p0_write_policy"]["default_agent_writes"] is False
    assert isinstance(data["can_produce_video_now"], bool)
    assert "binaries" in data
    assert "registry" in data
    assert isinstance(data["registry"].get("tool_count"), int)
    assert "openmontage-animated-explainer" in data["installed_skill_packs"]


def test_list_pipelines_sees_animated_explainer() -> None:
    data = run_list_pipelines()
    assert "animated-explainer" in data["pipeline_defs_present"]
    packs = data["skill_packs_present"]
    assert "openmontage-router" in packs
    assert "openmontage-gates-intro" in packs
    assert "openmontage-animated-explainer" in packs
    assert "openmontage-production-contract" in packs


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


@pytest.mark.parametrize("checkpoint_subdir", ["", "history"])
def test_validate_completed_commercial_assets_gate_uses_project_context(
    monkeypatch,
    tmp_path: Path,
    checkpoint_subdir: str,
) -> None:
    from PIL import Image

    from openmontage.mcp.doctor.tools import run_validate_checkpoint

    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    project_id = "doctor-commercial-assets"
    project = tmp_path / project_id
    artifacts = project / "artifacts"
    image_path = project / "assets" / "images" / "hero.png"
    artifacts.mkdir(parents=True)
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(image_path)
    (project / "project.json").write_text(json.dumps({
        "version": "1.0",
        "project_id": project_id,
        "pipeline_type": "bootstrap-commercial",
    }), encoding="utf-8")
    (artifacts / "segment_cards.json").write_text(json.dumps({
        "version": "1.0",
        "duration_seconds": 5,
        "overall_prompt_zh": "商品主图建立身份。",
        "segments": [{
            "beat": "S1",
            "time": "0-5",
            "copy_plan_zh": "商品亮相",
            "shot_plan_zh": "主图轻推",
            "asset_plan_zh": "使用商品主图",
        }],
    }), encoding="utf-8")
    (artifacts / "video_plan.json").write_text(json.dumps({
        "segments": [{
            "id": "S1",
            "t": "0-5",
            "ref_image": "assets/images/hero.png",
        }],
    }), encoding="utf-8")
    (artifacts / "asset_ledger.json").write_text(json.dumps({
        "version": "1.0",
        "entries": [{
            "path": "assets/images/hero.png",
            "user_class": "product_hero",
            "status": "confirmed",
            "selected": True,
            "beats": ["S1"],
            "kind": "image",
            "origin": "user_upload",
        }],
        "summary": {
            "available_image_count": 1,
            "counts_by_class": {"product_hero": 1},
            "status_zh": "就绪",
        },
    }), encoding="utf-8")
    checkpoint = project / checkpoint_subdir / "checkpoint_assets_gate.json"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(json.dumps({
        "version": "1.0",
        "project_id": project_id,
        "pipeline_type": "bootstrap-commercial",
        "stage": "assets_gate",
        "status": "completed",
        "timestamp": "2026-08-13T00:00:00+00:00",
        "checkpoint_policy": "guided",
        "human_approval_required": False,
        "human_approved": False,
        "artifacts": {
            "asset_ledger": "artifacts/asset_ledger.json",
        },
    }), encoding="utf-8")

    result = run_validate_checkpoint(str(checkpoint))

    assert result["validated"] is True

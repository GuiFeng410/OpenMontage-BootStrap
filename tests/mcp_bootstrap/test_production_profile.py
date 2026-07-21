"""Production profile persistence for BootStrap tiers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openmontage.mcp.bootstrap.tools import (
    list_bootstrap_tools,
    produce_init_project,
    produce_read_state,
    produce_set_production_profile,
    produce_write_checkpoint,
)
from openmontage.mcp.common.errors import DoctorError
from openmontage.mcp.doctor.tools import run_get_project_state, run_set_production_profile


@pytest.fixture
def sandbox(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    return tmp_path


def test_list_bootstrap_includes_set_profile() -> None:
    data = list_bootstrap_tools()
    assert "produce_set_production_profile" in data["produce_minimal"]


def test_set_profile_defaults_and_read_state(sandbox: Path) -> None:
    produce_init_project("tier_demo", "Tier Demo", "animated-explainer")
    set_result = produce_set_production_profile("tier_demo", "medium")
    assert set_result["production_profile"] == {
        "production_tier": "medium",
        "visual_source": "stock",
        "tts_source": "piper",
    }
    state = produce_read_state("tier_demo")
    assert state["production_profile"]["production_tier"] == "medium"
    assert state["production_profile"]["visual_source"] == "stock"
    marker = json.loads((sandbox / "tier_demo" / "project.json").read_text(encoding="utf-8"))
    assert marker["production_profile"]["tts_source"] == "piper"


def test_medium_can_override_tts_to_paid(sandbox: Path) -> None:
    produce_init_project("med_tts", "Med TTS", "animated-explainer")
    produce_set_production_profile("med_tts", "medium")
    produce_set_production_profile("med_tts", "medium", tts_source="paid")
    state = produce_read_state("med_tts")
    assert state["production_profile"] == {
        "production_tier": "medium",
        "visual_source": "stock",
        "tts_source": "paid",
    }


def test_heavy_defaults(sandbox: Path) -> None:
    produce_init_project("heavy1", "Heavy", "animated-explainer")
    run_set_production_profile("heavy1", "heavy")
    state = run_get_project_state("heavy1")
    assert state["production_profile"] == {
        "production_tier": "heavy",
        "visual_source": "paid_gen",
        "tts_source": "paid",
    }


def test_invalid_tier_rejected(sandbox: Path) -> None:
    produce_init_project("bad", "Bad", "animated-explainer")
    with pytest.raises(DoctorError, match="production_tier"):
        produce_set_production_profile("bad", "ultra")


def test_checkpoint_artifacts_sync_to_marker(sandbox: Path) -> None:
    produce_init_project("cp_sync", "CP Sync", "animated-explainer")
    # in_progress 不强制 canonical artifact；非 ARTIFACT_NAMES 的档位字段可原样写入
    artifacts = json.dumps(
        {
            "production_tier": "light",
            "note": "also syncs flat keys",
        }
    )
    written = produce_write_checkpoint(
        "cp_sync",
        "proposal",
        "in_progress",
        artifacts_json=artifacts,
    )
    assert written["production_profile"]["production_tier"] == "light"
    assert written["production_profile"]["visual_source"] == "template"
    state = produce_read_state("cp_sync")
    assert state["production_profile"]["tts_source"] == "piper"

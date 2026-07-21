"""Phase C: BGM register + compose input bundle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openmontage.mcp.bootstrap.tools import (
    list_bootstrap_tools,
    produce_build_compose_inputs,
    produce_init_project,
    produce_register_music,
    produce_scan_copy_music,
    produce_segment_copy_to_subtitles,
    produce_write_copy,
)
from openmontage.mcp.common.errors import ConfigError
from schemas.artifacts import validate_artifact


@pytest.fixture
def sandbox(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    return tmp_path


def test_list_includes_phase_c_tools() -> None:
    names = list_bootstrap_tools()["produce_minimal"]
    assert "produce_import_music" in names
    assert "produce_register_music" in names
    assert "produce_build_compose_inputs" in names
    assert "produce_mix_narration_and_music" in names
    assert "mix_audio" not in list_bootstrap_tools()["not_in_v1"]


def test_register_music_and_build_compose_inputs(sandbox: Path) -> None:
    produce_init_project("c1", "C1", "animated-explainer")
    produce_write_copy("c1", "第一句。第二句。", confirm=True)
    produce_segment_copy_to_subtitles("c1", confirm_copy_ok=True)

    music_dir = sandbox / "c1" / "assets" / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    bgm = music_dir / "bed.mp3"
    bgm.write_bytes(b"ID3fake")

    scan = produce_scan_copy_music("c1")
    assert scan["has_music"] is True

    with pytest.raises(ConfigError, match="confirm=true"):
        produce_register_music("c1", confirm=False)

    reg = produce_register_music("c1", confirm=True, volume=0.3)
    assert reg["asset_id"] == "music_bgm"
    assert Path(reg["path"]).exists()

    bundle = produce_build_compose_inputs("c1", music_volume=0.3)
    assert bundle["has_music"] is True
    assert bundle["has_subtitles"] is True
    edit = json.loads(bundle["edit_decisions_json"])
    assert edit["audio"]["music"]["asset_id"] == "music_bgm"
    assert edit["subtitles"]["enabled"] is True
    assert edit["subtitles"]["source"] == "subs_main"
    validate_artifact("asset_manifest", bundle["asset_manifest"])
    types = {a["type"] for a in bundle["asset_manifest"]["assets"]}
    assert "music" in types
    assert "subtitle" in types
    assert "mix_dependency" in bundle
    assert "produce_compose" in bundle["compose_hint"]


def test_build_compose_inputs_without_music(sandbox: Path) -> None:
    produce_init_project("c2", "C2", "animated-explainer")
    produce_write_copy("c2", "只有字幕。", confirm=True)
    produce_segment_copy_to_subtitles("c2", confirm_copy_ok=True)
    bundle = produce_build_compose_inputs("c2", include_music=True)
    assert bundle["has_subtitles"] is True
    assert bundle["has_music"] is False
    assert any("No BGM" in w or "missing" in w for w in bundle["warnings"])

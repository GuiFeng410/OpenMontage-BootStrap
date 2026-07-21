"""Phase B: copy → subtitles → asset_manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openmontage.mcp.bootstrap.tools import (
    list_bootstrap_tools,
    produce_init_project,
    produce_read_asset_manifest,
    produce_scan_copy_music,
    produce_segment_copy_to_subtitles,
    produce_write_copy,
)
from openmontage.mcp.common.captions_music import split_copy_into_cues
from openmontage.mcp.common.errors import ConfigError
from schemas.artifacts import validate_artifact


@pytest.fixture
def sandbox(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    return tmp_path


def test_list_includes_captions_tools() -> None:
    names = list_bootstrap_tools()["produce_minimal"]
    assert "produce_scan_copy_music" in names
    assert "produce_segment_copy_to_subtitles" in names
    assert "produce_write_copy" in names


def test_split_copy_into_cues_basic() -> None:
    segs = split_copy_into_cues("天空为什么是蓝色的。因为阳光被大气散射。", chars_per_second=4.0)
    assert len(segs) >= 2
    assert segs[0]["start"] == 0.0
    assert segs[-1]["end"] > segs[0]["end"]
    assert all("text" in s and "start" in s and "end" in s for s in segs)


def test_write_copy_requires_confirm(sandbox: Path) -> None:
    produce_init_project("cap1", "Cap", "animated-explainer")
    with pytest.raises(ConfigError, match="confirm=true"):
        produce_write_copy("cap1", "hello", confirm=False)


def test_scan_write_segment_register(sandbox: Path) -> None:
    produce_init_project("cap2", "Cap2", "animated-explainer")
    scan0 = produce_scan_copy_music("cap2")
    assert scan0["has_copy"] is False
    assert (sandbox / "cap2" / "assets" / "copy").is_dir()

    written = produce_write_copy(
        "cap2",
        "第一句说明主题。第二句补充原因。第三句收束。",
        confirm=True,
    )
    assert Path(written["path"]).exists()

    scan1 = produce_scan_copy_music("cap2")
    assert scan1["has_copy"] is True

    with pytest.raises(ConfigError, match="confirm_copy_ok"):
        produce_segment_copy_to_subtitles("cap2", confirm_copy_ok=False)

    out = produce_segment_copy_to_subtitles("cap2", confirm_copy_ok=True)
    assert out["segment_count"] >= 2
    assert Path(out["subtitle_path"]).exists()
    assert out["subtitle_path"].endswith("captions.srt")
    srt = Path(out["subtitle_path"]).read_text(encoding="utf-8")
    assert "-->" in srt

    manifest = produce_read_asset_manifest("cap2")
    assert manifest["asset_count"] >= 1
    types = {a["type"] for a in manifest["asset_manifest"]["assets"]}
    assert "subtitle" in types
    validate_artifact("asset_manifest", manifest["asset_manifest"])
    assert json.loads(out["segments_json"])[0]["text"]

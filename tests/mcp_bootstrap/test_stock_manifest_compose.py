"""Medium-tier stock → asset_manifest → compose handoff tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from openmontage.mcp.bootstrap.tools import (
    produce_append_asset_manifest_entry,
    produce_compose_preflight,
    produce_init_project,
    produce_read_asset_manifest,
    produce_set_production_profile,
)
from openmontage.mcp.common.asset_manifest import build_stock_asset_entry, upsert_asset_entry
from openmontage.mcp.providers_stock.tools import stock_download
from schemas.artifacts import validate_artifact


@pytest.fixture
def sandbox(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    monkeypatch.setenv("PEXELS_API_KEY", "dummy")
    return tmp_path


def test_append_stock_entry_schema_and_read(sandbox: Path) -> None:
    produce_init_project("med1", "Medium", "animated-explainer")
    produce_set_production_profile("med1", "medium")
    img = sandbox / "med1" / "assets" / "stock" / "sky.jpg"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"fake-jpeg")
    entry = build_stock_asset_entry(
        project_id="med1",
        asset_id="shot_01",
        media_kind="image",
        absolute_path=str(img),
        source="pexels",
        tool_name="pexels_image",
        scene_id="scene_01",
        query="blue sky",
        license_text="Pexels License",
    )
    registered = upsert_asset_entry("med1", entry)
    assert registered["asset_count"] == 1
    validate_artifact("asset_manifest", registered["asset_manifest"])
    read = produce_read_asset_manifest("med1")
    assert read["exists"] is True
    assert read["asset_count"] == 1
    assert read["asset_manifest"]["assets"][0]["path"] == "assets/stock/sky.jpg"
    assert read["asset_manifest"]["assets"][0]["subtype"] == "stock"


def test_stock_download_appends_manifest(monkeypatch, sandbox: Path) -> None:
    produce_init_project("med2", "Medium2", "animated-explainer")

    def fake_execute(inputs):
        out = Path(inputs["output_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"img")
        return MagicMock(
            success=True,
            error=None,
            data={"path": str(out)},
            artifacts=[],
            cost_usd=0.0,
            duration_seconds=0.0,
            metadata={},
        )

    fake_tool = MagicMock()
    fake_tool.execute.side_effect = fake_execute
    monkeypatch.setattr(
        "openmontage.mcp.providers_stock.tools.get_tool",
        lambda _name: fake_tool,
    )
    monkeypatch.setattr(
        "openmontage.mcp.providers_stock.tools.tool_result_to_dict",
        lambda result: {
            "success": True,
            "error": None,
            "data": result.data,
            "license": "Pexels License",
        },
    )

    payload = stock_download(
        "pexels",
        "image",
        "ocean waves",
        confirm=True,
        project_id="med2",
        scene_id="scene_01",
        asset_id="broll_01",
    )
    assert payload["asset_id"] == "broll_01"
    assert Path(payload["asset_manifest_path"]).exists()
    read = produce_read_asset_manifest("med2")
    assert read["asset_count"] == 1
    assert read["asset_manifest"]["assets"][0]["provider"] == "pexels"
    validate_artifact("asset_manifest", read["asset_manifest"])


def test_compose_preflight_accepts_stock_manifest(sandbox: Path) -> None:
    produce_init_project("med3", "Medium3", "animated-explainer")
    img = sandbox / "med3" / "assets" / "stock" / "a.jpg"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"x")
    entry = build_stock_asset_entry(
        project_id="med3",
        asset_id="a1",
        media_kind="image",
        absolute_path=str(img),
        source="pixabay",
        tool_name="pixabay_image",
        scene_id="scene_01",
        query="city",
    )
    upsert_asset_entry("med3", entry)
    read = produce_read_asset_manifest("med3")
    edit = {
        "version": "1.0",
        "timeline": [{"scene_id": "scene_01", "asset_id": "a1", "start": 0, "duration": 3}],
    }
    result = produce_compose_preflight(
        edit_decisions_json=json.dumps(edit),
        asset_manifest_json=read["asset_manifest_json"],
    )
    assert "dry_run" in result
    assert "tool_status" in result


def test_manual_append_via_produce(sandbox: Path) -> None:
    produce_init_project("med4", "Medium4", "animated-explainer")
    entry = {
        "id": "narr_01",
        "type": "narration",
        "path": "assets/audio/vo.wav",
        "source_tool": "piper_tts",
        "scene_id": "scene_01",
    }
    out = produce_append_asset_manifest_entry("med4", json.dumps(entry))
    assert out["asset_count"] == 1
    validate_artifact("asset_manifest", out["asset_manifest"])

"""Phase 1: error capture / classify / plan (no auto-apply)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openmontage.mcp.bootstrap.tools import (
    error_capture_context,
    error_classify,
    error_list_incidents,
    error_plan_recovery,
    list_bootstrap_tools,
    produce_init_project,
)
from openmontage.mcp.common.error_recovery import classify_text


@pytest.fixture
def sandbox(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    return tmp_path


def test_list_includes_error_tools() -> None:
    names = list_bootstrap_tools()["produce_minimal"]
    assert "error_capture_context" in names
    assert "error_classify" in names
    assert "error_plan_recovery" in names
    assert "error_apply_recovery" in names
    assert "probe_audio_loudness" in names
    assert "error_apply_recovery" not in list_bootstrap_tools()["not_in_v1"]


def test_classify_e01_silent_bgm() -> None:
    text = "volumedetect mean_volume: -91.0 dB input_i: -inf"
    hit = classify_text(text)
    assert hit["matched"] is True
    assert hit["playbook_id"] == "E01_silent_bgm"


def test_classify_e02_subtitle_colon() -> None:
    text = 'Error: Unable to parse "original_size" option value "\\workfile\\sub.srt"\nsubtitles=D:\\workfile\\sub.srt'
    hit = classify_text(text)
    assert hit["playbook_id"] == "E02_subtitle_drive_colon"


def test_classify_e03_powershell() -> None:
    text = "ParserError: The token '&&' is not a valid statement separator"
    hit = classify_text(text)
    assert hit["playbook_id"] == "E03_powershell_arg_escaping"


def test_classify_e04_amix_bitrate() -> None:
    text = "ffmpeg amix duck encode aac Qavg: 65536 output 2kbps mixed.wav"
    hit = classify_text(text)
    assert hit["playbook_id"] == "E04_amix_aac_bitrate_collapse"


def test_classify_unknown() -> None:
    hit = classify_text("completely unrelated network DNS failure XYZ")
    assert hit["matched"] is False
    assert hit["playbook_id"] == "E00_unknown"


def test_capture_classify_plan_persist(sandbox: Path) -> None:
    produce_init_project("err1", "Err1", "animated-explainer")
    stderr = 'Unable to parse "original_size" option value\nsubtitles=D:\\a\\b\\captions.srt'
    cap = error_capture_context(
        "err1",
        tool_name="produce_compose_start",
        stage="compose",
        stderr=stderr,
        paths_json=json.dumps({"subtitle": r"D:\a\b\captions.srt"}),
    )
    assert cap["incident_id"].startswith("inc_")
    assert cap["playbook_id"] == "E02_subtitle_drive_colon"
    assert Path(cap["error_recovery_path"]).exists()

    clf = error_classify("err1", cap["incident_id"])
    assert clf["matched"] is True
    assert clf["title_zh"]

    plan = error_plan_recovery("err1", cap["incident_id"])
    assert plan["plan"]["playbook_id"] == "E02_subtitle_drive_colon"
    assert plan["plan"]["max_retries"] == 3
    assert plan["plan"]["apply_available"] is True
    assert plan["plan"]["phase"] == 2
    assert plan["plan"]["auto_allowed"] is True
    assert any(a["id"] == "copy_srt_to_work_relpath" for a in plan["plan"]["actions"])

    listed = error_list_incidents("err1")
    assert listed["count"] == 1
    assert listed["incidents"][0]["incident_id"] == cap["incident_id"]

    state = json.loads(Path(cap["error_recovery_path"]).read_text(encoding="utf-8"))
    assert state["incidents"][cap["incident_id"]]["status"] == "planned"

"""Phase 2: error_apply_recovery + probe helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openmontage.mcp.bootstrap.tools import (
    error_apply_recovery,
    error_capture_context,
    error_plan_recovery,
    produce_init_project,
    produce_register_music,
)
from openmontage.mcp.common.errors import ConfigError, DoctorError


@pytest.fixture
def sandbox(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    return tmp_path


def test_apply_e02_copies_srt_to_work(sandbox: Path) -> None:
    produce_init_project("e02", "E02", "animated-explainer")
    subs = sandbox / "e02" / "assets" / "subs"
    subs.mkdir(parents=True, exist_ok=True)
    srt = subs / "main.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")

    stderr = 'Unable to parse "original_size"\nsubtitles=D:\\x\\main.srt'
    cap = error_capture_context(
        "e02",
        "produce_compose_start",
        "compose",
        stderr,
        paths_json=json.dumps({"subtitle": str(srt)}),
    )
    plan = error_plan_recovery("e02", cap["incident_id"])
    assert plan["plan"]["apply_available"] is True

    applied = error_apply_recovery("e02", cap["incident_id"])
    assert applied["retry_count"] == 1
    assert applied["all_ok"] is True
    work = sandbox / "e02" / "assets" / "subs" / "_work" / "captions.srt"
    assert work.exists()
    rels = [r.get("relative_path") for r in applied["results"] if r.get("relative_path")]
    assert any(str(p).replace("\\", "/").endswith("assets/subs/_work/captions.srt") for p in rels)


def test_apply_high_risk_needs_confirm(sandbox: Path) -> None:
    produce_init_project("e01c", "E01c", "animated-explainer")
    music = sandbox / "e01c" / "assets" / "music"
    music.mkdir(parents=True, exist_ok=True)
    (music / "bed.mp3").write_bytes(b"ID3fake")
    produce_register_music("e01c", confirm=True)

    cap = error_capture_context(
        "e01c",
        "produce_mix_narration_and_music",
        "mix",
        "mean_volume: -91.0 dB input_i: -inf",
    )
    with pytest.raises(ConfigError, match="confirm=true"):
        error_apply_recovery("e01c", cap["incident_id"], action_ids="replace_bgm", confirm=False)


def test_apply_retry_budget_exhausted(sandbox: Path) -> None:
    produce_init_project("e02x", "E02x", "animated-explainer")
    subs = sandbox / "e02x" / "assets" / "subs"
    subs.mkdir(parents=True, exist_ok=True)
    (subs / "a.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")

    cap = error_capture_context(
        "e02x",
        "compose",
        "compose",
        'Unable to parse "original_size" option',
        paths_json=json.dumps({"subtitle": str(subs / "a.srt")}),
    )
    for _ in range(3):
        error_apply_recovery("e02x", cap["incident_id"])
    with pytest.raises(DoctorError, match="exhausted"):
        error_apply_recovery("e02x", cap["incident_id"])


def test_apply_e03_without_command_returns_hint(sandbox: Path) -> None:
    produce_init_project("e03", "E03", "animated-explainer")
    cap = error_capture_context(
        "e03",
        "ffmpeg",
        "shell",
        "ParserError: The token '&&' is not a valid statement separator",
    )
    applied = error_apply_recovery("e03", cap["incident_id"])
    assert applied["retry_count"] == 1
    assert applied["results"][0]["action"] == "rerun_via_python_subprocess_list"
    assert applied["results"][0]["executed"] is False
    assert "subprocess" in applied["results"][0]["hint"].lower()


def test_apply_e01_skip_bgm_writes_hints(sandbox: Path) -> None:
    produce_init_project("e01", "E01", "animated-explainer")
    music = sandbox / "e01" / "assets" / "music"
    music.mkdir(parents=True, exist_ok=True)
    (music / "bed.mp3").write_bytes(b"ID3fake")
    produce_register_music("e01", confirm=True)

    cap = error_capture_context(
        "e01",
        "mix",
        "mix",
        "mean_volume: -91.0 dB input_i: -inf",
    )
    # Only skip + mark (skip loudness if no ffmpeg) — still valid auto set
    applied = error_apply_recovery(
        "e01",
        cap["incident_id"],
        action_ids="mark_manifest_invalid,skip_bgm_continue",
    )
    assert applied["all_ok"] is True
    hints = sandbox / "e01" / "artifacts" / "recovery_hints.json"
    assert hints.exists()
    data = json.loads(hints.read_text(encoding="utf-8"))
    assert data["include_music"] is False

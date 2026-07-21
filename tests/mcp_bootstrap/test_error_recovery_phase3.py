"""Phase 3: zero-key synth BGM + stderr fixture classify."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from openmontage.mcp.bootstrap.tools import (
    error_apply_recovery,
    error_capture_context,
    error_classify,
    list_bootstrap_tools,
    produce_init_project,
    produce_register_music,
    produce_synthesize_bgm,
)
from openmontage.mcp.common.error_recovery import classify_text
from openmontage.mcp.common.errors import ConfigError

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "error_stderr"


@pytest.fixture
def sandbox(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    return tmp_path


def test_list_includes_synthesize_bgm() -> None:
    names = list_bootstrap_tools()["produce_minimal"]
    assert "produce_synthesize_bgm" in names


@pytest.mark.parametrize(
    "filename,expected_id",
    [
        ("e01_silent_bgm.txt", "E01_silent_bgm"),
        ("e02_subtitle_colon.txt", "E02_subtitle_drive_colon"),
        ("e03_powershell.txt", "E03_powershell_arg_escaping"),
        ("e04_amix_aac.txt", "E04_amix_aac_bitrate_collapse"),
    ],
)
def test_fixture_stderr_classifies(filename: str, expected_id: str) -> None:
    text = (FIXTURES / filename).read_text(encoding="utf-8")
    hit = classify_text(text)
    assert hit["matched"] is True
    assert hit["playbook_id"] == expected_id


def test_produce_synthesize_bgm_needs_confirm(sandbox: Path) -> None:
    produce_init_project("syn0", "Syn0", "animated-explainer")
    with pytest.raises(ConfigError, match="confirm=true"):
        produce_synthesize_bgm("syn0", confirm=False)


def test_produce_synthesize_bgm_writes_wav(sandbox: Path) -> None:
    produce_init_project("syn1", "Syn1", "animated-explainer")
    music = sandbox / "syn1" / "assets" / "music"
    music.mkdir(parents=True, exist_ok=True)
    (music / "dead.mp3").write_bytes(b"ID3fake-silent")
    produce_register_music("syn1", confirm=True)

    out = produce_synthesize_bgm("syn1", duration_seconds=2.0, confirm=True)
    wav = Path(out["synthesized_path"])
    assert wav.exists()
    assert wav.stat().st_size > 1000
    with wave.open(str(wav), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 44100
        assert wf.getnframes() >= 44100  # ~2s
    archived = out.get("archived_invalid") or []
    assert any("dead.mp3" in str(p) for p in archived)
    invalid = music / "_invalid"
    assert invalid.exists()
    assert any(p.name.startswith("dead") for p in invalid.iterdir())


def test_apply_replace_bgm_with_confirm(sandbox: Path) -> None:
    produce_init_project("e01r", "E01r", "animated-explainer")
    music = sandbox / "e01r" / "assets" / "music"
    music.mkdir(parents=True, exist_ok=True)
    (music / "bed.mp3").write_bytes(b"ID3fake")
    produce_register_music("e01r", confirm=True)

    cap = error_capture_context(
        "e01r",
        "produce_mix_narration_and_music",
        "mix",
        "mean_volume: -91.0 dB input_i: -inf",
        paths_json=json.dumps({"duration_seconds": 2.0}),
    )
    assert cap["playbook_id"] == "E01_silent_bgm"

    with pytest.raises(ConfigError, match="confirm=true"):
        error_apply_recovery("e01r", cap["incident_id"], action_ids="replace_bgm", confirm=False)

    applied = error_apply_recovery(
        "e01r",
        cap["incident_id"],
        action_ids="replace_bgm",
        confirm=True,
    )
    assert applied["all_ok"] is True
    assert applied["results"][0]["action"] == "replace_bgm"
    synth = music / "synth_ambient.wav"
    assert synth.exists()
    assert synth.stat().st_size > 1000


def test_apply_synthesize_alias(sandbox: Path) -> None:
    produce_init_project("e01a", "E01a", "animated-explainer")
    (sandbox / "e01a" / "assets" / "music").mkdir(parents=True, exist_ok=True)

    cap = error_capture_context(
        "e01a",
        "mix",
        "mix",
        (FIXTURES / "e01_silent_bgm.txt").read_text(encoding="utf-8"),
        paths_json=json.dumps({"duration_seconds": 2.0}),
    )
    classified = error_classify("e01a", cap["incident_id"])
    assert classified["playbook_id"] == "E01_silent_bgm"

    applied = error_apply_recovery(
        "e01a",
        cap["incident_id"],
        action_ids="synthesize_replacement_bgm",
        confirm=True,
    )
    assert applied["all_ok"] is True
    assert (sandbox / "e01a" / "assets" / "music" / "synth_ambient.wav").exists()

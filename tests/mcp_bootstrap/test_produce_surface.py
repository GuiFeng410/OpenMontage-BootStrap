"""Produce surface is minimal (wrappers importable)."""

from __future__ import annotations

import openmontage.mcp.bootstrap.tools as T


def test_produce_wrappers_exist() -> None:
    for name in (
        "produce_init_project",
        "produce_tts_sample",
        "produce_tts_generate",
        "produce_generate_subtitles",
        "produce_compose_start",
        "produce_job_status",
        "produce_probe_media",
    ):
        assert callable(getattr(T, name))


def test_no_diagram_or_stitch_on_facade_module() -> None:
    assert not hasattr(T, "produce_generate_diagram")
    assert not hasattr(T, "produce_stitch_video")
    assert not hasattr(T, "produce_mix_audio")

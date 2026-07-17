"""P1 media / doctor write gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openmontage.mcp.common.errors import ConfigError
from openmontage.mcp.common.jobs import create_job, read_job, update_job
from openmontage.mcp.doctor.tools import (
    run_approve_checkpoint,
    run_init_project,
    run_write_artifact,
)
from openmontage.mcp.media.tools import tts_generate


def test_init_project_denied_without_flag(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.delenv("OPENMONTAGE_P1_ALLOW_WRITES", raising=False)
    monkeypatch.delenv("OPENMONTAGE_P0_ALLOW_WRITES", raising=False)
    with pytest.raises(ConfigError, match="OPENMONTAGE_P1_ALLOW_WRITES"):
        run_init_project("demo", "Demo", "animated-explainer")


def test_write_artifact_and_init_with_flag(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    result = run_init_project("p1demo", "P1 Demo", "animated-explainer")
    assert Path(result["project_dir"]).exists()
    art = tmp_path / "p1demo" / "artifacts" / "note.json"
    written = run_write_artifact(str(art), json.dumps({"ok": True}))
    assert Path(written["path"]).exists()
    assert json.loads(Path(written["path"]).read_text(encoding="utf-8"))["ok"] is True


def test_approve_checkpoint_requires_text(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    run_init_project("gate", "Gate", "animated-explainer")
    with pytest.raises(ConfigError, match="approval_text"):
        run_approve_checkpoint("gate", "proposal", "")


def test_tts_generate_requires_confirm(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    with pytest.raises(ConfigError, match="confirm_sample_ok"):
        tts_generate("你好", str(tmp_path / "a.wav"), confirm_sample_ok=False)


def test_job_store_roundtrip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    job = create_job("compose", {"output": "renders/final.mp4"})
    assert job["status"] == "queued"
    update_job(job["job_id"], status="running", progress=0.5)
    again = read_job(job["job_id"])
    assert again["status"] == "running"
    assert again["progress"] == 0.5
    store = tmp_path / ".openmontage_jobs"
    assert store.exists()

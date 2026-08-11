"""P1 media / doctor write gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openmontage.mcp.doctor import tools as doctor_tools
from openmontage.mcp.common.errors import ConfigError, DoctorError
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
    for rel in (
        "assets/images",
        "assets/video",
        "assets/audio",
        "assets/music",
        "assets/copy",
        "assets/subs",
        "assets/stock",
        "artifacts",
        "renders",
    ):
        assert (tmp_path / "p1demo" / rel).is_dir()
    art = tmp_path / "p1demo" / "artifacts" / "note.json"
    written = run_write_artifact(str(art), json.dumps({"ok": True}))
    assert Path(written["path"]).exists()
    assert json.loads(Path(written["path"]).read_text(encoding="utf-8"))["ok"] is True


def test_init_project_defaults_to_fresh_unique_project(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    first = run_init_project("same-title", "同名项目", "bootstrap-commercial")
    (Path(first["project_dir"]) / "checkpoint_brief_locked.json").write_text(
        json.dumps({"stage": "brief_locked", "status": "completed"}),
        encoding="utf-8",
    )

    second = run_init_project("same-title", "同名项目", "bootstrap-commercial")

    assert second["project_id"] != "same-title"
    assert second["project_id"].startswith("same-title-")
    assert second["requested_project_id"] == "same-title"
    assert second["mode"] == "create_new"
    assert second["conflict_avoided"] is True
    assert not (Path(second["project_dir"]) / "checkpoint_brief_locked.json").exists()
    assert (tmp_path / "same-title" / "checkpoint_brief_locked.json").exists()


def test_init_project_resumes_only_when_explicit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    first = run_init_project("resume-me", "续作", "bootstrap-commercial")
    marker = Path(first["project_dir"]) / "project.json"
    before = marker.read_text(encoding="utf-8")

    resumed = run_init_project(
        "resume-me",
        "续作",
        "bootstrap-commercial",
        mode="resume",
    )

    assert resumed["project_id"] == "resume-me"
    assert resumed["mode"] == "resume"
    assert resumed["resumed"] is True
    assert marker.read_text(encoding="utf-8") == before


def test_resume_rejects_missing_project(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")

    with pytest.raises(DoctorError, match="does not exist"):
        run_init_project("missing", "不存在", "bootstrap-commercial", mode="resume")


def test_import_project_images_copies_only_selected_images(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    source = run_init_project("source", "旧项目", "bootstrap-commercial")
    target = run_init_project("target", "新项目", "bootstrap-commercial")
    source_dir = Path(source["project_dir"])
    target_dir = Path(target["project_dir"])
    (source_dir / "assets" / "images" / "hero.png").write_bytes(b"image")
    (source_dir / "assets" / "video" / "stale.mp4").write_bytes(b"video")
    (source_dir / "checkpoint_brief_locked.json").write_text("{}", encoding="utf-8")

    result = doctor_tools.run_import_project_images(
        "source",
        "target",
        json.dumps(["hero.png"]),
    )

    assert result["imported"][0]["target_path"] == "assets/images/hero.png"
    assert (target_dir / "assets" / "images" / "hero.png").read_bytes() == b"image"
    assert not (target_dir / "assets" / "video" / "stale.mp4").exists()
    assert not (target_dir / "checkpoint_brief_locked.json").exists()


def test_import_project_images_rejects_path_traversal(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    run_init_project("source", "旧项目", "bootstrap-commercial")
    run_init_project("target", "新项目", "bootstrap-commercial")

    with pytest.raises(DoctorError, match="plain filename"):
        doctor_tools.run_import_project_images("source", "target", json.dumps(["../secret.png"]))


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

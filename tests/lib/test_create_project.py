"""create_project use case: init/resume without going through MCP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.application.create_project import create_project
from lib.application.errors import ApplicationError
from lib.install_state import read_install_state, snapshot_install_state
from lib.library_create import create_library_project
from lib.paths import REPO_ROOT


def test_create_project_writes_marker_without_mcp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects = tmp_path / "projects"
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(projects))
    result = create_project(
        title="Demo Film",
        pipeline_type="bootstrap-commercial",
        requested_project_id="demo-film",
    )
    marker_path = projects / "demo-film" / "project.json"
    assert result["created"] is True
    assert result["conflict_avoided"] is False
    assert result["project_id"] == "demo-film"
    assert marker_path.is_file()
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["title"] == "Demo Film"
    assert marker["pipeline_type"] == "bootstrap-commercial"


def test_create_project_isolates_duplicate_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects = tmp_path / "projects"
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(projects))
    first = create_project(
        title="Same",
        pipeline_type="bootstrap-commercial",
        requested_project_id="same-title",
    )
    second = create_project(
        title="Same",
        pipeline_type="bootstrap-commercial",
        requested_project_id="same-title",
    )
    assert first["project_id"] == "same-title"
    assert second["conflict_avoided"] is True
    assert second["project_id"] != "same-title"
    assert (projects / second["project_id"] / "project.json").is_file()


def test_create_project_resume_keeps_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects = tmp_path / "projects"
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(projects))
    created = create_project(
        title="Keep Me",
        pipeline_type="bootstrap-commercial",
        requested_project_id="resume-me",
    )
    extra = projects / "resume-me" / "artifacts" / "keep.json"
    extra.write_text("{}", encoding="utf-8")
    resumed = create_project(
        title="Keep Me",
        pipeline_type="bootstrap-commercial",
        mode="resume",
        requested_project_id="resume-me",
    )
    assert resumed["resumed"] is True
    assert resumed["created"] is False
    assert resumed["project_id"] == created["project_id"]
    assert extra.is_file()


def test_create_project_resume_missing_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    with pytest.raises(ApplicationError) as caught:
        create_project(
            title="Missing",
            pipeline_type="bootstrap-commercial",
            mode="resume",
            requested_project_id="no-such",
        )
    assert caught.value.code == "not_found"


def test_library_create_source_does_not_import_mcp() -> None:
    source = (
        REPO_ROOT / "src" / "openmontage" / "lib" / "library_create.py"
    ).read_text(encoding="utf-8")
    assert "openmontage.mcp" not in source
    assert "produce_init_project" not in source


def test_library_create_works_when_bootstrap_tools_are_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    snapshot_install_state(repo_root=tmp_path, verify_ready=False)

    def _blocked(*_args, **_kwargs):
        raise AssertionError("library_create must not call MCP produce_init_project")

    monkeypatch.setattr(
        "openmontage.mcp.bootstrap.tools.produce_init_project",
        _blocked,
    )
    result = create_library_project(title="Jade Bangle", repo_root=tmp_path)
    assert result["ok"] is True
    project_dir = Path(tmp_path / "projects" / result["project_id"])
    assert (project_dir / "project.json").is_file()


def test_library_create_does_not_set_verify_ready_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    snapshot_install_state(repo_root=tmp_path, verify_ready=False)
    create_library_project(title="Keep Flag", repo_root=tmp_path)
    listed = read_install_state(repo_root=tmp_path)
    assert listed["state"]["verify_ready"] is False


def test_library_create_preserves_existing_verify_ready_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    snapshot_install_state(repo_root=tmp_path, verify_ready=True)
    create_library_project(title="Keep True", repo_root=tmp_path)
    listed = read_install_state(repo_root=tmp_path)
    assert listed["state"]["verify_ready"] is True

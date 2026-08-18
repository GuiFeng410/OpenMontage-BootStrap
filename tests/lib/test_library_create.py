from pathlib import Path

import pytest

from lib.library_create import (
    LibraryCreateError,
    create_library_project,
    public_install_flags,
    slug_project_id,
)
from openmontage.mcp.bootstrap.install_state import snapshot_install_state


def test_flags_default_not_ready(tmp_path: Path) -> None:
    flags = public_install_flags(repo_root=tmp_path)
    assert flags["install_state_exists"] is False
    assert flags["verify_ready"] is False
    assert flags["video_key_present"] is False


def test_create_requires_title(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    with pytest.raises(LibraryCreateError) as caught:
        create_library_project(title="  ", repo_root=tmp_path)
    assert caught.value.code == "missing_title"


def test_create_patches_review_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    snapshot_install_state(repo_root=tmp_path, verify_ready=True)
    project_dir = tmp_path / "projects" / "jade-bangle-demo"
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(
        '{"project_id":"jade-bangle-demo","title":"Jade","pipeline_type":"bootstrap-commercial"}',
        encoding="utf-8",
    )

    def fake_init(project_id, title, pipeline_type="bootstrap-commercial", mode="create_new"):
        return {
            "project_id": "jade-bangle-demo",
            "project_dir": str(project_dir),
            "title": title,
            "pipeline_type": pipeline_type,
            "mode": mode,
        }

    monkeypatch.setattr(
        "openmontage.mcp.bootstrap.tools.produce_init_project",
        fake_init,
    )
    result = create_library_project(
        title="Jade Bangle",
        review_mode="pro",
        duration_seconds=20,
        asset_location="https://example.com/jade",
        repo_root=tmp_path,
        asset_files=[("hero.png", b"fake-image")],
    )
    assert result["ok"] is True
    assert result["board_path"] == "/p/jade-bangle-demo"
    marker = (project_dir / "project.json").read_text(encoding="utf-8")
    assert '"review_mode": "pro"' in marker
    assert '"review_mode_preset": "pro"' in marker
    assert '"asset_location": "https://example.com/jade"' in marker
    assert '"duration_seconds": 20' in marker
    assert (project_dir / "assets" / "images" / "hero.png").read_bytes() == b"fake-image"
    assert result["imported_count"] == 1


def test_slug_falls_back_for_chinese_title() -> None:
    assert slug_project_id("翡翠手镯").startswith("commercial-")
    assert "jade" in slug_project_id("Jade Bangle")

from pathlib import Path

import pytest

from lib.library_create import (
    LibraryCreateError,
    create_library_project,
    public_install_flags,
    refresh_key_availability,
    slug_project_id,
    start_production,
)
from openmontage.mcp.bootstrap.install_state import snapshot_install_state


def test_flags_default_not_ready(tmp_path: Path) -> None:
    flags = public_install_flags(repo_root=tmp_path)
    assert flags["install_state_exists"] is False
    assert flags["verify_ready"] is False
    assert flags["video_key_present"] is False
    assert flags["stock_key_present"] is False


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


EXAMPLE = """
## 【二、视频生成专项服务】

TOKENHUB_API_KEY=
KLING_API_KEY=
"""


def _write_ready_project(tmp_path: Path, project_id: str = "shop-demo") -> Path:
    project_dir = tmp_path / "projects" / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(
        '{"project_id":"shop-demo","title":"Shop","pipeline_type":"bootstrap-commercial"}',
        encoding="utf-8",
    )
    (tmp_path / ".env-example.md").write_text(EXAMPLE, encoding="utf-8")
    return project_dir


def test_refresh_then_keys_become_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    (tmp_path / ".env-example.md").write_text(EXAMPLE, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "TOKENHUB_API_KEY=\nPEXELS_API_KEY=\n",
        encoding="utf-8",
    )
    empty = refresh_key_availability(repo_root=tmp_path, environ={})
    assert empty["video_key_present"] is False
    assert empty["stock_key_present"] is False
    (tmp_path / ".env").write_text(
        "TOKENHUB_API_KEY=th-secret-do-not-leak-aaa\nPEXELS_API_KEY=px-secret-do-not-leak-bbb\n",
        encoding="utf-8",
    )
    filled = refresh_key_availability(repo_root=tmp_path, environ={})
    assert filled["video_key_present"] is True
    assert filled["stock_key_present"] is True
    dumped = str(filled)
    assert "th-secret-do-not-leak-aaa" not in dumped
    assert "px-secret-do-not-leak-bbb" not in dumped


def test_start_production_blocks_heavy_without_video_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    _write_ready_project(tmp_path)
    (tmp_path / ".env").write_text("TOKENHUB_API_KEY=\n", encoding="utf-8")
    with pytest.raises(LibraryCreateError) as caught:
        start_production(
            project_id="shop-demo",
            production_tier="heavy",
            repo_root=tmp_path,
            environ={},
        )
    assert caught.value.code == "missing_video_key"
    marker = (tmp_path / "projects" / "shop-demo" / "project.json").read_text(encoding="utf-8")
    assert "production_tier" not in marker


def test_start_production_blocks_medium_without_stock_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    _write_ready_project(tmp_path)
    (tmp_path / ".env").write_text("PEXELS_API_KEY=\n", encoding="utf-8")
    with pytest.raises(LibraryCreateError) as caught:
        start_production(
            project_id="shop-demo",
            production_tier="medium",
            repo_root=tmp_path,
            environ={},
        )
    assert caught.value.code == "missing_stock_key"


def test_start_production_locks_light_and_heavy_when_keys_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    project_dir = _write_ready_project(tmp_path)
    (tmp_path / ".env").write_text(
        "TOKENHUB_API_KEY=th-secret-do-not-leak-ccc\nPEXELS_API_KEY=px-secret-do-not-leak-ddd\n",
        encoding="utf-8",
    )
    light = start_production(
        project_id="shop-demo",
        production_tier="light",
        repo_root=tmp_path,
        environ={},
    )
    assert light["production_tier"] == "light"
    heavy = start_production(
        project_id="shop-demo",
        production_tier="heavy",
        repo_root=tmp_path,
        environ={},
    )
    assert heavy["ok"] is True
    assert heavy["production_tier"] == "heavy"
    marker = (project_dir / "project.json").read_text(encoding="utf-8")
    assert '"production_tier": "heavy"' in marker
    assert "th-secret-do-not-leak-ccc" not in marker
    assert "th-secret-do-not-leak-ccc" not in str(heavy)

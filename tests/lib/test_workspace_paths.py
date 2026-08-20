"""WorkspacePaths runtime resolution tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import lib.paths as paths_mod
from lib.paths import WorkspacePaths, ensure_import_roots, get_workspace
from openmontage.mcp.common.errors import ConfigError, SandboxError


def test_get_workspace_projects_dir_tracks_env_after_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    assert get_workspace().projects_dir.resolve() == tmp_path.resolve()
    assert Path(paths_mod.PROJECTS_DIR).resolve() == tmp_path.resolve()


def test_discover_repo_root_matches_checkout_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENMONTAGE_REPO_ROOT", raising=False)
    assert WorkspacePaths.discover().repo_root == paths_mod.REPO_ROOT


def test_projects_dir_strict_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENMONTAGE_PROJECTS_DIR", raising=False)
    with pytest.raises(ConfigError, match="OPENMONTAGE_PROJECTS_DIR"):
        get_workspace().projects_dir_strict()


def test_project_dir_require_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    missing = get_workspace().project_dir("demo")
    assert missing == (tmp_path / "demo").resolve()
    with pytest.raises(SandboxError, match="unknown project"):
        get_workspace().project_dir("demo", require_marker=True)
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "project.json").write_text("{}", encoding="utf-8")
    assert get_workspace().project_dir("demo", require_marker=True).is_dir()


def test_src_root_is_repo_src(tmp_path: Path) -> None:
    ws = WorkspacePaths(repo_root=tmp_path)
    assert ws.src_root == (tmp_path / "src").resolve()


def test_ensure_import_roots_puts_src_first_and_keeps_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "path", list(sys.path))
    src = str((tmp_path / "src").resolve())
    root = str(tmp_path.resolve())
    sys.path.insert(0, root)
    sys.path.append(src)
    returned = ensure_import_roots(tmp_path)
    assert returned == tmp_path.resolve()
    assert sys.path[0] == src
    assert sys.path.count(src) == 1
    assert root in sys.path
    ensure_import_roots(tmp_path)
    assert sys.path.count(src) == 1
    assert sys.path[0] == src

"""Workspace path resolver contracts for G2 infrastructure unification."""

from __future__ import annotations

from pathlib import Path

import pytest

import lib.paths as paths_mod
from lib.board_gap_plan import projects_root as gap_plan_projects_root
from lib.paths import get_workspace
from openmontage.mcp.common.errors import ConfigError
from openmontage.mcp.common.sandbox import projects_root, require_projects_root


def test_sandbox_projects_root_matches_env_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    assert projects_root() == tmp_path.resolve()


def test_require_projects_root_fails_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENMONTAGE_PROJECTS_DIR", raising=False)
    with pytest.raises(ConfigError, match="OPENMONTAGE_PROJECTS_DIR"):
        require_projects_root()


def test_paths_projects_dir_tracks_runtime_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    assert Path(paths_mod.PROJECTS_DIR).resolve() == tmp_path.resolve()


def test_gap_plan_projects_root_tracks_runtime_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    assert Path(gap_plan_projects_root()).resolve() == tmp_path.resolve()
    assert Path(gap_plan_projects_root()).resolve() == projects_root()


def test_get_workspace_projects_dir_tracks_runtime_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    assert get_workspace().projects_dir.resolve() == projects_root()

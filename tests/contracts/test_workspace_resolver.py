"""Workspace path resolver contracts for G2 infrastructure unification."""

from __future__ import annotations

from pathlib import Path

import pytest

import lib.paths as paths_mod
from backlot.state import PROJECTS_DIR as BACKLOT_PROJECTS_DIR
from lib.board_gap_plan import projects_root as gap_plan_projects_root
from lib.paths import get_workspace
from openmontage.mcp.bootstrap.install_state import read_install_state
from openmontage.mcp.common.errors import ConfigError
from openmontage.mcp.common.sandbox import projects_root, require_projects_root


def _norm(path: Path | str) -> str:
    return str(Path(path).expanduser().resolve())


def test_four_parties_share_projects_root_when_env_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    ws = get_workspace()
    payload = read_install_state(repo_root=ws.repo_root)
    assert _norm(projects_root()) == _norm(tmp_path)
    assert _norm(ws.projects_dir) == _norm(tmp_path)
    assert _norm(BACKLOT_PROJECTS_DIR) == _norm(tmp_path)
    assert _norm(payload["state"]["projects_dir"]) == _norm(tmp_path)


def test_require_projects_root_fails_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENMONTAGE_PROJECTS_DIR", raising=False)
    with pytest.raises(ConfigError, match="OPENMONTAGE_PROJECTS_DIR"):
        require_projects_root()
    ws = get_workspace()
    fallback = (ws.repo_root / "projects").resolve()
    assert ws.projects_dir == fallback
    assert Path(BACKLOT_PROJECTS_DIR).resolve() == fallback
    assert Path(paths_mod.PROJECTS_DIR).resolve() == fallback
    assert projects_root() is None


def test_sandbox_projects_root_matches_env_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    assert projects_root() == tmp_path.resolve()


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


def test_install_state_repo_root_matches_workspace() -> None:
    ws = get_workspace()
    payload = read_install_state(repo_root=ws.repo_root)
    assert _norm(payload["state"]["repo_root"]) == _norm(ws.repo_root)

"""P0 sandbox path tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from openmontage.mcp.common.errors import ConfigError, SandboxError
from openmontage.mcp.common.sandbox import project_dir, resolve_under_projects


def test_require_projects_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENMONTAGE_PROJECTS_DIR", raising=False)
    with pytest.raises(ConfigError):
        resolve_under_projects("x.json")

    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    p = resolve_under_projects("a/b.json")
    assert p == (tmp_path / "a" / "b.json").resolve()


def test_reject_escape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    outside = tmp_path.parent / "outside.txt"
    with pytest.raises(SandboxError):
        resolve_under_projects(str(outside))


def test_project_id_rejects_traversal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    with pytest.raises(SandboxError):
        project_dir("../evil")


def test_init_project_denied() -> None:
    from openmontage.mcp.doctor.tools import run_init_project_denied

    with pytest.raises(ConfigError):
        run_init_project_denied()

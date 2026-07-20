"""Bootstrap facade gate tests (no system installs)."""

from __future__ import annotations

import pytest

from openmontage.mcp.bootstrap.tools import (
    clone_repo,
    ensure_ffmpeg,
    install_python_deps,
    list_bootstrap_tools,
    plan_install,
)
from openmontage.mcp.common.errors import ConfigError


def test_list_bootstrap_tools_minimal_surface() -> None:
    data = list_bootstrap_tools()
    assert "install_python_deps" in data["bootstrap"]
    assert "produce_compose_start" in data["produce_minimal"]
    assert "diagram" in data["not_in_v1"]
    assert "stitch" in data["not_in_v1"]


def test_install_python_deps_default_dry_run() -> None:
    data = install_python_deps()
    assert data["dry_run"] is True
    assert data["executed"] is False
    assert "plan" in data


def test_install_python_deps_requires_confirm() -> None:
    with pytest.raises(ConfigError, match="confirm_execute"):
        install_python_deps(dry_run=False, confirm_execute=False)


def test_ensure_ffmpeg_dry_run_shape() -> None:
    data = ensure_ffmpeg(dry_run=True)
    assert data["dry_run"] is True
    assert "plan" in data
    assert "manual_commands" in data["plan"]


def test_clone_repo_dry_run(tmp_path) -> None:
    target = tmp_path / "om"
    data = clone_repo(str(target), source="github", dry_run=True)
    assert data["dry_run"] is True
    assert data["plan"]["primary_url"].endswith("OpenMontage-BootStrap.git")


def test_clone_repo_requires_confirm(tmp_path) -> None:
    with pytest.raises(ConfigError, match="confirm_execute"):
        clone_repo(str(tmp_path / "x"), source="gitee", dry_run=False, confirm_execute=False)


def test_plan_install_is_preview_only() -> None:
    data = plan_install()
    assert "steps" in data
    assert all(step.get("dry_run") is True or step.get("executed") is False for step in data["steps"])

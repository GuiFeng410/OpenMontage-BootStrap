"""Path sandbox: all project file access under OPENMONTAGE_PROJECTS_DIR."""

from __future__ import annotations

import os
from pathlib import Path

from lib.paths import get_workspace
from openmontage.mcp.common.errors import ConfigError, SandboxError


def projects_root() -> Path | None:
    raw = os.environ.get("OPENMONTAGE_PROJECTS_DIR", "").strip()
    if not raw:
        return None
    return get_workspace().projects_dir


def require_projects_root() -> Path:
    return get_workspace().projects_dir_strict()


def resolve_under_projects(path_str: str) -> Path:
    """Resolve a user path and reject escapes outside PROJECTS_DIR."""
    return get_workspace().resolve_under_projects(path_str)


def project_dir(project_id: str) -> Path:
    get_workspace().projects_dir_strict()
    return get_workspace().project_dir(project_id)


# Re-export for callers that imported errors from this module historically.
__all__ = [
    "ConfigError",
    "SandboxError",
    "projects_root",
    "require_projects_root",
    "resolve_under_projects",
    "project_dir",
]

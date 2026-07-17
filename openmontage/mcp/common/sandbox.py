"""Path sandbox: all project file access under OPENMONTAGE_PROJECTS_DIR."""

from __future__ import annotations

import os
from pathlib import Path

from openmontage.mcp.common.errors import ConfigError, SandboxError


def projects_root() -> Path | None:
    raw = os.environ.get("OPENMONTAGE_PROJECTS_DIR", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def require_projects_root() -> Path:
    root = projects_root()
    if root is None:
        raise ConfigError(
            "OPENMONTAGE_PROJECTS_DIR is not set. "
            "Read-only diagnosis still works via doctor/provider_menu_summary; "
            "project tools require a sandboxed projects root."
        )
    return root


def resolve_under_projects(path_str: str) -> Path:
    """Resolve a user path and reject escapes outside PROJECTS_DIR."""
    root = require_projects_root()
    candidate = Path(path_str).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SandboxError(
            f"Path escapes OPENMONTAGE_PROJECTS_DIR sandbox: {resolved}"
        ) from exc
    return resolved


def project_dir(project_id: str) -> Path:
    root = require_projects_root()
    if not project_id or "/" in project_id or "\\" in project_id or ".." in project_id:
        raise SandboxError(f"Invalid project_id: {project_id!r}")
    path = (root / project_id).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SandboxError(f"project_id escapes sandbox: {project_id!r}") from exc
    return path

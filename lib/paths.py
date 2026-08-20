"""Canonical repository paths — single source of truth.

The projects root is the most load-bearing path in the system: checkpoints
are written under it, tool events are attributed against it, and the Backlot
board watches it. Resolve it at call time, not at import time.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openmontage.mcp.common.errors import ConfigError, SandboxError

_ENV_PROJECTS = "OPENMONTAGE_PROJECTS_DIR"
_ENV_REPO = "OPENMONTAGE_REPO_ROOT"
_RELEASE_MANIFEST_REL = Path("distribution") / "manifests" / "release-manifest.json"
_MISSING_PROJECTS_DIR = (
    "OPENMONTAGE_PROJECTS_DIR is not set. "
    "Read-only diagnosis still works via doctor/provider_menu_summary; "
    "project tools require a sandboxed projects root."
)


def _checkout_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _discover_repo_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get(_ENV_REPO, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = _checkout_root()
    if (here / _RELEASE_MANIFEST_REL).is_file():
        return here
    raise RuntimeError(
        "OpenMontage repo root is unavailable: set OPENMONTAGE_REPO_ROOT "
        f"or keep {_RELEASE_MANIFEST_REL.as_posix()} next to the checkout"
    )


def _env_projects_dir() -> Path | None:
    raw = os.environ.get(_ENV_PROJECTS, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    repo_root: Path

    @classmethod
    def discover(cls, repo_root: Path | None = None) -> "WorkspacePaths":
        return cls(repo_root=_discover_repo_root(repo_root))

    @property
    def projects_dir(self) -> Path:
        env_dir = _env_projects_dir()
        if env_dir is not None:
            return env_dir
        return (self.repo_root / "projects").resolve()

    def projects_dir_strict(self) -> Path:
        env_dir = _env_projects_dir()
        if env_dir is None:
            raise ConfigError(_MISSING_PROJECTS_DIR)
        return env_dir

    def project_dir(
        self,
        project_id: str,
        *,
        must_exist: bool = False,
        require_marker: bool = False,
    ) -> Path:
        if not project_id or "/" in project_id or "\\" in project_id or ".." in project_id:
            raise SandboxError(f"Invalid project_id: {project_id!r}")
        root = self.projects_dir
        path = (root / project_id).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise SandboxError(f"project_id escapes sandbox: {project_id!r}") from exc
        if must_exist and not path.is_dir():
            raise SandboxError(f"project directory does not exist: {project_id!r}")
        if require_marker and not (path / "project.json").is_file():
            raise SandboxError(f"unknown project: {project_id!r}")
        return path

    def resolve_under_projects(self, path_str: str) -> Path:
        root = self.projects_dir_strict()
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

    @property
    def src_root(self) -> Path:
        return (self.repo_root / "src").resolve()

    @property
    def env_file(self) -> Path:
        return self.repo_root / ".env"

    @property
    def install_state_path(self) -> Path:
        return self.repo_root / ".openmontage" / "install-state.json"

    @property
    def backlot_dir(self) -> Path:
        return self.repo_root / ".backlot"


def ensure_import_roots(repo_root: Path | None = None) -> Path:
    """Put checkout ``src/`` first on ``sys.path``, then the repo root.

    After G5-D the ``openmontage`` package lives under ``src/``. A leftover
    ``openmontage/`` directory at repo root is only a shim and must not win.
    ``src/`` may be absent; inserting a missing directory is harmless.
    """
    root = Path(repo_root).expanduser().resolve() if repo_root is not None else get_workspace().repo_root
    src = (root / "src").resolve()
    root_s = str(root)
    src_s = str(src)
    if src_s in sys.path:
        sys.path.remove(src_s)
    sys.path.insert(0, src_s)
    if root_s not in sys.path:
        sys.path.append(root_s)
    return root


def get_workspace() -> WorkspacePaths:
    return WorkspacePaths.discover()


def get_projects_dir() -> Path:
    return get_workspace().projects_dir


class _LiveProjectsDir:
    """Path-like proxy so `from lib.paths import PROJECTS_DIR` re-reads env."""

    __slots__ = ()

    def _current(self) -> Path:
        return get_projects_dir()

    def __truediv__(self, other: Any) -> Path:
        return self._current() / other

    def __rtruediv__(self, other: Any) -> Path:
        return Path(other) / self._current()

    def __fspath__(self) -> str:
        return os.fspath(self._current())

    def __str__(self) -> str:
        return str(self._current())

    def __repr__(self) -> str:
        return f"PROJECTS_DIR({self._current()!s})"

    def __eq__(self, other: object) -> bool:
        return self._current() == other

    def __hash__(self) -> int:
        return hash(self._current())

    def __getattr__(self, name: str) -> Any:
        return getattr(self._current(), name)


# Compatible aliases. REPO_ROOT is the source checkout; projects dir is live.
REPO_ROOT = _checkout_root()
PROJECTS_DIR = _LiveProjectsDir()

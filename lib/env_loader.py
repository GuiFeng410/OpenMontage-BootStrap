"""Environment variable loader for OpenMontage.

Loads .env file and provides typed access to environment configuration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_env(project_root: Optional[Path] = None, *, override: bool = False) -> None:
    """Load .env from the workspace root. Missing keys only, unless override."""
    if project_root is None:
        from lib.paths import get_workspace

        project_root = get_workspace().repo_root
    env_path = Path(project_root) / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=override)


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get an environment variable with optional default."""
    return os.environ.get(key, default)


def require_env(key: str) -> str:
    """Get a required environment variable. Raises if missing."""
    value = os.environ.get(key)
    if value is None:
        raise EnvironmentError(f"Required environment variable {key!r} is not set")
    return value

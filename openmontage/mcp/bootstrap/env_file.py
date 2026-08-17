"""Ensure a local .env exists by copying the committed template."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from openmontage.mcp.common.errors import ConfigError

ENV_NAME = ".env"
EXAMPLE_NAME = ".env.example"


def ensure_env_file(
    *,
    repo_root: Path,
    dry_run: bool = True,
    confirm_execute: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    env_path = root / ENV_NAME
    example_path = root / EXAMPLE_NAME
    plan = {
        "action": "copy_env_example",
        "env_path": str(env_path),
        "example_path": str(example_path),
        "exists": env_path.is_file(),
        "example_exists": example_path.is_file(),
        "manual_commands": {
            "windows": f'Copy-Item "{example_path}" "{env_path}"',
            "posix": f'cp "{example_path}" "{env_path}"',
        },
    }
    if env_path.is_file():
        return {
            "dry_run": dry_run,
            "executed": False,
            "skipped": True,
            "reason": "env_already_exists",
            "plan": plan,
            "note_zh": "已有 .env，未覆盖。",
        }
    if not example_path.is_file():
        raise ConfigError(f"missing {EXAMPLE_NAME}; cannot create {ENV_NAME}")
    if dry_run:
        return {
            "dry_run": True,
            "executed": False,
            "skipped": False,
            "plan": plan,
            "note_zh": "将复制 .env.example 为 .env（Key 留空，不覆盖已有文件）。",
        }
    if not confirm_execute:
        raise ConfigError("confirm_execute required")
    shutil.copyfile(example_path, env_path)
    return {
        "dry_run": False,
        "executed": True,
        "skipped": False,
        "plan": plan,
        "note_zh": "已复制 .env.example 为 .env，Key 仍为空，填写后再重启 MCP。",
    }

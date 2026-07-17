"""Shared helpers to load OpenMontage BaseTools from the monorepo."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def ensure_repo_on_path() -> Path:
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return REPO_ROOT


def get_registry():
    ensure_repo_on_path()
    from tools.tool_registry import registry

    registry.discover()
    return registry


def get_tool(name: str):
    reg = get_registry()
    tool = getattr(reg, "_tools", {}).get(name)
    if tool is None:
        raise KeyError(name)
    return tool


def tool_result_to_dict(result: Any) -> dict[str, Any]:
    return {
        "success": bool(getattr(result, "success", False)),
        "data": getattr(result, "data", None),
        "artifacts": getattr(result, "artifacts", None),
        "error": getattr(result, "error", None),
        "cost_usd": getattr(result, "cost_usd", None),
        "duration_seconds": getattr(result, "duration_seconds", None),
        "seed": getattr(result, "seed", None),
        "model": getattr(result, "model", None),
    }

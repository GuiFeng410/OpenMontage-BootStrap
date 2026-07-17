"""Uniform JSON envelope for doctor MCP tools."""

from __future__ import annotations

from typing import Any

from openmontage.mcp.common.errors import DoctorError
from openmontage.mcp.common.version import version_fields


def ok(data: Any, *, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        **version_fields(),
        "data": data,
        "warnings": warnings or [],
        "error": None,
    }


def fail(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, DoctorError):
        payload = {"code": exc.code, "message": exc.message}
    else:
        payload = {"code": "internal_error", "message": str(exc)}
    return {
        "ok": False,
        **version_fields(),
        "data": None,
        "warnings": [],
        "error": payload,
    }

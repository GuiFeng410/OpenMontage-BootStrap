"""Shared version constants for MCP responses."""

from __future__ import annotations

from openmontage import __version__ as PACKAGE_VERSION
from openmontage.mcp import CONTRACT_VERSION

OPENMONTAGE_VERSION = PACKAGE_VERSION


def version_fields() -> dict[str, str]:
    return {
        "contract_version": CONTRACT_VERSION,
        "openmontage_version": OPENMONTAGE_VERSION,
    }

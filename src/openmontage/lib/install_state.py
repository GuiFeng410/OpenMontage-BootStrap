"""Facade over install-state helpers for lib callers."""

from openmontage.mcp.bootstrap.install_state import (
    count_existing_projects,
    read_install_state,
    scan_stock_keys,
    scan_video_keys,
    snapshot_install_state,
)

__all__ = [
    "count_existing_projects",
    "read_install_state",
    "scan_stock_keys",
    "scan_video_keys",
    "snapshot_install_state",
]

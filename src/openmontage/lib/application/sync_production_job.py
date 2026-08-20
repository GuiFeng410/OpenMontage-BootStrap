"""Load project marker and sync the local produce job. Does not import SDKs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lib.checkpoint import PROJECT_MARKER_FILENAME
from lib.paths import get_workspace
from lib.persistence.json_store import JsonStore
from lib.produce.orchestrator import sync_produce


def sync_production_job(
    project_id: str,
    *,
    compose_start: Callable[..., dict[str, Any]] | None = None,
    job_status: Callable[[str], dict[str, Any]] | None = None,
    video_generate: Callable[..., dict[str, Any]] | None = None,
    paid_inline: bool = False,
) -> dict[str, Any]:
    """Load marker from workspace, then call produce.orchestrator.sync_produce."""
    workspace = get_workspace()
    pdir = workspace.project_dir(project_id)
    try:
        marker = JsonStore.read_object(pdir / PROJECT_MARKER_FILENAME, missing="empty")
    except (OSError, ValueError):
        marker = {}
    if not isinstance(marker, dict):
        marker = {}
    return sync_produce(
        project_id,
        marker,
        projects_dir=workspace.projects_dir,
        compose_start=compose_start,
        job_status=job_status,
        video_generate=video_generate,
        paid_inline=paid_inline,
    )

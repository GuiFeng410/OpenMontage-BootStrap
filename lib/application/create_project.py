"""Create or resume a project under the workspace projects root."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from lib.application.errors import ApplicationError
from lib.checkpoint import PROJECT_MARKER_FILENAME, init_project
from lib.error_codes import (
    BAD_REQUEST,
    INVALID_PROJECT,
    NOT_FOUND,
    PIPELINE_MISMATCH,
    PROJECT_ID_EXHAUSTED,
)
from lib.paths import get_workspace

_CREATE_NEW = "create_new"
_RESUME = "resume"


def _allocate_fresh_project_id(requested_project_id: str) -> str:
    workspace = get_workspace()
    requested = workspace.project_dir(requested_project_id)
    if not requested.exists():
        return requested_project_id

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    for sequence in range(1, 10_000):
        candidate_id = f"{requested_project_id}-{stamp}-{sequence:02d}"
        if not workspace.project_dir(candidate_id).exists():
            return candidate_id
    raise ApplicationError(
        f"Could not allocate a unique project_id for {requested_project_id!r}",
        code=PROJECT_ID_EXHAUSTED,
    )


def _resume_project(
    *,
    requested_project_id: str,
    title: str,
    pipeline_type: str,
) -> dict[str, Any]:
    workspace = get_workspace()
    root = workspace.projects_dir
    target = workspace.project_dir(requested_project_id)
    marker_path = target / PROJECT_MARKER_FILENAME
    if not marker_path.is_file():
        raise ApplicationError(
            f"Project {requested_project_id!r} does not exist; resume requires an existing project.json",
            code=NOT_FOUND,
        )
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ApplicationError(
            f"Project {requested_project_id!r} has an unreadable project.json",
            code=INVALID_PROJECT,
        ) from exc
    if not isinstance(marker, dict):
        raise ApplicationError(
            f"Project {requested_project_id!r} has an unreadable project.json",
            code=INVALID_PROJECT,
        )
    existing_pipeline = marker.get("pipeline_type")
    if existing_pipeline and existing_pipeline != pipeline_type:
        raise ApplicationError(
            f"Project {requested_project_id!r} uses pipeline {existing_pipeline!r}, "
            f"not {pipeline_type!r}",
            code=PIPELINE_MISMATCH,
        )
    return {
        "project_id": requested_project_id,
        "requested_project_id": requested_project_id,
        "project_dir": str(target),
        "title": marker.get("title") or title,
        "pipeline_type": existing_pipeline or pipeline_type,
        "sandbox_root": str(root),
        "resolved": str(target),
        "mode": _RESUME,
        "created": False,
        "resumed": True,
        "conflict_avoided": False,
        "message_zh": "已明确续作现有项目；原检查点和生成物均保留。",
    }


def create_project(
    *,
    title: str,
    pipeline_type: str,
    mode: str = _CREATE_NEW,
    requested_project_id: str = "",
    review_mode: str = "",
    duration_seconds: int | None = None,
    asset_location: str = "",
) -> dict[str, Any]:
    """Create a new isolated project or resume an existing one. Does not spawn a runner."""
    _ = (review_mode, duration_seconds, asset_location)
    if mode not in {_CREATE_NEW, _RESUME}:
        raise ApplicationError(
            "mode must be create_new or resume",
            code=BAD_REQUEST,
        )
    requested = (requested_project_id or "").strip()
    if not requested:
        raise ApplicationError(
            "requested_project_id is required",
            code=BAD_REQUEST,
        )
    if mode == _RESUME:
        return _resume_project(
            requested_project_id=requested,
            title=title,
            pipeline_type=pipeline_type,
        )

    workspace = get_workspace()
    root = workspace.projects_dir
    project_id = _allocate_fresh_project_id(requested)
    path = init_project(
        project_id,
        title=title,
        pipeline_type=pipeline_type,
        pipeline_dir=root,
    )
    target = workspace.project_dir(project_id)
    return {
        "project_id": project_id,
        "requested_project_id": requested,
        "project_dir": str(path),
        "title": title,
        "pipeline_type": pipeline_type,
        "sandbox_root": str(root),
        "resolved": str(target),
        "mode": _CREATE_NEW,
        "created": True,
        "resumed": False,
        "conflict_avoided": project_id != requested,
        "message_zh": (
            f"检测到同名项目，已新建隔离项目 {project_id}；未继承旧检查点和生成物。"
            if project_id != requested
            else "已新建独立项目；未继承其它项目的检查点和生成物。"
        ),
    }

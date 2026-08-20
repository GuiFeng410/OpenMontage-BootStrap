"""Complete a gated stage with explicit approval text. Does not call generate."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lib.application.errors import ApplicationError
from lib.checkpoint import merge_write_checkpoint
from lib.error_codes import USER_CONFIRMATION_REQUIRED
from lib.paths import get_workspace

_STALE_METADATA_KEYS = (
    "decision_title_zh",
    "decision_context_zh",
    "decision_prompt_zh",
    "decision_options",
    "recommendation_zh",
    "examples_zh",
)

_EMPTY_APPROVAL = (
    "approve_checkpoint requires approval_text from the user's chat reply; "
    "MCP cannot invent approval."
)


def approve_stage(
    project_id: str,
    stage: str,
    approval_text: str,
    *,
    artifacts: dict[str, Any] | None = None,
    pipeline_type: str = "",
    metadata: dict[str, Any] | None = None,
    cost_snapshot: dict[str, Any] | None = None,
    metadata_remove_keys: tuple[str, ...] | None = None,
    human_approval_required: bool = True,
    record_approval_note: bool = True,
    project_marker_builder: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Empty approval_text is rejected. Writes completed+human_approved."""
    if not approval_text or not str(approval_text).strip():
        raise ApplicationError(_EMPTY_APPROVAL, code=USER_CONFIRMATION_REQUIRED)

    supplied_artifacts = artifacts if isinstance(artifacts, dict) else {}
    supplied_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    supplied_metadata["needs_user_decision"] = False
    if record_approval_note:
        supplied_metadata["approval_note"] = str(approval_text).strip()
    remove_keys = (
        metadata_remove_keys if metadata_remove_keys is not None else _STALE_METADATA_KEYS
    )
    root = get_workspace().projects_dir
    get_workspace().project_dir(project_id)
    path, written, marker_update = merge_write_checkpoint(
        root,
        project_id,
        stage,
        "completed",
        supplied_artifacts,
        pipeline_type=pipeline_type or None,
        human_approval_required=human_approval_required,
        human_approved=True,
        cost_snapshot_patch=cost_snapshot,
        metadata_patch=supplied_metadata,
        metadata_remove_keys=remove_keys,
        project_marker_builder=project_marker_builder,
    )
    artifacts_written = written["artifacts"]
    result: dict[str, Any] = {
        "checkpoint_path": str(path),
        "stage": stage,
        "status": "completed",
        "artifact_keys": sorted(artifacts_written.keys()),
        "materialized_hint_zh": "已写入 checkpoint，并尽量落盘 artifacts/*.json；请刷新看板核对。",
    }
    synced_profile = (
        marker_update.get("production_profile")
        if isinstance(marker_update, dict)
        else None
    )
    if synced_profile:
        result["production_profile"] = synced_profile
    return result

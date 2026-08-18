"""Seed commercial board stop cards for the local runner.

Does not call paid generate. Options are listed without a recommended badge.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lib.checkpoint import (
    CheckpointValidationError,
    merge_write_checkpoint,
    read_checkpoint,
)
from lib.paths import PROJECTS_DIR as DEFAULT_PROJECTS_DIR
from lib.review_interrupt import (
    COMMERCIAL_STAGE_ORDER,
    STAGE_LABEL_ZH,
    confirm_stop_ids,
    normalize_review_preset,
)

DECISION_STALE_KEYS = (
    "decision_title_zh",
    "decision_context_zh",
    "decision_prompt_zh",
    "decision_options",
    "recommendation_zh",
    "examples_zh",
)


def projects_root(projects_dir: Path | None = None) -> Path:
    if projects_dir is not None:
        return Path(projects_dir)
    return Path(os.environ.get("OPENMONTAGE_PROJECTS_DIR") or DEFAULT_PROJECTS_DIR)


PRODUCING_WAIT_ZH = (
    "素材已确认。成片尚未就绪，请留在本页等待制作。"
    "成片出现后即可在本页预览并导出。"
)


def primary_submit_label_zh(stage: str) -> str:
    if stage == "assets_gate":
        return "开始出片"
    return "进入下一步"


def final_video_ready(project_id: str, *, projects_dir: Path | None = None) -> bool:
    path = projects_root(projects_dir) / project_id / "renders" / "final.mp4"
    return path.is_file() and path.stat().st_size > 0


def stop_options(stage: str) -> list[dict[str, str]]:
    label = STAGE_LABEL_ZH.get(stage, stage)
    continue_label = primary_submit_label_zh(stage)
    if stage == "assets_gate":
        continue_desc = "确认素材无误后，按已锁定档位开始生成成片。"
    else:
        continue_desc = f"确认当前「{label}」内容，继续后面的步骤。"
    return [
        {
            "id": "continue",
            "label_zh": continue_label if stage == "assets_gate" else "同意，进入下一步",
            "description_zh": continue_desc,
        },
        {
            "id": "revise",
            "label_zh": "要修改后再继续",
            "description_zh": f"先改「{label}」，改完再进入下一步。",
        },
    ]


def stop_card_metadata(
    stage: str,
    project_id: str = "",
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    label = STAGE_LABEL_ZH.get(stage, stage)
    prompt = f"请确认「{label}」后进入下一步。"
    if stage == "assets_gate":
        prompt = "请确认素材后开始出片。成片将出现在交付确认页。"
    metadata: dict[str, Any] = {
        "needs_user_decision": True,
        "decision_title_zh": label,
        "decision_prompt_zh": prompt,
        "decision_options": stop_options(stage),
    }
    if stage == "delivery_signoff" and project_id:
        if not final_video_ready(project_id, projects_dir=projects_dir):
            return {
                "needs_user_decision": False,
                "producing_wait": True,
                "decision_title_zh": "制作中",
                "decision_prompt_zh": PRODUCING_WAIT_ZH,
                "decision_options": [],
            }
        metadata["decision_prompt_zh"] = (
            "成片已就绪，请在本页预览。确认后点「结束并导出项目」。"
        )
        metadata["decision_options"] = []
        metadata["needs_user_decision"] = False
    if stage == "brief_locked" and project_id:
        from lib.board_gap_plan import build_gap_snapshot

        snapshot = build_gap_snapshot(project_id, projects_dir=projects_dir)
        metadata["gap_plan"] = snapshot
        if snapshot.get("enough"):
            metadata["decision_prompt_zh"] = (
                "现有图片已覆盖各段所需画面。确认方案后进入素材检查。"
            )
        else:
            metadata["decision_prompt_zh"] = (
                "有画面缺口。请为每段选择：补传 / 图生图 / 复用 / 不补。"
                "选了图生图后全片共用一个生图模型；有多个 Key 时请点选。"
                "确认后锁定计划，本页不展示生成结果。"
            )
    return metadata


def strip_recommend(raw: Any) -> Any:
    if isinstance(raw, dict):
        cleaned = {
            key: strip_recommend(value)
            for key, value in raw.items()
            if key not in {"recommended", "recommendation_zh"}
        }
        return cleaned
    if isinstance(raw, list):
        return [strip_recommend(item) for item in raw]
    return raw


def _preset_from_marker(marker: dict[str, Any]) -> str | None:
    profile = marker.get("production_profile") if isinstance(marker, dict) else {}
    if not isinstance(profile, dict):
        profile = {}
    return normalize_review_preset(
        profile.get("review_mode_preset") or profile.get("review_mode")
    )


def _read_stage_checkpoint(
    root: Path,
    project_id: str,
    name: str,
    projects_dir: Path | None,
) -> dict[str, Any] | None:
    try:
        return read_checkpoint(root, project_id, name)
    except CheckpointValidationError:
        if name == "delivery_signoff" and not final_video_ready(
            project_id, projects_dir=projects_dir
        ):
            return {
                "status": "in_progress",
                "metadata": {"producing_wait": True},
            }
        raise


def _stage_rows(project_id: str, projects_dir: Path | None = None) -> list[dict[str, Any]]:
    root = projects_root(projects_dir)
    rows: list[dict[str, Any]] = []
    for name in COMMERCIAL_STAGE_ORDER:
        checkpoint = _read_stage_checkpoint(root, project_id, name, projects_dir)
        status = "pending"
        metadata: dict[str, Any] = {}
        if isinstance(checkpoint, dict):
            status = str(checkpoint.get("status") or "pending")
            maybe_meta = checkpoint.get("metadata")
            if isinstance(maybe_meta, dict):
                metadata = maybe_meta
        rows.append({"name": name, "status": status, "metadata": metadata})
    return rows


def _effective_stop_status(
    name: str,
    row: dict[str, Any],
    project_id: str,
    projects_dir: Path | None,
) -> str:
    status = str(row.get("status") or "pending")
    if (
        name == "delivery_signoff"
        and status == "completed"
        and not final_video_ready(project_id, projects_dir=projects_dir)
    ):
        return "in_progress"
    return status


def current_confirm_stop(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
) -> str | None:
    stops = confirm_stop_ids(_preset_from_marker(marker))
    by_name = {row["name"]: row for row in _stage_rows(project_id, projects_dir)}
    for name in stops:
        row = by_name.get(name) or {}
        if _effective_stop_status(name, row, project_id, projects_dir) != "completed":
            return name
    return None


def next_confirm_stop(
    project_id: str,
    marker: dict[str, Any],
    current: str,
    *,
    projects_dir: Path | None = None,
) -> str | None:
    stops = confirm_stop_ids(_preset_from_marker(marker))
    by_name = {row["name"]: row for row in _stage_rows(project_id, projects_dir)}
    passed = False
    for name in stops:
        if name == current:
            passed = True
            continue
        if not passed:
            continue
        row = by_name.get(name) or {}
        if _effective_stop_status(name, row, project_id, projects_dir) != "completed":
            return name
    return None


def _has_option_card(metadata: dict[str, Any]) -> bool:
    options = metadata.get("decision_options")
    return bool(metadata.get("needs_user_decision")) and isinstance(options, list) and bool(options)


def _approval_kwargs_from_checkpoint(current: dict[str, Any]) -> dict[str, bool]:
    """Preserve gate flags when patching metadata on an existing checkpoint."""
    return {
        "human_approval_required": bool(current.get("human_approval_required")),
        "human_approved": bool(current.get("human_approved")),
    }


def write_stop_card(
    project_id: str,
    stage: str,
    *,
    pipeline_type: str = "bootstrap-commercial",
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    root = projects_root(projects_dir)
    try:
        current = read_checkpoint(root, project_id, stage) or {}
    except CheckpointValidationError:
        if stage == "delivery_signoff" and not final_video_ready(
            project_id, projects_dir=projects_dir
        ):
            stale = root / project_id / f"checkpoint_{stage}.json"
            stale.unlink(missing_ok=True)
            current = {}
        else:
            raise
    status = str(current.get("status") or "in_progress")
    if status in {"", "pending"}:
        status = "in_progress"
    metadata = strip_recommend(
        stop_card_metadata(stage, project_id, projects_dir=projects_dir)
    )
    write_kwargs = {
        "pipeline_type": str(current.get("pipeline_type") or pipeline_type),
        "metadata_patch": metadata,
        "metadata_remove_keys": (
            "recommendation_zh",
            "examples_zh",
            "minimal_plan_signoff",
        ),
        **_approval_kwargs_from_checkpoint(current),
    }
    if status == "completed":
        if stage == "delivery_signoff" and not final_video_ready(
            project_id, projects_dir=projects_dir
        ):
            status = "in_progress"
        else:
            return {
                "path": str(root / project_id / f"checkpoint_{stage}.json"),
                "stage": stage,
                "status": "completed",
                "skipped": True,
            }
    try:
        path, written, _marker = merge_write_checkpoint(
            root, project_id, stage, status, {}, **write_kwargs
        )
    except CheckpointValidationError:
        write_board_stop_overlay(
            project_id, stage, projects_dir=projects_dir
        )
        return {
            "path": str(root / project_id / "project.json"),
            "stage": stage,
            "status": "overlay",
            "skipped": True,
        }
    write_board_stop_overlay(project_id, stage, projects_dir=projects_dir)
    return {"path": str(path), "stage": stage, "status": written.get("status")}


def clear_stop_card(
    project_id: str,
    stage: str,
    *,
    pipeline_type: str = "bootstrap-commercial",
    projects_dir: Path | None = None,
) -> None:
    root = projects_root(projects_dir)
    current = read_checkpoint(root, project_id, stage)
    if not isinstance(current, dict):
        return
    status = str(current.get("status") or "in_progress")
    if status == "awaiting_human":
        status = "in_progress"
    merge_write_checkpoint(
        root,
        project_id,
        stage,
        status,
        {},
        pipeline_type=str(current.get("pipeline_type") or pipeline_type),
        metadata_patch={"needs_user_decision": False},
        metadata_remove_keys=DECISION_STALE_KEYS,
        **_approval_kwargs_from_checkpoint(current),
    )


def ensure_current_stop_card(
    project_id: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
) -> str | None:
    stage = current_confirm_stop(project_id, marker, projects_dir=projects_dir)
    if not stage:
        return None
    try:
        current = read_checkpoint(projects_root(projects_dir), project_id, stage) or {}
    except CheckpointValidationError:
        current = {}
    metadata = current.get("metadata") if isinstance(current.get("metadata"), dict) else {}
    if _has_option_card(metadata) and "recommendation_zh" not in metadata:
        options = metadata.get("decision_options")
        if isinstance(options, list) and not any(
            isinstance(item, dict) and item.get("recommended") for item in options
        ):
            write_board_stop_overlay(
                project_id, stage, projects_dir=projects_dir
            )
            return stage
    write_stop_card(
        project_id,
        stage,
        pipeline_type=str(
            current.get("pipeline_type")
            or marker.get("pipeline_type")
            or "bootstrap-commercial"
        ),
        projects_dir=projects_dir,
    )
    return stage


def advance_after_apply(
    project_id: str,
    applied_stage: str,
    marker: dict[str, Any],
    *,
    projects_dir: Path | None = None,
) -> str | None:
    pipeline_type = str(marker.get("pipeline_type") or "bootstrap-commercial")
    clear_stop_card(
        project_id,
        applied_stage,
        pipeline_type=pipeline_type,
        projects_dir=projects_dir,
    )
    nxt = next_confirm_stop(
        project_id, marker, applied_stage, projects_dir=projects_dir
    )
    if not nxt:
        clear_board_stop_overlay(project_id, projects_dir=projects_dir)
        return None
    write_stop_card(
        project_id,
        nxt,
        pipeline_type=pipeline_type,
        projects_dir=projects_dir,
    )
    return nxt


def write_board_stop_overlay(
    project_id: str,
    stage: str,
    *,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    path = projects_root(projects_dir) / project_id / "project.json"
    data = read_marker(project_id, projects_dir=projects_dir)
    data["board_stop"] = {
        "stage": stage,
        **strip_recommend(
            stop_card_metadata(stage, project_id, projects_dir=projects_dir)
        ),
    }
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return data["board_stop"]


def clear_board_stop_overlay(
    project_id: str,
    *,
    projects_dir: Path | None = None,
) -> None:
    path = projects_root(projects_dir) / project_id / "project.json"
    data = read_marker(project_id, projects_dir=projects_dir)
    if "board_stop" not in data:
        return
    data.pop("board_stop", None)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_marker(project_id: str, *, projects_dir: Path | None = None) -> dict[str, Any]:
    path = projects_root(projects_dir) / project_id / "project.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}

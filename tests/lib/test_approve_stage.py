"""approve_stage use case: empty text rejected; completed lands on snapshot."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.application.approve_stage import approve_stage
from lib.application.create_project import create_project
from lib.application.errors import ApplicationError
from lib.application.read_project_snapshot import read_project_snapshot
from lib.error_codes import USER_CONFIRMATION_REQUIRED


def _brief_locked_artifacts() -> dict:
    return {
        "brief": {
            "theme": "审批测商品片",
            "duration_seconds": 15,
            "images": {},
        },
        "asset_precheck": {
            "version": "1.0",
            "entries": [],
            "summary": {
                "total_images": 0,
                "low_resolution_count": 0,
                "duplicate_group_count": 0,
                "needs_user_attention": True,
            },
        },
        "video_plan": {
            "segments": [{"id": "beat_01", "t": "0-5", "method": "camera_move"}]
        },
        "segment_cards": {
            "version": "1.0",
            "duration_seconds": 5,
            "overall_prompt_zh": "开场→细节→收尾",
            "segments": [
                {
                    "beat": "b1",
                    "time": "0-5",
                    "copy_plan_zh": "亮相",
                    "shot_plan_zh": "缓慢推进",
                    "asset_plan_zh": "使用商品主图",
                }
            ],
        },
    }


def test_empty_approval_text_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    create_project(
        title="Empty Approve",
        pipeline_type="bootstrap-commercial",
        requested_project_id="empty-approve",
    )
    with pytest.raises(ApplicationError) as caught:
        approve_stage("empty-approve", "brief_locked", "   ")
    assert caught.value.code == USER_CONFIRMATION_REQUIRED
    assert "approval_text" in caught.value.message


def test_approve_marks_stage_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects = tmp_path / "projects"
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(projects))
    create_project(
        title="Approve Light",
        pipeline_type="bootstrap-commercial",
        requested_project_id="approve-light",
    )
    result = approve_stage(
        "approve-light",
        "brief_locked",
        "用户确认方案",
        artifacts=_brief_locked_artifacts(),
        pipeline_type="bootstrap-commercial",
    )
    assert result["status"] == "completed"
    assert result["stage"] == "brief_locked"
    snapshot = read_project_snapshot("approve-light")
    assert "brief_locked" in snapshot["completed_stages"]
    assert snapshot["latest_checkpoint_status"] == "completed"

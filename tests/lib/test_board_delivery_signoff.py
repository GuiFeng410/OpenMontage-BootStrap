"""Minimal delivery signoff without final video."""

from __future__ import annotations

import json
from pathlib import Path

from lib.board_delivery_signoff import DeliverySignoffError, seal_delivery_signoff_minimal


def _write_project(root: Path) -> Path:
    project = root / "shop-demo"
    (project / "artifacts").mkdir(parents=True)
    (project / "decision_log.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": "shop-demo",
                "decisions": [
                    {
                        "decision_id": "test-1",
                        "stage": "brief_locked",
                        "category": "approval_policy",
                        "subject": "Commercial fast-track production",
                        "options_considered": [
                            {
                                "option_id": "fast_track_v2",
                                "label": "快速模式",
                                "score": 1.0,
                                "reason": "test",
                            }
                        ],
                        "selected": "fast_track_v2",
                        "reason": "test",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project / "artifacts" / "asset_ledger.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": "shop-demo",
                "entries": [],
                "summary": {"status_zh": "就绪"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project / "project.json").write_text(
        json.dumps(
            {
                "project_id": "shop-demo",
                "pipeline_type": "bootstrap-commercial",
                "production_profile": {"review_mode_preset": "minimal"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project / "checkpoint_brief_locked.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": "shop-demo",
                "pipeline_type": "bootstrap-commercial",
                "stage": "brief_locked",
                "status": "completed",
                "artifacts": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project / "checkpoint_assets_gate.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": "shop-demo",
                "pipeline_type": "bootstrap-commercial",
                "stage": "assets_gate",
                "status": "completed",
                "artifacts": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project


def test_seal_delivery_signoff_minimal_requires_final(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    _write_project(root)
    try:
        seal_delivery_signoff_minimal("shop-demo", projects_dir=root)
        raise AssertionError("expected DeliverySignoffError")
    except DeliverySignoffError as exc:
        assert exc.code == "final_video_required"


def test_minimal_plan_signoff_metadata_cannot_complete_without_video(
    tmp_path: Path,
) -> None:
    from lib.checkpoint import CheckpointValidationError, validate_checkpoint

    project = tmp_path / "shop-demo"
    project.mkdir()
    try:
        validate_checkpoint(
            {
                "version": "1.0",
                "project_id": "shop-demo",
                "pipeline_type": "bootstrap-commercial",
                "stage": "delivery_signoff",
                "status": "completed",
                "timestamp": "2026-08-11T00:00:00+00:00",
                "checkpoint_policy": "guided",
                "human_approval_required": False,
                "human_approved": True,
                "artifacts": {},
                "metadata": {"minimal_plan_signoff": True},
            },
            project_dir=project,
        )
        raise AssertionError("expected CheckpointValidationError")
    except CheckpointValidationError:
        pass

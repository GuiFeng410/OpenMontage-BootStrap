"""Tests for checkpoint artifact merge + materialize."""

from __future__ import annotations

import json
from pathlib import Path

from lib.checkpoint import (
    _materialize_artifacts,
    merge_checkpoint_artifacts,
    write_checkpoint,
)


def test_merge_checkpoint_artifacts_keeps_prior_keys():
    merged = merge_checkpoint_artifacts(
        {"brief": {"theme": "A"}, "video_plan": {"segments": [1]}},
        {"asset_ledger": {"entries": []}},
    )
    assert "brief" in merged
    assert "video_plan" in merged
    assert "asset_ledger" in merged


def test_write_checkpoint_materializes_artifacts_json(tmp_path: Path):
    project_id = "seal-demo"
    (tmp_path / project_id).mkdir()
    (tmp_path / project_id / "project.json").write_text(
        json.dumps({"pipeline_type": "bootstrap-commercial", "title": "t"}),
        encoding="utf-8",
    )
    artifacts = {
        "brief": {
            "theme": "银手镯",
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
        "video_plan": {"segments": [{"id": "beat_01", "t": "0-5", "method": "camera_move"}]},
        "segment_cards": {
            "overall_prompt_zh": "开场→细节→收尾",
            "segments": [{"beat": "b1", "copy_plan_zh": "亮相"}],
        },
    }
    write_checkpoint(
        tmp_path,
        project_id,
        "brief_locked",
        "awaiting_human",
        artifacts,
        pipeline_type="bootstrap-commercial",
        human_approval_required=True,
    )
    art = tmp_path / project_id / "artifacts"
    assert (art / "brief.json").exists()
    assert (art / "video_plan.json").exists()
    assert (art / "segment_cards.json").exists()
    brief = json.loads((art / "brief.json").read_text(encoding="utf-8"))
    assert brief["theme"] == "银手镯"


def test_materialize_skips_path_strings(tmp_path: Path):
    written = _materialize_artifacts(
        tmp_path,
        {"brief": {"ok": True}, "video_plan": "artifacts/video_plan.json"},
    )
    assert written == ["brief"]
    assert (tmp_path / "artifacts" / "brief.json").exists()

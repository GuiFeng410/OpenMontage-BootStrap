"""Resume must reuse on-disk segments even if review_overview was wiped to B01."""

from __future__ import annotations

import json
from pathlib import Path

from lib.board_stage_artifacts import build_review_overview
from lib.produce.compose_adapter import _matching_segment_rel, _seg_rel


def test_matching_segment_falls_back_to_disk_when_overview_only_has_first_beat(
    tmp_path: Path,
) -> None:
    revision = "sha256:deadbeef"
    video_dir = tmp_path / "assets" / "video"
    video_dir.mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    b01 = _seg_rel("B01", revision)
    b02 = _seg_rel("B02", revision)
    (tmp_path / b01).write_bytes(b"segment-one")
    (tmp_path / b02).write_bytes(b"segment-two")

    overview = build_review_overview(
        [
            {
                "beat": "B01",
                "output_path": b01,
                "status": "completed",
                "artifact_revision": revision,
                "provider": "agnes",
                "model": "agnes-video-v2.0",
            }
        ],
        batches=[],
        extra={
            "artifact_revision": revision,
            "provider": "agnes",
            "model": "agnes-video-v2.0",
            "status": "in_progress",
        },
    )
    (artifacts / "review_overview.json").write_text(
        json.dumps(overview, ensure_ascii=False),
        encoding="utf-8",
    )

    assert _matching_segment_rel(tmp_path, "B01", revision) == b01
    assert _matching_segment_rel(tmp_path, "B02", revision) == b02
    assert _matching_segment_rel(tmp_path, "B03", revision) == ""

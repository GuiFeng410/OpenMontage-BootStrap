"""Unit tests for draft-review reject / suggestions helpers."""

from __future__ import annotations

import json
from pathlib import Path

from lib.board_draft_review import (
    apply_draft_approve,
    apply_draft_reject,
    draft_is_rejected,
    suggestions_from_note,
)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_suggestions_from_note_empty_and_keyword(tmp_path: Path) -> None:
    empty = suggestions_from_note("")
    assert empty
    assert any("分段" in tip or "预览" in tip for tip in empty)

    blur = suggestions_from_note("画面太模糊了")
    assert any("画质" in tip or "重做" in tip for tip in blur)


def test_apply_draft_reject_and_approve(tmp_path: Path) -> None:
    project_id = "draft-review-demo"
    project = tmp_path / project_id
    video = project / "assets" / "video" / "seg_B01.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"fake-mp4")
    _write(
        project / "artifacts" / "full_draft_pro.json",
        {
            "version": "1.0",
            "path": "assets/video/seg_B01.mp4",
            "issue_segments": [],
            "modification_list": [],
            "status": "pending",
        },
    )
    _write(
        project / "artifacts" / "review_overview.json",
        {
            "overview": [
                {"beat": "B01", "output_path": "assets/video/seg_B01.mp4", "status": "ok"},
            ]
        },
    )

    rejected = apply_draft_reject(
        project_id,
        {"payload": {"note": "节奏偏慢", "selections": []}},
        projects_dir=tmp_path,
    )
    assert rejected["status"] == "rejected"
    assert draft_is_rejected(project_id, projects_dir=tmp_path)
    assert rejected.get("suggestions_zh")

    approved = apply_draft_approve(project_id, projects_dir=tmp_path)
    assert approved["status"] == "approved"
    assert approved.get("approved") is True
    assert not draft_is_rejected(project_id, projects_dir=tmp_path)

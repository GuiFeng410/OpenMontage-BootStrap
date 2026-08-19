"""Auto-seal assets_gate for closed user-upload video plans."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from lib.board_assets_gate import build_asset_ledger_from_plan, seal_assets_gate
from lib.checkpoint import read_checkpoint


def _write_project(root: Path) -> Path:
    project = root / "shop-demo"
    (project / "artifacts").mkdir(parents=True)
    (project / "assets" / "images").mkdir(parents=True)
    for name in ("001.png", "002.png"):
        Image.new("RGB", (800, 800), (200, 200, 200)).save(
            project / "assets" / "images" / name
        )
    (project / "project.json").write_text(
        json.dumps(
            {
                "project_id": "shop-demo",
                "title": "手链",
                "pipeline_type": "bootstrap-commercial",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project / "artifacts" / "video_plan.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "segments": [
                    {
                        "id": "B01",
                        "beat": "B01",
                        "gap_fill": "user_upload",
                        "assignment_status": "assigned",
                        "ref_image": "assets/images/001.png",
                    },
                    {
                        "id": "B02",
                        "beat": "B02",
                        "gap_fill": "user_upload",
                        "assignment_status": "assigned",
                        "ref_image": "assets/images/002.png",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project / "artifacts" / "segment_cards.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "duration_seconds": 20,
                "overall_prompt_zh": "测试",
                "segments": [
                    {
                        "beat": "B01",
                        "time": "0-10s",
                        "copy_plan_zh": "a",
                        "shot_plan_zh": "b",
                        "asset_plan_zh": "c",
                    },
                    {
                        "beat": "B02",
                        "time": "10-20s",
                        "copy_plan_zh": "a",
                        "shot_plan_zh": "b",
                        "asset_plan_zh": "c",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project / "artifacts" / "asset_precheck.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "entries": [
                    {
                        "file": "001.png",
                        "path": "assets/images/001.png",
                        "width": 800,
                        "height": 800,
                        "bytes": 100,
                        "suggested_class": "product",
                        "issues": [],
                    },
                    {
                        "file": "002.png",
                        "path": "assets/images/002.png",
                        "width": 800,
                        "height": 800,
                        "bytes": 100,
                        "suggested_class": "product",
                        "issues": [],
                    },
                ],
                "summary": {
                    "total_images": 2,
                    "low_resolution_count": 0,
                    "duplicate_group_count": 0,
                    "needs_user_attention": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project / "artifacts" / "brief.json").write_text(
        json.dumps({"theme": "手链", "duration_seconds": 20, "images": {}}),
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
                "human_approval_required": True,
                "human_approved": True,
                "artifacts": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project


def test_build_asset_ledger_from_plan(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    ledger = build_asset_ledger_from_plan("shop-demo", projects_dir=root)
    assert len(ledger["entries"]) == 2
    assert ledger["entries"][0]["beats"] == ["B01"]


def test_build_asset_ledger_marks_extra_upload_unused(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = _write_project(root)
    Image.new("RGB", (800, 800), (180, 180, 180)).save(
        project / "assets" / "images" / "003.png"
    )
    ledger = build_asset_ledger_from_plan("shop-demo", projects_dir=root)
    unused = [item for item in ledger["entries"] if item.get("selected") is False]
    used = [item for item in ledger["entries"] if item.get("selected") is not False]
    assert [item["path"] for item in used] == [
        "assets/images/001.png",
        "assets/images/002.png",
    ]
    assert [item["path"] for item in unused] == ["assets/images/003.png"]
    assert unused[0]["note_zh"]
    assert unused[0]["reason"] == "extra_unassigned_upload"
    assert "beats" not in unused[0]
    assert ledger["summary"]["available_image_count"] == 2


def test_seal_assets_gate_writes_checkpoint(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    seal_assets_gate("shop-demo", projects_dir=root)
    checkpoint = read_checkpoint(root, "shop-demo", "assets_gate")
    assert checkpoint["status"] == "completed"
    assert (root / "shop-demo" / "artifacts" / "asset_ledger.json").is_file()


def test_seal_assets_gate_completes_with_extra_unassigned_upload(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = _write_project(root)
    Image.new("RGB", (800, 800), (180, 180, 180)).save(
        project / "assets" / "images" / "003.png"
    )
    seal_assets_gate("shop-demo", projects_dir=root)
    checkpoint = read_checkpoint(root, "shop-demo", "assets_gate")
    assert checkpoint["status"] == "completed"
    ledger = json.loads(
        (project / "artifacts" / "asset_ledger.json").read_text(encoding="utf-8")
    )
    unused = [item for item in ledger["entries"] if item.get("selected") is False]
    assert [item["path"] for item in unused] == ["assets/images/003.png"]

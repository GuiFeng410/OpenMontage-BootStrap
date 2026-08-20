"""assets_gate i2i generate + review + seal. Uses a fake generate, never paid APIs."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from lib.board_advance import stop_card_metadata, stop_options
from lib.board_assets_gate import AssetsGateError, seal_assets_gate
from lib.board_i2i import approve_pending_i2i, i2i_mode, run_i2i_generate
from lib.checkpoint import read_checkpoint


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (640, 640), (180, 40, 40)).save(path)


def _write_mixed_project(root: Path) -> Path:
    project = root / "shop-i2i"
    art = project / "artifacts"
    art.mkdir(parents=True)
    _png(project / "assets" / "images" / "001.png")
    (project / "project.json").write_text(
        json.dumps(
            {
                "project_id": "shop-i2i",
                "title": "手链",
                "pipeline_type": "bootstrap-commercial",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (art / "video_plan.json").write_text(
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
                        "gap_fill": "i2i",
                        "assignment_status": "i2i_planned",
                        "asset_source": "i2i",
                        "provider": "agnes",
                        "model": "agnes",
                        "planned_output_path": "assets/images/i2i_B02.png",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (art / "segment_cards.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "duration_seconds": 10,
                "overall_prompt_zh": "测试",
                "segments": [
                    {
                        "beat": "B01",
                        "time": "0-5s",
                        "copy_plan_zh": "正面",
                        "shot_plan_zh": "中景",
                        "asset_plan_zh": "用户图",
                    },
                    {
                        "beat": "B02",
                        "time": "5-10s",
                        "copy_plan_zh": "侧面结构",
                        "shot_plan_zh": "侧光",
                        "asset_plan_zh": "图生图",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (art / "asset_precheck.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "entries": [
                    {
                        "file": "001.png",
                        "path": "assets/images/001.png",
                        "width": 640,
                        "height": 640,
                        "bytes": 100,
                        "suggested_class": "product_hero",
                        "issues": [],
                    }
                ],
                "summary": {
                    "total_images": 1,
                    "low_resolution_count": 0,
                    "duplicate_group_count": 0,
                    "needs_user_attention": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (art / "gap_plan.json").write_text(
        json.dumps({"version": "1.0", "enough": False, "locked": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (art / "brief.json").write_text(
        json.dumps({"theme": "手链", "duration_seconds": 10, "images": {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project / "checkpoint_brief_locked.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": "shop-i2i",
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


def _fake_generate(_provider, _prompt, output_path, _extras):
    dest = Path(output_path)
    _png(dest)
    return {"success": True, "output_path": str(dest)}


def test_seal_rejects_i2i_planned(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_mixed_project(root)
    try:
        seal_assets_gate("shop-i2i", projects_dir=root)
        raise AssertionError("should refuse open i2i")
    except AssetsGateError as exc:
        assert exc.code == "i2i_not_closed"


def test_generate_then_approve_then_seal(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = _write_mixed_project(root)
    assert i2i_mode(project) == "i2i_planned"

    generated = run_i2i_generate(
        "shop-i2i",
        projects_dir=root,
        generate=_fake_generate,
    )
    assert generated["paths"] == ["assets/images/i2i_B02.png"]
    assert (project / "assets" / "images" / "i2i_B02.png").is_file()
    plan = json.loads((project / "artifacts" / "video_plan.json").read_text(encoding="utf-8"))
    assert plan["segments"][1]["assignment_status"] == "i2i_review_pending"
    assert "ref_image" not in plan["segments"][1]
    assert i2i_mode(project) == "i2i_review"
    review_opts = stop_options("assets_gate", "shop-i2i", projects_dir=root)
    assert review_opts[0]["id"] == "continue"
    assert "通过这些补图" in review_opts[0]["label_zh"]
    try:
        seal_assets_gate("shop-i2i", projects_dir=root)
        raise AssertionError("should refuse unreviewed i2i")
    except AssetsGateError as exc:
        assert exc.code == "i2i_not_closed"

    approved = approve_pending_i2i("shop-i2i", projects_dir=root)
    assert approved["action"] == "approved"
    plan = json.loads((project / "artifacts" / "video_plan.json").read_text(encoding="utf-8"))
    assert plan["segments"][1]["ref_image"] == "assets/images/i2i_B02.png"
    assert plan["segments"][1]["assignment_status"] == "assigned"

    result = seal_assets_gate("shop-i2i", projects_dir=root)
    assert result["action"] == "continue"
    checkpoint = read_checkpoint(root, "shop-i2i", "assets_gate")
    assert checkpoint["status"] == "completed"
    ledger = json.loads((project / "artifacts" / "asset_ledger.json").read_text(encoding="utf-8"))
    i2i_rows = [item for item in ledger["entries"] if item.get("origin") == "i2i"]
    assert len(i2i_rows) == 1
    assert i2i_rows[0]["review_status"] == "approved"
    log = json.loads((project / "decision_log.json").read_text(encoding="utf-8"))
    assert log["decisions"][0]["selected"] == "approved"


def test_stop_options_show_generate_when_i2i_planned(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_mixed_project(root)
    options = stop_options("assets_gate", "shop-i2i", projects_dir=root)
    assert options[0]["id"] == "generate"
    assert options[0]["label_zh"] == "开始生成补图"
    assert all(item["id"] != "continue" for item in options)
    meta = stop_card_metadata("assets_gate", "shop-i2i", projects_dir=root)
    assert "先生成" in meta["decision_prompt_zh"]
    assert meta["decision_options"][0]["id"] == "generate"

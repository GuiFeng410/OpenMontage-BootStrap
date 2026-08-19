"""Board stop cards list options without a recommended badge."""

from __future__ import annotations

import json
from pathlib import Path

from lib.board_advance import (
    advance_after_apply,
    ensure_current_stop_card,
    stop_card_metadata,
    stop_options,
    strip_recommend,
    write_stop_card,
)
from lib.checkpoint import read_checkpoint


def _write_project(root: Path, project_id: str = "shop-demo") -> dict:
    project = root / project_id
    project.mkdir(parents=True)
    marker = {
        "project_id": project_id,
        "title": "Shop",
        "pipeline_type": "bootstrap-commercial",
        "production_profile": {
            "review_mode_preset": "minimal",
            "production_tier": "light",
        },
    }
    (project / "project.json").write_text(
        json.dumps(marker, ensure_ascii=False),
        encoding="utf-8",
    )
    return marker


def test_stop_options_have_no_recommend() -> None:
    options = stop_options("brief_locked")
    assert [item["id"] for item in options] == ["continue", "revise"]
    assert all("recommended" not in item for item in options)
    assets = stop_options("assets_gate")
    assert assets[0]["label_zh"] == "开始出片"


def test_delivery_without_final_is_producing_wait(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    meta = stop_card_metadata(
        "delivery_signoff", "shop-demo", projects_dir=root
    )
    assert meta["producing_wait"] is True
    assert meta["needs_user_decision"] is False
    assert meta["decision_options"] == []
    assert "1–3 分钟" in meta["decision_prompt_zh"]


def test_delivery_without_final_heavy_uses_range_not_light_wait(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    project = root / "shop-demo"
    marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
    marker["production_profile"]["production_tier"] = "heavy"
    (project / "project.json").write_text(
        json.dumps(marker, ensure_ascii=False), encoding="utf-8"
    )
    (project / "artifacts").mkdir(parents=True, exist_ok=True)
    (project / "artifacts" / "video_plan.json").write_text(
        json.dumps(
            {"segments": [{"id": "a"}, {"id": "b"}, {"id": "c"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    meta = stop_card_metadata(
        "delivery_signoff", "shop-demo", projects_dir=root
    )
    assert meta["producing_wait"] is True
    assert "重度" in meta["decision_prompt_zh"]
    assert "分钟" in meta["decision_prompt_zh"]
    assert "1–3 分钟" not in meta["decision_prompt_zh"]


def test_delivery_with_final_is_preview_not_continue(tmp_path: Path) -> None:
    from lib.board_advance import DELIVERY_READY_ZH, open_delivery_preview

    root = tmp_path / "projects"
    _write_project(root)
    renders = root / "shop-demo" / "renders"
    renders.mkdir()
    (renders / "final.mp4").write_bytes(b"film")
    meta = stop_card_metadata(
        "delivery_signoff", "shop-demo", projects_dir=root
    )
    assert meta.get("producing_wait") is not True
    assert meta["needs_user_decision"] is False
    assert meta["decision_options"] == []
    assert "结束并导出" in meta["decision_prompt_zh"]
    opened = open_delivery_preview("shop-demo", projects_dir=root)
    assert opened["ok"] is True
    overlay = json.loads(
        (root / "shop-demo" / "project.json").read_text(encoding="utf-8")
    )["board_stop"]
    assert overlay["stage"] == "delivery_signoff"
    assert overlay.get("producing_wait") is not True
    assert DELIVERY_READY_ZH in overlay["decision_prompt_zh"]


def test_sample_stop_without_real_evidence_is_paused(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)

    meta = stop_card_metadata("sample_review", "shop-demo", projects_dir=root)

    assert meta["paused"] is True
    assert meta["producing_wait"] is False
    assert meta["needs_user_decision"] is False
    assert meta["decision_options"] == []
    assert "未创建制作任务" in meta["decision_prompt_zh"]
    assert "没有调用视频模型" in meta["decision_prompt_zh"]


def test_sample_stop_requires_canonical_video_and_beat_ids(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = root / "shop-demo"
    _write_project(root)
    (project / "artifacts").mkdir()
    (project / "assets" / "video").mkdir(parents=True)
    (project / "assets" / "video" / "sample.mp4").write_bytes(b"film")
    (project / "artifacts" / "sample_reel.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "path": "assets/video/sample.mp4",
                "beat_ids": ["beat_01"],
                "status": "pending",
            }
        ),
        encoding="utf-8",
    )

    meta = stop_card_metadata("sample_review", "shop-demo", projects_dir=root)

    assert meta.get("paused") is not True
    assert meta["needs_user_decision"] is True
    assert meta["decision_options"]


def test_strip_recommend_drops_badge_fields() -> None:
    cleaned = strip_recommend(
        {
            "recommendation_zh": "推荐重度",
            "options": [{"id": "heavy", "recommended": True, "label_zh": "重度"}],
        }
    )
    assert "recommendation_zh" not in cleaned
    assert "recommended" not in cleaned["options"][0]
    assert cleaned["options"][0]["label_zh"] == "重度"


def test_ensure_current_stop_card_has_no_recommend(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    stage = ensure_current_stop_card("shop-demo", marker, projects_dir=root)
    assert stage == "brief_locked"
    checkpoint = read_checkpoint(root, "shop-demo", "brief_locked")
    meta = checkpoint["metadata"]
    assert meta["needs_user_decision"] is True
    assert "recommendation_zh" not in meta
    assert all("recommended" not in item for item in meta["decision_options"])
    assert checkpoint["status"] == "in_progress"


def test_advance_writes_next_stop_without_completing_prior(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    write_stop_card("shop-demo", "brief_locked", projects_dir=root)
    nxt = advance_after_apply(
        "shop-demo",
        "brief_locked",
        marker,
        projects_dir=root,
    )
    assert nxt == "assets_gate"
    brief = read_checkpoint(root, "shop-demo", "brief_locked")
    assert brief["metadata"].get("needs_user_decision") is False
    assert "decision_options" not in brief["metadata"]
    assert read_checkpoint(root, "shop-demo", "assets_gate") is None
    overlay = json.loads(
        (root / "shop-demo" / "project.json").read_text(encoding="utf-8")
    )["board_stop"]
    assert overlay["stage"] == "assets_gate"
    assert overlay["needs_user_decision"] is True
    assert overlay["decision_options"][0]["label_zh"] == "开始出片"
    assert "recommendation_zh" not in overlay
    assert all("recommended" not in item for item in overlay["decision_options"])


def test_advance_after_completed_brief_locked_preserves_human_approved(
    tmp_path: Path,
) -> None:
    """clear_stop_card must not reset human_approved on a completed gate stage."""
    from lib.checkpoint import merge_write_checkpoint

    root = tmp_path / "projects"
    marker = _write_project(root)
    artifacts = {
        "brief": {"theme": "手链", "duration_seconds": 25, "images": {}},
        "asset_precheck": {
            "version": "1.0",
            "entries": [],
            "summary": {
                "total_images": 1,
                "low_resolution_count": 0,
                "duplicate_group_count": 0,
                "needs_user_attention": False,
            },
        },
        "video_plan": {"segments": [{"id": "beat_01", "t": "0-10"}]},
        "segment_cards": {
            "version": "1.0",
            "duration_seconds": 25,
            "overall_prompt_zh": "商品片",
            "segments": [
                {
                    "beat": "beat_01",
                    "time": "00:00-00:10",
                    "copy_plan_zh": "卖点",
                    "shot_plan_zh": "推镜",
                    "asset_plan_zh": "主图",
                }
            ],
        },
    }
    merge_write_checkpoint(
        root,
        "shop-demo",
        "brief_locked",
        "completed",
        artifacts,
        pipeline_type="bootstrap-commercial",
        human_approval_required=True,
        human_approved=True,
    )
    nxt = advance_after_apply(
        "shop-demo",
        "brief_locked",
        marker,
        projects_dir=root,
    )
    assert nxt == "assets_gate"
    brief = read_checkpoint(root, "shop-demo", "brief_locked")
    assert brief["status"] == "completed"
    assert brief["human_approved"] is True


def _plan_artifacts() -> dict:
    return {
        "brief": {"theme": "手链", "duration_seconds": 25, "images": {}},
        "asset_precheck": {
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
                }
            ],
            "summary": {
                "total_images": 1,
                "low_resolution_count": 0,
                "duplicate_group_count": 0,
                "needs_user_attention": False,
            },
        },
        "video_plan": {
            "version": "1.0",
            "segments": [
                {
                    "id": "beat_01",
                    "beat": "beat_01",
                    "t": "0-10",
                    "gap_fill": "user_upload",
                    "assignment_status": "assigned",
                    "ref_image": "assets/images/001.png",
                }
            ],
        },
        "segment_cards": {
            "version": "1.0",
            "duration_seconds": 25,
            "overall_prompt_zh": "商品片",
            "segments": [
                {
                    "beat": "beat_01",
                    "time": "00:00-00:10",
                    "copy_plan_zh": "卖点",
                    "shot_plan_zh": "推镜",
                    "asset_plan_zh": "主图",
                }
            ],
        },
    }


def _seed_minimal_ready_for_delivery(root: Path, project_id: str) -> None:
    from PIL import Image

    from lib.board_assets_gate import seal_assets_gate
    from lib.checkpoint import merge_write_checkpoint

    project = root / project_id
    (project / "artifacts").mkdir(parents=True, exist_ok=True)
    (project / "assets" / "images").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 800), (200, 200, 200)).save(
        project / "assets" / "images" / "001.png"
    )
    artifacts = _plan_artifacts()
    for name, body in artifacts.items():
        (project / "artifacts" / f"{name}.json").write_text(
            json.dumps(body, ensure_ascii=False), encoding="utf-8"
        )
    merge_write_checkpoint(
        root,
        project_id,
        "brief_locked",
        "completed",
        artifacts,
        pipeline_type="bootstrap-commercial",
        human_approval_required=True,
        human_approved=True,
    )
    seal_assets_gate(project_id, projects_dir=root)


def _write_bogus_delivery_completed(project: Path) -> None:
    (project / "checkpoint_delivery_signoff.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": project.name,
                "pipeline_type": "bootstrap-commercial",
                "stage": "delivery_signoff",
                "status": "completed",
                "timestamp": "2026-08-18T00:00:00+00:00",
                "checkpoint_policy": "guided",
                "human_approval_required": False,
                "human_approved": True,
                "artifacts": {},
                "metadata": {"minimal_plan_signoff": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_fake_completed_delivery_without_video_reopens(tmp_path: Path) -> None:
    from lib.board_advance import current_confirm_stop

    root = tmp_path / "projects"
    marker = _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    project = root / "shop-demo"
    _write_bogus_delivery_completed(project)
    assert current_confirm_stop("shop-demo", marker, projects_dir=root) == (
        "delivery_signoff"
    )
    write_stop_card("shop-demo", "delivery_signoff", projects_dir=root)
    overlay = json.loads(
        (project / "project.json").read_text(encoding="utf-8")
    )["board_stop"]
    assert overlay["producing_wait"] is True
    assert overlay["needs_user_decision"] is False
    delivery = read_checkpoint(root, "shop-demo", "delivery_signoff")
    assert delivery is not None
    assert delivery["status"] != "completed"
    assert delivery["metadata"].get("minimal_plan_signoff") is not True

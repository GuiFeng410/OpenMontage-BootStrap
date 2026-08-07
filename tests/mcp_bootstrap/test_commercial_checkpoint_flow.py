"""Commercial board/checkpoint integration through the BootStrap facade."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.checkpoint import CheckpointValidationError, read_checkpoint, write_checkpoint
from openmontage.mcp.bootstrap.tools import (
    list_bootstrap_tools,
    produce_append_decision,
    produce_approve_checkpoint,
    produce_analyze_public_product_images,
    produce_init_project,
    produce_scan_user_images,
    produce_write_checkpoint,
)


@pytest.fixture
def sandbox(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    return tmp_path


def _brief() -> dict:
    return {
        "theme": "测试商品 30 秒宣传片",
        "duration_seconds": 30,
        "images": {},
    }


def _video_plan() -> dict:
    return {"segments": [{"id": "beat_01", "t": "0-10", "method": "camera_move"}]}


def _asset_precheck() -> dict:
    return {
        "version": "1.0",
        "entries": [
            {
                "file": "product_hero.png",
                "path": "assets/images/product_hero.png",
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
    }


def test_facade_lists_append_decision() -> None:
    assert "produce_append_decision" in list_bootstrap_tools()["produce_minimal"]


def test_facade_scans_uploaded_images_without_writing_artifacts(sandbox: Path) -> None:
    from PIL import Image

    produce_init_project("commercial-scan", "商品预检", "bootstrap-commercial")
    images_dir = sandbox / "commercial-scan" / "assets" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), "white").save(images_dir / "product_hero.png")

    result = produce_scan_user_images("commercial-scan")

    assert "produce_scan_user_images" in list_bootstrap_tools()["produce_minimal"]
    assert result["summary"]["total_images"] == 1
    assert result["entries"][0]["suggested_class"] == "product_hero"
    assert not (sandbox / "commercial-scan" / "artifacts" / "asset_precheck.json").exists()


def test_facade_requires_explicit_consent_before_sending_public_image_urls() -> None:
    with pytest.raises(Exception, match="explicit user authorization"):
        produce_analyze_public_product_images(
            image_urls_json='["https://images.example.com/product.jpg"]',
            user_authorized=False,
        )


def test_commercial_skills_require_readonly_board_chat_flow() -> None:
    root = Path(__file__).resolve().parents[2]
    usercheck = (
        root / "openmontage" / "skills" / "openmontage-bootstrap-03-usercheck" / "SKILL.md"
    ).read_text(encoding="utf-8")
    produce = (
        root / "openmontage" / "skills" / "openmontage-bootstrap-04-produce" / "SKILL.md"
    ).read_text(encoding="utf-8")
    for text in (usercheck, produce):
        assert "pipeline_type=bootstrap-commercial" in text
        assert "python -m backlot open <project_id>" in text
        assert "produce_append_decision" in text
        assert "网页" in text and "聊天" in text
    assert "produce_scan_user_images" in usercheck
    assert "produce_analyze_public_product_images" in usercheck
    assert "asset_precheck" in usercheck
    assert "表 2 后、表 3 前" in usercheck
    assert "首次商品三点确认卡" in usercheck


def test_intermediate_decision_and_approval_preserve_evidence(sandbox: Path) -> None:
    produce_init_project("commercial-flow", "商品流程", "bootstrap-commercial")
    metadata = {
        "needs_user_decision": True,
        "decision_title_zh": "选择评审模式",
        "decision_prompt_zh": "请选择普通或专业模式",
        "decision_options": [
            {
                "id": "normal",
                "label_zh": "普通模式",
                "description_zh": "只展开问题片段",
                "recommended": True,
            }
        ],
        "partial_progress": {"beats_done": 0, "beats_total": 3},
    }
    cost = {"total_spent_usd": 0.2, "total_reserved_usd": 0.1}

    produce_write_checkpoint(
        "commercial-flow",
        "brief_locked",
        "in_progress",
        pipeline_type="bootstrap-commercial",
        metadata_json=json.dumps(metadata, ensure_ascii=False),
        cost_snapshot_json=json.dumps(cost),
    )
    current = read_checkpoint(sandbox, "commercial-flow", "brief_locked")
    assert current["metadata"]["decision_options"][0]["id"] == "normal"
    assert current["cost_snapshot"]["total_spent_usd"] == 0.2

    artifacts = {
        "brief": _brief(),
        "asset_precheck": _asset_precheck(),
        "video_plan": _video_plan(),
    }
    produce_write_checkpoint(
        "commercial-flow",
        "brief_locked",
        "awaiting_human",
        artifacts_json=json.dumps(artifacts, ensure_ascii=False),
        pipeline_type="bootstrap-commercial",
        metadata_json=json.dumps({**metadata, "needs_user_decision": False}, ensure_ascii=False),
        cost_snapshot_json=json.dumps(cost),
    )
    produce_approve_checkpoint(
        "commercial-flow",
        "brief_locked",
        "确认规划",
        pipeline_type="bootstrap-commercial",
    )

    approved = read_checkpoint(sandbox, "commercial-flow", "brief_locked")
    assert approved["status"] == "completed"
    assert approved["artifacts"] == artifacts
    assert approved["metadata"]["decision_title_zh"] == "选择评审模式"
    assert approved["metadata"]["approval_note"] == "确认规划"
    assert approved["cost_snapshot"] == cost
    history = list((sandbox / "commercial-flow" / "history").glob("checkpoint_brief_locked_*.json"))
    assert len(history) == 1


def test_project_local_artifact_refs_validate(sandbox: Path) -> None:
    pdir = Path(produce_init_project("commercial-refs", "引用", "bootstrap-commercial")["project_dir"])
    (pdir / "artifacts" / "brief.json").write_text(
        json.dumps(_brief(), ensure_ascii=False), encoding="utf-8"
    )
    (pdir / "artifacts" / "video_plan.json").write_text(
        json.dumps(_video_plan(), ensure_ascii=False), encoding="utf-8"
    )
    (pdir / "artifacts" / "asset_precheck.json").write_text(
        json.dumps(_asset_precheck(), ensure_ascii=False), encoding="utf-8"
    )
    result = produce_write_checkpoint(
        "commercial-refs",
        "brief_locked",
        "awaiting_human",
        artifacts_json=json.dumps(
            {
                "brief": "artifacts/brief.json",
                "asset_precheck": "artifacts/asset_precheck.json",
                "video_plan": "artifacts/video_plan.json",
            }
        ),
        pipeline_type="bootstrap-commercial",
    )
    assert Path(result["checkpoint_path"]).exists()


def test_manifest_outputs_are_required_on_new_writes(tmp_path: Path) -> None:
    with pytest.raises(CheckpointValidationError, match="sample_reel"):
        write_checkpoint(
            tmp_path,
            "commercial",
            "sample_review",
            "awaiting_human",
            {},
            pipeline_type="bootstrap-commercial",
        )


def test_append_decision_persists_exact_chat_reply(sandbox: Path) -> None:
    produce_init_project("commercial-decision", "决定", "bootstrap-commercial")
    decision = {
        "decision_id": "d-001",
        "stage": "brief_locked",
        "category": "production_tier_selection",
        "subject": "商品视频制作档位",
        "options_considered": [
            {"option_id": "light", "label": "轻度", "score": 0.5, "reason": "零生成费用"},
            {"option_id": "heavy", "label": "重度", "score": 0.9, "reason": "动态更强"},
        ],
        "selected": "heavy",
        "reason": "用户选择重度并先做试片",
        "user_visible": True,
        "user_approved": True,
        "user_response_text": "重度，先做试片",
        "decided_at": "2026-08-07T10:00:00+00:00",
    }
    produce_append_decision(
        "commercial-decision", json.dumps(decision, ensure_ascii=False)
    )
    saved = json.loads(
        (sandbox / "commercial-decision" / "decision_log.json").read_text(encoding="utf-8")
    )
    assert saved["decisions"][0]["category"] == "production_tier_selection"
    assert saved["decisions"][0]["user_response_text"] == "重度，先做试片"

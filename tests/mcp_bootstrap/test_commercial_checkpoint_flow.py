"""Commercial board/checkpoint integration through the BootStrap facade."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import lib.checkpoint as checkpoint_lib

from lib.checkpoint import (
    CheckpointValidationError,
    read_checkpoint,
    validate_checkpoint,
    write_checkpoint,
)
from openmontage.mcp.bootstrap.tools import (
    list_bootstrap_tools,
    produce_append_decision,
    produce_approve_checkpoint,
    produce_analyze_public_product_images,
    produce_init_project,
    produce_scan_user_images,
    produce_write_checkpoint,
)
from openmontage.mcp.doctor import tools as doctor_tools


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


def _segment_cards() -> dict:
    return {
        "version": "1.0",
        "duration_seconds": 30,
        "overall_prompt_zh": "商品亮相、细节展示、品牌收尾",
        "segments": [
            {
                "beat": "beat_01",
                "time": "00:00-00:10",
                "copy_plan_zh": "先交代商品核心卖点。",
                "shot_plan_zh": "从全景缓慢推进到主体。",
                "asset_plan_zh": "使用商品主图，后续可做轻微推镜。",
            }
        ],
    }


def _seed_checkpoint_status(
    root: Path,
    project_id: str,
    stage: str,
    status: str,
    *,
    pipeline_type: str = "bootstrap-commercial",
) -> None:
    checkpoint = {
        "version": "1.0",
        "project_id": project_id,
        "pipeline_type": pipeline_type,
        "stage": stage,
        "status": status,
        "timestamp": "2026-08-11T00:00:00+00:00",
        "checkpoint_policy": "guided",
        "human_approval_required": False,
        "human_approved": False,
        "artifacts": {},
    }
    project = root / project_id
    project.mkdir(parents=True, exist_ok=True)
    (project / f"checkpoint_{stage}.json").write_text(
        json.dumps(checkpoint), encoding="utf-8"
    )


def _media_artifacts(stage: str, media_path: str) -> dict:
    if stage == "sample_review":
        return {"sample_reel": {"path": media_path}}
    if stage == "draft_review":
        return {
            "full_draft_pro": {
                "path": media_path,
                "issue_segments": [],
                "modification_list": [],
            }
        }
    return {
        "final_review": {
            "version": "1.0",
            "output_path": media_path,
            "status": "pass",
            "checks": {
                "technical_probe": {},
                "visual_spotcheck": {},
                "audio_spotcheck": {},
                "promise_preservation": {},
                "subtitle_check": {},
            },
        }
    }


def _commercial_checkpoint(stage: str, artifacts: dict, status: str = "awaiting_human") -> dict:
    return {
        "version": "1.0",
        "project_id": "commercial-media",
        "pipeline_type": "bootstrap-commercial",
        "stage": stage,
        "status": status,
        "timestamp": "2026-08-11T00:00:00+00:00",
        "checkpoint_policy": "guided",
        "human_approval_required": status == "awaiting_human",
        "human_approved": False,
        "artifacts": artifacts,
    }


def _run_concurrently(*calls) -> None:
    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        futures = [executor.submit(call) for call in calls]
        for future in futures:
            future.result(timeout=10)


def _force_legacy_mcp_rmw_race(monkeypatch: pytest.MonkeyPatch) -> None:
    original_sync = doctor_tools._sync_production_profile_to_marker
    barrier = threading.Barrier(2)

    def synchronized_sync(project_id, fields):
        synced = original_sync(project_id, fields)
        barrier.wait(timeout=5)
        return synced

    monkeypatch.setattr(
        doctor_tools,
        "_sync_production_profile_to_marker",
        synchronized_sync,
    )


def test_facade_lists_append_decision() -> None:
    assert "produce_append_decision" in list_bootstrap_tools()["produce_minimal"]
    assert "produce_import_project_images" in list_bootstrap_tools()["produce_minimal"]


def test_concurrent_write_checkpoint_merges_both_patches_under_one_lock(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    produce_init_project("concurrent-write", "并发写入", "animated-explainer")
    _force_legacy_mcp_rmw_race(monkeypatch)

    _run_concurrently(
        lambda: produce_write_checkpoint(
            "concurrent-write",
            "proposal",
            "in_progress",
            artifacts_json=json.dumps({"writer_a": {"value": "a"}}),
            metadata_json=json.dumps({"meta_a": "a"}),
        ),
        lambda: produce_write_checkpoint(
            "concurrent-write",
            "proposal",
            "in_progress",
            artifacts_json=json.dumps({"writer_b": {"value": "b"}}),
            metadata_json=json.dumps({"meta_b": "b"}),
        ),
    )

    saved = read_checkpoint(sandbox, "concurrent-write", "proposal")
    assert saved["artifacts"]["writer_a"] == {"value": "a"}
    assert saved["artifacts"]["writer_b"] == {"value": "b"}
    assert saved["metadata"]["meta_a"] == "a"
    assert saved["metadata"]["meta_b"] == "b"


def test_concurrent_approve_and_patch_preserve_fields_and_cleanup(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "concurrent-approve"
    produce_init_project(project_id, "并发审批", "bootstrap-commercial")
    artifacts = {
        "brief": _brief(),
        "asset_precheck": _asset_precheck(),
        "video_plan": _video_plan(),
        "segment_cards": _segment_cards(),
    }
    produce_write_checkpoint(
        project_id,
        "brief_locked",
        "awaiting_human",
        artifacts_json=json.dumps(artifacts, ensure_ascii=False),
        pipeline_type="bootstrap-commercial",
        human_approval_required=True,
        metadata_json=json.dumps(
            {
                "needs_user_decision": True,
                "decision_title_zh": "待清理",
                "decision_prompt_zh": "请选择",
            },
            ensure_ascii=False,
        ),
    )
    _force_legacy_mcp_rmw_race(monkeypatch)

    _run_concurrently(
        lambda: produce_approve_checkpoint(
            project_id,
            "brief_locked",
            "确认通过",
            pipeline_type="bootstrap-commercial",
        ),
        lambda: produce_write_checkpoint(
            project_id,
            "brief_locked",
            "completed",
            artifacts_json=json.dumps({"parallel_patch": {"value": "kept"}}),
            pipeline_type="bootstrap-commercial",
            human_approval_required=True,
            human_approved=True,
            metadata_json=json.dumps({"parallel_meta": "kept"}),
        ),
    )

    saved = read_checkpoint(sandbox, project_id, "brief_locked")
    assert saved["artifacts"]["parallel_patch"] == {"value": "kept"}
    assert saved["metadata"]["parallel_meta"] == "kept"
    assert saved["metadata"]["approval_note"] == "确认通过"
    assert saved["metadata"]["needs_user_decision"] is False
    assert "decision_title_zh" not in saved["metadata"]
    assert "decision_prompt_zh" not in saved["metadata"]


def test_concurrent_write_and_approve_keep_marker_on_latest_checkpoint_profile(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "concurrent-profile"
    produce_init_project(project_id, "并发档位", "bootstrap-commercial")
    artifacts = {
        "brief": _brief(),
        "asset_precheck": _asset_precheck(),
        "video_plan": _video_plan(),
        "segment_cards": _segment_cards(),
    }
    produce_write_checkpoint(
        project_id,
        "brief_locked",
        "awaiting_human",
        artifacts_json=json.dumps(artifacts, ensure_ascii=False),
        pipeline_type="bootstrap-commercial",
        human_approval_required=True,
    )

    original_merge_write = checkpoint_lib.merge_write_checkpoint
    original_sync = doctor_tools._sync_production_profile_to_marker
    first_checkpoint_written = threading.Event()
    second_checkpoint_written = threading.Event()
    second_marker_synced = threading.Event()

    def controlled_merge_write(*args, **kwargs):
        tier = (
            (args[4].get("production_profile") or {}).get("production_tier")
            if isinstance(args[4], dict)
            else None
        )
        if tier == "light":
            result = original_merge_write(*args, **kwargs)
            first_checkpoint_written.set()
            assert second_checkpoint_written.wait(timeout=5)
            return result
        assert first_checkpoint_written.wait(timeout=5)
        result = original_merge_write(*args, **kwargs)
        second_checkpoint_written.set()
        return result

    def controlled_sync(marker_project_id, fields):
        tier = (fields.get("production_profile") or {}).get("production_tier")
        if tier == "light":
            assert second_marker_synced.wait(timeout=5)
            return original_sync(marker_project_id, fields)
        result = original_sync(marker_project_id, fields)
        second_marker_synced.set()
        return result

    monkeypatch.setattr(
        checkpoint_lib,
        "merge_write_checkpoint",
        controlled_merge_write,
    )
    monkeypatch.setattr(
        doctor_tools,
        "_sync_production_profile_to_marker",
        controlled_sync,
    )

    _run_concurrently(
        lambda: produce_write_checkpoint(
            project_id,
            "brief_locked",
            "completed",
            artifacts_json=json.dumps(
                {"production_profile": {"production_tier": "light"}}
            ),
            pipeline_type="bootstrap-commercial",
            human_approval_required=True,
            human_approved=True,
        ),
        lambda: produce_approve_checkpoint(
            project_id,
            "brief_locked",
            "确认重度档",
            artifacts_json=json.dumps(
                {"production_profile": {"production_tier": "heavy"}}
            ),
            pipeline_type="bootstrap-commercial",
        ),
    )

    checkpoint = read_checkpoint(sandbox, project_id, "brief_locked")
    marker = json.loads(
        (sandbox / project_id / "project.json").read_text(encoding="utf-8")
    )
    assert checkpoint["artifacts"]["production_profile"]["production_tier"] == "heavy"
    assert marker["production_profile"]["production_tier"] == "heavy"


def test_concurrent_append_decision_keeps_both_decisions(sandbox: Path) -> None:
    project_id = "concurrent-decisions"
    produce_init_project(project_id, "并发决定", "bootstrap-commercial")

    def append(decision_id: str, selected: str) -> None:
        produce_append_decision(
            project_id,
            json.dumps(
                {
                    "decision_id": decision_id,
                    "stage": "brief_locked",
                    "category": "asset_decision",
                    "subject": f"并发决定 {decision_id}",
                    "options_considered": [
                        {
                            "option_id": selected,
                            "label": selected,
                            "score": 1.0,
                            "reason": "并发测试",
                        }
                    ],
                    "selected": selected,
                    "reason": "并发测试",
                },
                ensure_ascii=False,
            ),
        )

    _run_concurrently(
        lambda: append("d-concurrent-a", "a"),
        lambda: append("d-concurrent-b", "b"),
    )

    saved = json.loads(
        (sandbox / project_id / "decision_log.json").read_text(encoding="utf-8")
    )
    assert {item["decision_id"] for item in saved["decisions"]} == {
        "d-concurrent-a",
        "d-concurrent-b",
    }


def test_facade_scans_uploaded_images_without_writing_artifacts(sandbox: Path) -> None:
    from PIL import Image

    produce_init_project("commercial-scan", "商品预检", "bootstrap-commercial")
    images_dir = sandbox / "commercial-scan" / "assets" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), "white").save(images_dir / "product_hero.png")

    result = produce_scan_user_images("commercial-scan")

    assert "produce_scan_user_images" in list_bootstrap_tools()["produce_minimal"]
    assert "produce_describe_user_images" in list_bootstrap_tools()["produce_minimal"]
    assert result["summary"]["total_images"] == 1
    assert result["entries"][0]["suggested_class"] == "product_hero"
    assert not (sandbox / "commercial-scan" / "artifacts" / "asset_precheck.json").exists()


def test_facade_describe_user_images_degrades_without_vision_key(sandbox: Path, monkeypatch) -> None:
    from PIL import Image
    from openmontage.mcp.bootstrap.tools import produce_describe_user_images

    monkeypatch.setattr(
        "lib.asset_vision.resolve_vision_env",
        lambda: {
            "api_key": "",
            "base_url": "https://example.invalid/v1",
            "model": "qwen-vl-max",
            "available": False,
            "key_source": "",
        },
    )
    produce_init_project("commercial-vision", "商品识图", "bootstrap-commercial")
    images_dir = sandbox / "commercial-vision" / "assets" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), "white").save(images_dir / "ring.png")

    result = produce_describe_user_images("commercial-vision")
    assert result["vision_degraded"] is True
    assert result["precheck"]["summary"]["total_images"] == 1
    assert not (sandbox / "commercial-vision" / "artifacts" / "asset_vision.json").exists()


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
    providers = (
        root / "openmontage" / "skills" / "openmontage-bootstrap-06-providers" / "SKILL.md"
    ).read_text(encoding="utf-8")
    for text in (usercheck, produce):
        assert "pipeline_type=bootstrap-commercial" in text
        assert "python -m backlot open <project_id>" in text
        assert "produce_append_decision" in text
        assert "网页" in text and "聊天" in text
    assert "produce_scan_user_images" in usercheck
    assert "produce_describe_user_images" in usercheck
    assert 'mode="create_new"' in usercheck
    assert 'mode="resume"' in usercheck
    assert "produce_import_project_images" in usercheck
    assert "默认新建独立项目" in usercheck
    assert "你可以查看该网址了解详细信息" in usercheck
    assert "已进入第 N 阶段" in usercheck
    assert "produce_analyze_public_product_images" in usercheck
    assert "asset_precheck" in usercheck
    assert "你可以查看该网址了解详细信息" in produce
    assert "已进入第 N 阶段" in produce
    assert "阶段封板" in usercheck
    assert "阶段封板" in produce
    assert "证据已写入看板" in usercheck
    assert "表 2 后、表 3 前" in usercheck
    assert "首次商品三点确认卡" in usercheck
    assert "商品片 ↔ 七阶段" in usercheck
    assert "commercial-video-15s-review.md" in usercheck
    assert "commercial-video-30s-review.md" not in usercheck
    assert "commercial-video-15s-review.md" in produce
    assert "commercial-video-30s-review.md" not in produce
    assert "付费 AI 镜提示词" in produce
    assert "asset-preprocess-gate.md" in usercheck
    assert "commercial-prompt-lexicon.md" in usercheck
    assert "openmontage-seedance-prompt" in produce
    assert "clarifyprompt" not in usercheck
    assert "clarifyprompt" not in produce
    assert "commercial-prompt-lexicon.md" in produce
    assert "asset-preprocess-gate.md" in produce
    assert "禁止重新调用 produce_init_project" in produce
    assert 'subject="Pixverse local image temporary OSS upload"' in usercheck
    assert "user_authorized_upload=true" in usercheck
    assert "user_authorized_upload=true" in produce
    assert "oss_staging.json" in produce
    assert "OSS_ACCESS_KEY_ID" in providers
    assert "配置 Key 不等于授权上传" in providers


def test_intermediate_decision_and_approval_preserve_evidence(sandbox: Path) -> None:
    produce_init_project("commercial-flow", "商品流程", "bootstrap-commercial")
    metadata = {
        "needs_user_decision": True,
        "decision_title_zh": "选择评审模式",
        "decision_context_zh": "需要确定后续评审深度",
        "decision_prompt_zh": "请选择普通或专业模式",
        "decision_options": [
            {
                "id": "normal",
                "label_zh": "普通模式",
                "description_zh": "只展开问题片段",
                "recommended": True,
            }
        ],
        "recommendation_zh": "建议普通模式",
        "examples_zh": ["普通模式只展开问题片段"],
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
        "segment_cards": _segment_cards(),
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
        artifacts_json="{}",
        pipeline_type="bootstrap-commercial",
    )

    approved = read_checkpoint(sandbox, "commercial-flow", "brief_locked")
    assert approved["status"] == "completed"
    assert approved["artifacts"]["brief"] == artifacts["brief"]
    assert approved["artifacts"]["video_plan"] == artifacts["video_plan"]
    assert approved["artifacts"]["segment_cards"]["overall_prompt_zh"] == _segment_cards()["overall_prompt_zh"]
    assert (sandbox / "commercial-flow" / "artifacts" / "brief.json").exists()
    assert approved["metadata"]["needs_user_decision"] is False
    for stale_key in (
        "decision_title_zh",
        "decision_context_zh",
        "decision_prompt_zh",
        "decision_options",
        "recommendation_zh",
        "examples_zh",
    ):
        assert stale_key not in approved["metadata"]
    assert approved["metadata"]["partial_progress"] == {"beats_done": 0, "beats_total": 3}
    assert approved["metadata"]["approval_note"] == "确认规划"
    assert approved["cost_snapshot"] == cost
    history = list((sandbox / "commercial-flow" / "history").glob("checkpoint_brief_locked_*.json"))
    assert len(history) == 1
    archived = json.loads(history[0].read_text(encoding="utf-8"))
    assert archived["status"] == "awaiting_human"
    assert archived["metadata"]["decision_title_zh"] == "选择评审模式"


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
    (pdir / "artifacts" / "segment_cards.json").write_text(
        json.dumps(_segment_cards(), ensure_ascii=False), encoding="utf-8"
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
                "segment_cards": "artifacts/segment_cards.json",
            }
        ),
        pipeline_type="bootstrap-commercial",
    )
    assert Path(result["checkpoint_path"]).exists()


def test_manifest_outputs_are_required_on_new_writes(tmp_path: Path) -> None:
    for stage in ("brief_locked", "assets_gate"):
        _seed_checkpoint_status(tmp_path, "commercial", stage, "completed")

    with pytest.raises(CheckpointValidationError, match="sample_reel"):
        write_checkpoint(
            tmp_path,
            "commercial",
            "sample_review",
            "awaiting_human",
            {},
            pipeline_type="bootstrap-commercial",
        )


def test_commercial_rejects_skipping_an_unfinished_prior_stage(tmp_path: Path) -> None:
    _seed_checkpoint_status(tmp_path, "commercial-order", "brief_locked", "completed")

    with pytest.raises(CheckpointValidationError, match=r"未完成前序阶段.*assets_gate"):
        write_checkpoint(
            tmp_path,
            "commercial-order",
            "sample_review",
            "in_progress",
            {},
            pipeline_type="bootstrap-commercial",
        )


def test_commercial_order_gate_applies_to_failed_status(tmp_path: Path) -> None:
    _seed_checkpoint_status(tmp_path, "commercial-failed-order", "brief_locked", "completed")

    with pytest.raises(CheckpointValidationError, match=r"未完成前序阶段.*assets_gate"):
        write_checkpoint(
            tmp_path,
            "commercial-failed-order",
            "sample_review",
            "failed",
            {},
            pipeline_type="bootstrap-commercial",
            error="生成失败",
        )


@pytest.mark.parametrize("status", ["awaiting_human", "completed"])
def test_commercial_order_gate_applies_to_later_terminal_statuses(
    tmp_path: Path, status: str
) -> None:
    _seed_checkpoint_status(tmp_path, "commercial-terminal-order", "brief_locked", "completed")

    with pytest.raises(CheckpointValidationError, match=r"未完成前序阶段.*assets_gate"):
        write_checkpoint(
            tmp_path,
            "commercial-terminal-order",
            "sample_review",
            status,
            {"sample_reel": {}},
            pipeline_type="bootstrap-commercial",
            human_approved=True,
        )


def test_commercial_rejects_segment_build_while_sample_review_awaits_human(
    tmp_path: Path,
) -> None:
    for stage in ("brief_locked", "assets_gate"):
        _seed_checkpoint_status(tmp_path, "commercial-awaiting", stage, "completed")
    _seed_checkpoint_status(
        tmp_path, "commercial-awaiting", "sample_review", "awaiting_human"
    )

    with pytest.raises(CheckpointValidationError, match=r"未完成前序阶段.*sample_review"):
        write_checkpoint(
            tmp_path,
            "commercial-awaiting",
            "segment_build",
            "in_progress",
            {},
            pipeline_type="bootstrap-commercial",
        )


def test_commercial_retry_blocks_later_stage_until_recompleted(tmp_path: Path) -> None:
    for stage in ("brief_locked", "assets_gate", "sample_review"):
        _seed_checkpoint_status(tmp_path, "commercial-retry", stage, "completed")
    write_checkpoint(
        tmp_path,
        "commercial-retry",
        "sample_review",
        "in_progress",
        {},
        pipeline_type="bootstrap-commercial",
    )

    with pytest.raises(CheckpointValidationError, match=r"未完成前序阶段.*sample_review"):
        write_checkpoint(
            tmp_path,
            "commercial-retry",
            "segment_build",
            "in_progress",
            {},
            pipeline_type="bootstrap-commercial",
        )


def test_commercial_allows_first_stage_and_rewriting_current_next_stage(
    tmp_path: Path,
) -> None:
    write_checkpoint(
        tmp_path,
        "commercial-allowed",
        "brief_locked",
        "in_progress",
        {},
        pipeline_type="bootstrap-commercial",
    )
    _seed_checkpoint_status(tmp_path, "commercial-allowed", "brief_locked", "completed")
    for _ in range(2):
        write_checkpoint(
            tmp_path,
            "commercial-allowed",
            "assets_gate",
            "in_progress",
            {},
            pipeline_type="bootstrap-commercial",
        )


def test_noncommercial_pipeline_keeps_permissive_stage_writes(tmp_path: Path) -> None:
    path = write_checkpoint(
        tmp_path,
        "framework-order",
        "script",
        "in_progress",
        {},
        pipeline_type="framework-smoke",
    )

    assert path.exists()


def test_marker_pipeline_rejects_explicit_known_pipeline_mismatch(
    tmp_path: Path,
) -> None:
    project = tmp_path / "marker-authority"
    project.mkdir()
    (project / "project.json").write_text(
        json.dumps({"pipeline_type": "bootstrap-commercial", "title": "t"}),
        encoding="utf-8",
    )

    with pytest.raises(CheckpointValidationError, match="pipeline_type.*marker"):
        write_checkpoint(
            tmp_path,
            "marker-authority",
            "research",
            "in_progress",
            {},
            pipeline_type="framework-smoke",
        )


def test_unknown_pipeline_cannot_bypass_delivery_signoff_gate(
    tmp_path: Path,
) -> None:
    project_id = "delivery-marker-authority"
    project = tmp_path / project_id
    project.mkdir()
    (project / "project.json").write_text(
        json.dumps({"pipeline_type": "bootstrap-commercial", "title": "t"}),
        encoding="utf-8",
    )
    for stage in (
        "brief_locked",
        "assets_gate",
        "sample_review",
        "segment_build",
        "draft_review",
        "final_compose",
    ):
        _seed_checkpoint_status(tmp_path, project_id, stage, "completed")

    with pytest.raises(CheckpointValidationError, match="GATE VIOLATION"):
        write_checkpoint(
            tmp_path,
            project_id,
            "delivery_signoff",
            "completed",
            {},
            pipeline_type="unknown",
        )


@pytest.mark.parametrize(
    "stage",
    ["sample_review", "draft_review", "final_compose", "delivery_signoff"],
)
def test_commercial_media_stage_accepts_existing_project_file(
    tmp_path: Path, stage: str
) -> None:
    project = tmp_path / "commercial-media"
    media = project / "renders" / "review.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"video")

    validate_checkpoint(
        _commercial_checkpoint(stage, _media_artifacts(stage, "renders/review.mp4")),
        project_dir=project,
    )


@pytest.mark.parametrize(
    ("stage", "status"),
    [
        ("sample_review", "awaiting_human"),
        ("draft_review", "completed"),
        ("final_compose", "awaiting_human"),
        ("delivery_signoff", "completed"),
    ],
)
def test_commercial_media_stage_rejects_missing_file(
    tmp_path: Path, stage: str, status: str
) -> None:
    project = tmp_path / "commercial-media"
    project.mkdir()

    with pytest.raises(CheckpointValidationError, match=r"媒体文件.*不存在"):
        validate_checkpoint(
            _commercial_checkpoint(
                stage,
                _media_artifacts(stage, "renders/missing.mp4"),
                status=status,
            ),
            project_dir=project,
        )


@pytest.mark.parametrize(
    "stage",
    ["sample_review", "draft_review", "final_compose", "delivery_signoff"],
)
def test_commercial_media_stage_rejects_file_outside_project(
    tmp_path: Path, stage: str
) -> None:
    project = tmp_path / "commercial-media"
    project.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")

    with pytest.raises(CheckpointValidationError, match=r"媒体路径.*项目目录"):
        validate_checkpoint(
            _commercial_checkpoint(stage, _media_artifacts(stage, str(outside))),
            project_dir=project,
        )


def test_commercial_media_stage_rejects_directory_path(tmp_path: Path) -> None:
    project = tmp_path / "commercial-media"
    directory = project / "renders"
    directory.mkdir(parents=True)

    with pytest.raises(CheckpointValidationError, match=r"媒体路径.*实际文件"):
        validate_checkpoint(
            _commercial_checkpoint(
                "sample_review",
                _media_artifacts("sample_review", "renders"),
            ),
            project_dir=project,
        )


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("review.json", b'{"not":"video"}'),
        ("empty.mp4", b""),
    ],
)
def test_commercial_media_stage_rejects_non_reviewable_media(
    tmp_path: Path,
    filename: str,
    content: bytes,
) -> None:
    project = tmp_path / "commercial-media"
    media = project / "renders" / filename
    media.parent.mkdir(parents=True)
    media.write_bytes(content)

    with pytest.raises(CheckpointValidationError, match="媒体不可评审"):
        validate_checkpoint(
            _commercial_checkpoint(
                "sample_review",
                _media_artifacts("sample_review", f"renders/{filename}"),
            ),
            project_dir=project,
        )


@pytest.mark.parametrize(
    "stage",
    ["sample_review", "draft_review", "final_compose", "delivery_signoff"],
)
def test_commercial_media_stage_rejects_missing_media_artifact(
    tmp_path: Path, stage: str
) -> None:
    project = tmp_path / "commercial-media"
    project.mkdir()

    with pytest.raises(CheckpointValidationError, match=r"媒体工件.*必须提供"):
        validate_checkpoint(
            _commercial_checkpoint(stage, {}),
            project_dir=project,
        )


@pytest.mark.parametrize("stage", ["final_compose", "delivery_signoff"])
def test_commercial_media_stage_rejects_blank_media_path(
    tmp_path: Path, stage: str
) -> None:
    project = tmp_path / "commercial-media"
    project.mkdir()
    artifacts = _media_artifacts(stage, "")

    with pytest.raises(CheckpointValidationError, match=r"媒体工件.*output_path.*非空"):
        validate_checkpoint(
            _commercial_checkpoint(stage, artifacts),
            project_dir=project,
        )


def test_commercial_media_stage_allows_in_progress_without_media(tmp_path: Path) -> None:
    validate_checkpoint(
        _commercial_checkpoint("sample_review", {}, status="in_progress"),
        project_dir=tmp_path / "commercial-media",
    )


def test_brief_locked_requires_complete_segment_cards(sandbox: Path) -> None:
    produce_init_project("commercial-segments", "分段完整性", "bootstrap-commercial")
    base_artifacts = {
        "brief": _brief(),
        "asset_precheck": _asset_precheck(),
        "video_plan": _video_plan(),
    }

    with pytest.raises(CheckpointValidationError, match="segment_cards"):
        produce_write_checkpoint(
            "commercial-segments",
            "brief_locked",
            "awaiting_human",
            artifacts_json=json.dumps(base_artifacts, ensure_ascii=False),
            pipeline_type="bootstrap-commercial",
        )

    with pytest.raises(CheckpointValidationError, match="segment_cards"):
        produce_write_checkpoint(
            "commercial-segments",
            "brief_locked",
            "awaiting_human",
            artifacts_json=json.dumps(
                {
                    **base_artifacts,
                    "segment_cards": {
                        "overall_prompt_zh": "只有不完整分段",
                        "segments": [
                            {
                                "beat": "beat_01",
                                "copy_plan_zh": "只有文案，没有镜头和素材规划",
                            }
                        ],
                    },
                },
                ensure_ascii=False,
            ),
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

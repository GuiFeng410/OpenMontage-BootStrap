"""Commercial board/checkpoint integration through the BootStrap facade."""

from __future__ import annotations

import hashlib
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image
import lib.checkpoint as checkpoint_lib
from lib import asset_precheck as asset_precheck_lib

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
from openmontage.mcp.common.errors import DoctorError
from openmontage.mcp.doctor import tools as doctor_tools


_TEST_IMAGE_BUFFER = io.BytesIO()
Image.new("RGB", (800, 600), "white").save(_TEST_IMAGE_BUFFER, format="PNG")
_TEST_IMAGE_BYTES = _TEST_IMAGE_BUFFER.getvalue()
_TEST_IMAGE_SHA256 = hashlib.sha256(_TEST_IMAGE_BYTES).hexdigest()


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


def _commercial_checkpoint(
    stage: str,
    artifacts: dict,
    status: str = "awaiting_human",
    *,
    project_id: str = "commercial-media",
) -> dict:
    return {
        "version": "1.0",
        "project_id": project_id,
        "pipeline_type": "bootstrap-commercial",
        "stage": stage,
        "status": status,
        "timestamp": "2026-08-11T00:00:00+00:00",
        "checkpoint_policy": "guided",
        "human_approval_required": status == "awaiting_human",
        "human_approved": False,
        "artifacts": artifacts,
    }


def _asset_assignment_ledger(
    *,
    missing: bool = False,
    orphan: bool = False,
    reuse: bool = False,
    i2i_review_status: str = "",
) -> dict:
    if reuse:
        entries = [
            {"path": "assets/images/01.png", "kind": "image", "beat": "S1,S4"},
            {"path": "assets/images/02.png", "kind": "image", "beat": "S2"},
            {"path": "assets/images/03.png", "kind": "image", "beat": "S3"},
            {"path": "assets/images/04.png", "kind": "image", "beat": "S5"},
            {"path": "assets/images/06.png", "kind": "image", "beat": "S6"},
        ]
    else:
        entries = [
            {
                "path": f"assets/images/{beat}.png",
                "kind": "image",
                "beat": beat,
            }
            for beat in ("S1", "S2", "S3", "S4", "S5", "S6")
            if not (missing and beat == "S6")
        ]
    if orphan:
        entries.append({
            "path": "assets/images/orphan.png",
            "kind": "image",
            "beat": "S9",
        })
    for entry in entries:
        entry.setdefault("user_class", "product_hero")
        entry.setdefault("status", "confirmed")
    if i2i_review_status == "approved":
        entries = [
            entry
            for entry in entries
            if entry.get("beat") != "S6"
        ]
    ledger = {
        "version": "1.0",
        "entries": entries,
        "summary": {
            "available_image_count": len(entries),
            "counts_by_class": {"product_hero": len(entries)},
            "status_zh": "就绪",
        },
    }
    if i2i_review_status:
        ledger["planned_entries"] = [{
            "beat": "S6",
            "kind": "image",
            "origin": "i2i",
            "status": (
                "approved"
                if i2i_review_status == "approved"
                else "ready"
            ),
            "review_status": i2i_review_status,
            "decision_id": "d-i2i-review-S6",
            "output_path": "assets/images/i2i-S6.png",
            "candidate_paths": ["assets/images/i2i-S6.png"],
            "provider": "test-provider",
            "model": "test-i2i-model",
        }]
    return ledger


def _generated_review_decision_log(
    project_id: str,
    path: str,
    beats: list[str],
    *,
    decision_id: str = "d-generated-review",
    decision_patch: dict | None = None,
) -> dict:
    decision = {
        "decision_id": decision_id,
        "stage": "assets_gate",
        "category": "asset_decision",
        "subject": path,
        "asset_path": path,
        "asset_source": "generated",
        "asset_sha256": _TEST_IMAGE_SHA256,
        "beat_ids": beats,
        "options_considered": [{
            "option_id": "approved",
            "label": "批准生成图",
            "score": 1.0,
            "reason": "候选图符合当前 Beat。",
        }],
        "selected": "approved",
        "reason": "用户批准该候选图。",
        "user_visible": True,
        "user_approved": True,
        "user_response_text": "批准该候选图。",
    }
    decision.update(decision_patch or {})
    return {
        "version": "1.0",
        "project_id": project_id,
        "decisions": [decision],
    }


def _stage_asset_assignment_gate(
    root: Path,
    project_id: str,
    ledger: dict,
    *,
    decision_log: dict | None = None,
) -> Path:
    project = root / project_id
    artifacts_dir = project / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps({
            "version": "1.0",
            "project_id": project_id,
            "pipeline_type": "bootstrap-commercial",
        }),
        encoding="utf-8",
    )
    canonical = [
        {"id": f"S{index}", "t": f"{(index - 1) * 5}-{index * 5}"}
        for index in range(1, 7)
    ]
    (artifacts_dir / "video_plan.json").write_text(
        json.dumps({"segments": canonical}),
        encoding="utf-8",
    )
    (artifacts_dir / "segment_cards.json").write_text(
        json.dumps({
            "version": "1.0",
            "duration_seconds": 30,
            "overall_prompt_zh": "六个 Beat 完成商品亮相、细节展示与收束。",
            "segments": [
                {
                    "beat": row["id"],
                    "time": row["t"],
                    "copy_plan_zh": f"{row['id']} 文案规划",
                    "shot_plan_zh": f"{row['id']} 镜头规划",
                    "asset_plan_zh": f"{row['id']} 素材规划",
                }
                for row in canonical
            ],
        }),
        encoding="utf-8",
    )
    (artifacts_dir / "asset_ledger.json").write_text(
        json.dumps(ledger),
        encoding="utf-8",
    )
    (artifacts_dir / "decision_log.json").write_text(
        json.dumps(decision_log or {
            "version": "1.0",
            "project_id": project_id,
            "decisions": [],
        }),
        encoding="utf-8",
    )
    for entry in [
        *(ledger.get("entries") or []),
        *(ledger.get("planned_entries") or []),
    ]:
        raw_path = entry.get("path") or entry.get("output_path")
        if raw_path:
            path = project / raw_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_TEST_IMAGE_BYTES)
    return project


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


def test_append_decision_rejects_conflicting_duplicate_decision_id(
    sandbox: Path,
) -> None:
    project_id = "duplicate-decision-id"
    produce_init_project(project_id, "重复决定", "bootstrap-commercial")

    def decision(selected: str) -> dict:
        return {
            "decision_id": "d-shared",
            "stage": "assets_gate",
            "category": "asset_decision",
            "subject": "同一决定",
            "options_considered": [{
                "option_id": selected,
                "label": selected,
                "score": 1.0,
                "reason": "重复 ID 测试",
            }],
            "selected": selected,
            "reason": "重复 ID 测试",
        }

    first = produce_append_decision(
        project_id,
        json.dumps(decision("approved"), ensure_ascii=False),
    )

    assert first["appended"] == 1
    with pytest.raises(DoctorError, match="decision_id"):
        produce_append_decision(
            project_id,
            json.dumps(decision("rejected"), ensure_ascii=False),
        )
    saved = json.loads(
        (sandbox / project_id / "decision_log.json").read_text(encoding="utf-8")
    )
    assert len(saved["decisions"]) == 1
    assert saved["decisions"][0]["selected"] == "approved"


def test_append_generated_image_approval_binds_current_content_hash(
    sandbox: Path,
) -> None:
    project_id = "hashed-image-approval"
    produce_init_project(project_id, "审图哈希", "bootstrap-commercial")
    relative_path = "assets/images/approved.png"
    image_path = sandbox / project_id / relative_path
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(_TEST_IMAGE_BYTES)
    decision = _generated_review_decision_log(
        project_id,
        relative_path,
        ["S1"],
        decision_id="d-hashed-approval",
    )["decisions"][0]
    decision.pop("asset_sha256")

    result = produce_append_decision(
        project_id,
        json.dumps(decision, ensure_ascii=False),
    )

    saved = json.loads(
        (sandbox / project_id / "decision_log.json").read_text(encoding="utf-8")
    )
    assert result["appended"] == 1
    assert saved["decisions"][0]["asset_sha256"] == _TEST_IMAGE_SHA256


def test_append_legacy_non_generated_approval_is_idempotent_without_hash(
    sandbox: Path,
) -> None:
    project_id = "legacy-non-generated-approval"
    produce_init_project(project_id, "旧素材批准", "bootstrap-commercial")
    relative_path = "assets/images/uploaded.png"
    image_path = sandbox / project_id / relative_path
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(_TEST_IMAGE_BYTES)
    decision = {
        "decision_id": "d-legacy-approved",
        "stage": "assets_gate",
        "category": "asset_decision",
        "subject": relative_path,
        "asset_path": relative_path,
        "beat_ids": ["S1"],
        "options_considered": [{
            "option_id": "approved",
            "label": "批准旧用户图",
            "score": 1.0,
            "reason": "沿用旧式用户素材决定。",
        }],
        "selected": "approved",
        "reason": "沿用旧式用户素材决定。",
    }

    first = produce_append_decision(
        project_id,
        json.dumps(decision, ensure_ascii=False),
    )
    second = produce_append_decision(
        project_id,
        json.dumps(decision, ensure_ascii=False),
    )

    saved = json.loads(
        (sandbox / project_id / "decision_log.json").read_text(encoding="utf-8")
    )
    assert first["appended"] == 1
    assert second["appended"] == 0
    assert "asset_sha256" not in saved["decisions"][0]


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


@pytest.mark.parametrize(
    ("scenario", "ledger", "expected_error"),
    [
        (
            "orphan",
            _asset_assignment_ledger(orphan=True),
            r"orphan|孤儿",
        ),
        (
            "missing",
            _asset_assignment_ledger(missing=True),
            r"missing|缺少",
        ),
        (
            "reuse-unapproved",
            _asset_assignment_ledger(reuse=True),
            r"reuse_pending|复用.*未批准",
        ),
        (
            "i2i-unreviewed",
            _asset_assignment_ledger(i2i_review_status="pending"),
            r"i2i.*review|图生图.*未审",
        ),
    ],
)
def test_assets_gate_completed_rejects_open_assignment_states(
    tmp_path: Path,
    scenario: str,
    ledger: dict,
    expected_error: str,
) -> None:
    project = _stage_asset_assignment_gate(tmp_path, scenario, ledger)

    with pytest.raises(CheckpointValidationError, match=expected_error):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=scenario,
            ),
            project_dir=project,
        )


@pytest.mark.parametrize(
    "scenario",
    [
        "open-non-i2i-plan",
        "multiple-paths-one-beat",
        "generic-reuse-approval",
        "reuse-wrong-project",
        "reuse-wrong-stage",
        "reuse-wrong-path",
        "reuse-wrong-beats",
        "conflicting-i2i-source",
        "conflicting-beat-fields",
        "duplicate-canonical-id",
    ],
)
def test_assets_gate_completed_rejects_assignment_contract_bypasses(
    tmp_path: Path,
    scenario: str,
) -> None:
    project_id = f"contract-{scenario}"
    ledger = _asset_assignment_ledger()
    decision_log = None

    if scenario == "open-non-i2i-plan":
        ledger["planned_entries"] = [{
            "beats": ["S1"],
            "kind": "image",
            "origin": "user_upload",
            "status": "planned",
            "output_path": "assets/images/future.png",
        }]
    elif scenario == "multiple-paths-one-beat":
        ledger["entries"].append({
            "path": "assets/images/S1-alternate.png",
            "kind": "image",
            "beat": "S1",
            "user_class": "product_hero",
            "status": "confirmed",
        })
    elif scenario == "generic-reuse-approval":
        ledger = _asset_assignment_ledger(reuse=True)
        decision_log = {
            "version": "1.0",
            "project_id": project_id,
            "decisions": [{
                "decision_id": "generic-approval",
                "stage": "assets_gate",
                "category": "asset_decision",
                "subject": "assets/images/01.png",
                "options_considered": [{
                    "option_id": "approved",
                    "label": "批准",
                    "score": 1.0,
                    "reason": "已批准其它事项。",
                }],
                "selected": "approved",
                "reason": "批准。",
                "user_approved": True,
                "user_response_text": "同意。",
            }],
        }
    elif scenario.startswith("reuse-wrong-"):
        ledger = _asset_assignment_ledger(reuse=True)
        decision = {
            "decision_id": "scoped-reuse",
            "stage": "assets_gate",
            "category": "asset_decision",
            "subject": "assets/images/01.png",
            "asset_path": "assets/images/01.png",
            "beat_ids": ["S1", "S4"],
            "options_considered": [{
                "option_id": "reuse",
                "label": "精确复用",
                "score": 1.0,
                "reason": "复用指定路径到指定 Beat。",
                "action": "reuse",
            }],
            "selected": "reuse",
            "reason": "用户批准精确复用。",
            "user_approved": True,
            "user_response_text": "同意精确复用。",
        }
        decision_log = {
            "version": "1.0",
            "project_id": project_id,
            "decisions": [decision],
        }
        if scenario == "reuse-wrong-project":
            decision_log["project_id"] = "other-project"
        elif scenario == "reuse-wrong-stage":
            decision["stage"] = "brief_locked"
        elif scenario == "reuse-wrong-path":
            decision["asset_path"] = "assets/images/other.png"
        else:
            decision["beat_ids"] = ["S1"]
    elif scenario == "conflicting-i2i-source":
        ledger["planned_entries"] = [{
            "beats": ["S1"],
            "kind": "image",
            "origin": "i2i",
            "asset_source": "user_upload",
            "status": "ready",
            "review_status": "approved",
            "provider": "provider",
            "model": "model",
            "output_path": "assets/images/i2i-conflict.png",
        }]
    elif scenario == "conflicting-beat-fields":
        ledger["entries"][0]["beats"] = ["S2"]

    project = _stage_asset_assignment_gate(
        tmp_path,
        project_id,
        ledger,
        decision_log=decision_log,
    )
    if scenario == "duplicate-canonical-id":
        video_plan_path = project / "artifacts" / "video_plan.json"
        video_plan = json.loads(video_plan_path.read_text(encoding="utf-8"))
        video_plan["segments"].append({"id": "S1", "t": "30-35"})
        video_plan_path.write_text(json.dumps(video_plan), encoding="utf-8")

    with pytest.raises(CheckpointValidationError):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


@pytest.mark.parametrize(
    "status",
    ["pending_user_confirmation", "pending", "rejected", "failed"],
)
def test_assets_gate_completed_rejects_open_unused_ledger_entries(
    tmp_path: Path,
    status: str,
) -> None:
    project_id = f"open-unused-{status}"
    ledger = _asset_assignment_ledger()
    ledger["entries"].append({
        "path": "assets/images/open-unused.png",
        "kind": "image",
        "user_class": "product_hero",
        "status": status,
    })
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)

    with pytest.raises(CheckpointValidationError):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_rejects_real_image_missing_from_ledger(
    tmp_path: Path,
) -> None:
    from PIL import Image

    project_id = "untracked-real-image"
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    untracked = project / "assets" / "images" / "untracked.webp"
    untracked.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), "white").save(untracked)

    with pytest.raises(
        CheckpointValidationError,
        match="未登记真实图片",
    ):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


@pytest.mark.parametrize(
    ("filename", "image_format"),
    [
        ("untracked.bmp", "BMP"),
        ("nested/untracked.tiff", "TIFF"),
    ],
)
def test_assets_gate_completed_rejects_scan_supported_image_missing_from_ledger(
    tmp_path: Path,
    filename: str,
    image_format: str,
) -> None:
    from PIL import Image

    project_id = f"untracked-{image_format.lower()}"
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    untracked = project / "assets" / "images" / filename
    untracked.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), "white").save(untracked, format=image_format)

    with pytest.raises(
        CheckpointValidationError,
        match="未登记真实图片",
    ):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_rejects_untracked_valid_svg(
    tmp_path: Path,
) -> None:
    project_id = "untracked-svg"
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    untracked = project / "assets" / "images" / "untracked.svg"
    untracked.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600">'
        '<rect width="800" height="600"/></svg>',
        encoding="utf-8",
    )

    with pytest.raises(
        CheckpointValidationError,
        match="未登记真实图片",
    ):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_ignores_fake_svg_extension(
    tmp_path: Path,
) -> None:
    project_id = "fake-svg"
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    (project / "assets" / "images" / "fake.svg").write_text(
        "<html><body>not an svg</body></html>",
        encoding="utf-8",
    )

    validate_checkpoint(
        _commercial_checkpoint(
            "assets_gate",
            {"asset_ledger": ledger},
            status="completed",
            project_id=project_id,
        ),
        project_dir=project,
    )


@pytest.mark.parametrize("accounted", [False, True])
def test_assets_gate_completed_rejects_dangerous_svg_even_when_accounted(
    tmp_path: Path,
    accounted: bool,
) -> None:
    project_id = f"dangerous-svg-{'accounted' if accounted else 'untracked'}"
    ledger = _asset_assignment_ledger()
    dangerous_path = "assets/images/dangerous.svg"
    if accounted:
        ledger["entries"][0]["path"] = dangerous_path
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    (project / dangerous_path).write_text(
        '<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///secret.txt">]>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">'
        "<text>&xxe;</text></svg>",
        encoding="utf-8",
    )

    with pytest.raises(
        CheckpointValidationError,
        match="危险 SVG",
    ):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


@pytest.mark.parametrize("accounted", [False, True])
def test_assets_gate_completed_rejects_oversized_svg_even_when_accounted(
    tmp_path: Path,
    accounted: bool,
) -> None:
    project_id = f"oversized-svg-{'accounted' if accounted else 'untracked'}"
    ledger = _asset_assignment_ledger()
    oversized_path = "assets/images/oversized.svg"
    if accounted:
        ledger["entries"][0]["path"] = oversized_path
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    with (project / oversized_path).open("wb") as stream:
        stream.seek(asset_precheck_lib._MAX_SVG_BYTES)
        stream.write(b"x")

    with pytest.raises(
        CheckpointValidationError,
        match="过大 SVG",
    ):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_rejects_assigned_file_with_fake_image_bytes(
    tmp_path: Path,
) -> None:
    project_id = "assigned-fake-image"
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    (project / "assets" / "images" / "S1.png").write_bytes(b"not-an-image")

    with pytest.raises(
        CheckpointValidationError,
        match="有效图片|图片内容",
    ):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_accounts_generated_source_candidate_and_output_paths(
    tmp_path: Path,
) -> None:
    from PIL import Image

    project_id = "generated-path-accounting"
    ledger = _asset_assignment_ledger()
    ledger["entries"][0].update({
        "origin": "generated",
        "provider": "provider",
        "model": "model",
        "review_status": "approved",
        "decision_id": "d-generated-review",
        "source_paths": ["assets/images/source-reference.png"],
        "candidate_paths": [
            "assets/images/S1.png",
            "assets/images/generated-candidate.png",
        ],
        "planned_output_path": "assets/images/generated-planned.png",
        "output_path": "assets/images/S1.png",
    })
    project = _stage_asset_assignment_gate(
        tmp_path,
        project_id,
        ledger,
        decision_log=_generated_review_decision_log(
            project_id,
            "assets/images/S1.png",
            ["S1"],
        ),
    )
    for relative_path in (
        "assets/images/S1.png",
        "assets/images/source-reference.png",
        "assets/images/generated-candidate.png",
        "assets/images/generated-planned.png",
    ):
        target = project / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (800, 600), "white").save(target)
    (project / "assets" / "images" / "notes.txt").write_text(
        "non-image files are outside the ledger contract",
        encoding="utf-8",
    )

    validate_checkpoint(
        _commercial_checkpoint(
            "assets_gate",
            {"asset_ledger": ledger},
            status="completed",
            project_id=project_id,
        ),
        project_dir=project,
    )


def test_assets_gate_completed_rejects_unused_actual_without_explanation(
    tmp_path: Path,
) -> None:
    project_id = "unused-without-explanation"
    ledger = _asset_assignment_ledger()
    ledger["entries"].append({
        "path": "assets/images/unused.png",
        "kind": "image",
        "user_class": "product_detail",
        "status": "confirmed",
        "selected": False,
    })
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)

    with pytest.raises(CheckpointValidationError) as exc_info:
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )
    assert "asset_ledger" in str(exc_info.value)


def test_assets_gate_completed_rejects_rejected_unused_actual_without_reason(
    tmp_path: Path,
) -> None:
    project_id = "unused-rejected-explanation"
    ledger = _asset_assignment_ledger()
    ledger["entries"].append({
        "path": "assets/images/rejected-unused.png",
        "kind": "image",
        "user_class": "product_detail",
        "status": "rejected",
        "selected": False,
    })
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)

    with pytest.raises(CheckpointValidationError):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_uses_latest_decision_across_all_log_copies(
    tmp_path: Path,
) -> None:
    project_id = "latest-decision-across-copies"
    output_path = "assets/images/i2i-S6.png"
    ledger = _asset_assignment_ledger(i2i_review_status="approved")
    old_approval = _generated_review_decision_log(
        project_id,
        output_path,
        ["S6"],
        decision_id="d-i2i-review-S6",
    )
    latest_rejection = _generated_review_decision_log(
        project_id,
        output_path,
        ["S6"],
        decision_id="d-i2i-review-rejected",
        decision_patch={
            "options_considered": [{
                "option_id": "rejected",
                "label": "撤回生成图",
                "score": 1.0,
                "reason": "用户撤回先前批准。",
            }],
            "selected": "rejected",
            "reason": "用户要求不再采用该图。",
            "user_response_text": "撤回这张图。",
        },
    )
    latest_rejection["decisions"].insert(
        0,
        old_approval["decisions"][0],
    )
    project = _stage_asset_assignment_gate(
        tmp_path,
        project_id,
        ledger,
        decision_log=latest_rejection,
    )

    with pytest.raises(
        CheckpointValidationError,
        match=r"review|审图|批准",
    ):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {
                    "asset_ledger": ledger,
                    "decision_log": old_approval,
                },
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_rejects_divergent_decision_log_copies(
    tmp_path: Path,
) -> None:
    project_id = "divergent-decision-copies"
    path = "assets/images/S1.png"
    inline_log = _generated_review_decision_log(
        project_id,
        path,
        ["S1"],
        decision_id="d-inline",
    )
    file_log = _generated_review_decision_log(
        project_id,
        path,
        ["S1"],
        decision_id="d-file",
    )
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(
        tmp_path,
        project_id,
        ledger,
        decision_log=file_log,
    )

    with pytest.raises(
        CheckpointValidationError,
        match="不是同一追加历史",
    ):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {
                    "asset_ledger": ledger,
                    "decision_log": inline_log,
                },
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_rejects_conflicting_duplicate_decision_id(
    tmp_path: Path,
) -> None:
    project_id = "conflicting-duplicate-decision"
    path = "assets/images/S1.png"
    inline_log = _generated_review_decision_log(
        project_id,
        path,
        ["S1"],
        decision_id="d-shared",
    )
    file_log = _generated_review_decision_log(
        project_id,
        path,
        ["S1"],
        decision_id="d-shared",
        decision_patch={"reason": "同一 ID 的冲突内容。"},
    )
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(
        tmp_path,
        project_id,
        ledger,
        decision_log=file_log,
    )

    with pytest.raises(
        CheckpointValidationError,
        match="同一 decision_id 内容不一致",
    ):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {
                    "asset_ledger": ledger,
                    "decision_log": inline_log,
                },
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


@pytest.mark.parametrize("source", ["file", "inline"])
def test_assets_gate_completed_rejects_cross_project_decision_log_without_reuse_or_i2i(
    tmp_path: Path,
    source: str,
) -> None:
    project_id = f"cross-project-decision-{source}"
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    cross_project_log = {
        "version": "1.0",
        "project_id": "another-project",
        "decisions": [],
    }
    artifacts = {"asset_ledger": ledger}
    if source == "file":
        (project / "artifacts" / "decision_log.json").write_text(
            json.dumps(cross_project_log),
            encoding="utf-8",
        )
    else:
        artifacts["decision_log"] = cross_project_log

    with pytest.raises(
        CheckpointValidationError,
        match="decision_log project_id",
    ):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                artifacts,
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_allows_absent_decision_log_when_no_decision_needed(
    tmp_path: Path,
) -> None:
    project_id = "decision-log-not-needed"
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    (project / "artifacts" / "decision_log.json").unlink()

    validate_checkpoint(
        _commercial_checkpoint(
            "assets_gate",
            {"asset_ledger": ledger},
            status="completed",
            project_id=project_id,
        ),
        project_dir=project,
    )


def test_assets_gate_completed_rejects_cross_project_file_even_with_valid_inline_log(
    tmp_path: Path,
) -> None:
    project_id = "cross-project-shadowed-file"
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    valid_inline = {
        "version": "1.0",
        "project_id": project_id,
        "decisions": [],
    }
    (project / "artifacts" / "decision_log.json").write_text(
        json.dumps({
            "version": "1.0",
            "project_id": "another-project",
            "decisions": [],
        }),
        encoding="utf-8",
    )

    with pytest.raises(
        CheckpointValidationError,
        match="decision_log project_id",
    ):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {
                    "asset_ledger": ledger,
                    "decision_log": valid_inline,
                },
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


@pytest.mark.parametrize(
    ("plan_patch", "reason"),
    [
        ({"assignment_status": "missing"}, "open-status"),
        (
            {
                "assignment_status": "assigned",
                "gap_fill": "i2i",
                "asset_source": "i2i",
            },
            "source-drift",
        ),
        ({"ref": "assets/images/old-S1.png"}, "reference-drift"),
    ],
)
def test_assets_gate_completed_rejects_video_plan_matrix_drift(
    tmp_path: Path,
    plan_patch: dict,
    reason: str,
) -> None:
    project_id = f"plan-drift-{reason}"
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    plan_path = project / "artifacts" / "video_plan.json"
    video_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    video_plan["segments"][0].update(plan_patch)
    plan_path.write_text(json.dumps(video_plan), encoding="utf-8")

    with pytest.raises(CheckpointValidationError):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


@pytest.mark.parametrize("conflict", ["top-level", "inner"])
def test_assets_gate_completed_rejects_video_plan_canonical_conflicts(
    tmp_path: Path,
    conflict: str,
) -> None:
    project_id = f"plan-conflict-{conflict}"
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    plan_path = project / "artifacts" / "video_plan.json"
    video_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if conflict == "top-level":
        video_plan["beats"] = [
            *video_plan["segments"][:-1],
            {"id": "S9", "t": "25-30"},
        ]
    else:
        video_plan["segments"][0]["beat"] = "S9"
    plan_path.write_text(json.dumps(video_plan), encoding="utf-8")

    with pytest.raises(CheckpointValidationError):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_binds_checkpoint_id_to_project_marker(
    tmp_path: Path,
) -> None:
    project_id = "marker-project"
    ledger = _asset_assignment_ledger()
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)

    with pytest.raises(CheckpointValidationError):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id="forged-project",
            ),
            project_dir=project,
        )


@pytest.mark.parametrize(
    ("mutation", "remove_output"),
    [
        ({"provider": ""}, False),
        ({"model": ""}, False),
        ({"review_status": "pending"}, False),
        ({}, True),
        ({"asset_source": "user_upload"}, False),
    ],
)
def test_assets_gate_completed_rejects_incomplete_actual_i2i(
    tmp_path: Path,
    mutation: dict,
    remove_output: bool,
) -> None:
    project_id = (
        "actual-i2i-missing-output"
        if remove_output
        else "actual-i2i-" + next(iter(mutation))
    )
    ledger = _asset_assignment_ledger()
    actual_i2i = ledger["entries"][0]
    actual_i2i.update({
        "origin": "i2i",
        "provider": "provider",
        "model": "model",
        "review_status": "approved",
        "decision_id": "d-i2i-review-S1",
    })
    actual_i2i.update(mutation)
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)
    if remove_output:
        (project / actual_i2i["path"]).unlink()

    with pytest.raises(CheckpointValidationError):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_rejects_unreviewed_generated_actual(
    tmp_path: Path,
) -> None:
    project_id = "actual-generated-unreviewed"
    ledger = _asset_assignment_ledger()
    ledger["entries"][0].update({
        "origin": "generated",
        "provider": "provider",
        "model": "model",
    })
    project = _stage_asset_assignment_gate(tmp_path, project_id, ledger)

    with pytest.raises(CheckpointValidationError):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


@pytest.mark.parametrize(
    "scenario",
    ["fake-decision-id", "empty-candidates", "decision-scope-mismatch"],
)
def test_assets_gate_completed_rejects_unverifiable_generated_approval(
    tmp_path: Path,
    scenario: str,
) -> None:
    project_id = f"generated-{scenario}"
    output_path = "assets/images/S1.png"
    ledger = _asset_assignment_ledger()
    generated = ledger["entries"][0]
    generated.update({
        "origin": "generated",
        "provider": "provider",
        "model": "model",
        "review_status": "approved",
        "decision_id": "d-generated-review",
        "candidate_paths": [output_path],
    })
    decision_patch = None
    if scenario == "fake-decision-id":
        generated["decision_id"] = "missing-decision"
    elif scenario == "empty-candidates":
        generated["candidate_paths"] = []
    else:
        decision_patch = {"beat_ids": ["S2"]}
    decision_log = _generated_review_decision_log(
        project_id,
        output_path,
        ["S1"],
        decision_patch=decision_patch,
    )
    project = _stage_asset_assignment_gate(
        tmp_path,
        project_id,
        ledger,
        decision_log=decision_log,
    )

    with pytest.raises(CheckpointValidationError):
        validate_checkpoint(
            _commercial_checkpoint(
                "assets_gate",
                {"asset_ledger": ledger},
                status="completed",
                project_id=project_id,
            ),
            project_dir=project,
        )


def test_assets_gate_completed_accepts_verifiable_generated_approval(
    tmp_path: Path,
) -> None:
    project_id = "generated-review-valid"
    output_path = "assets/images/S1.png"
    ledger = _asset_assignment_ledger()
    ledger["entries"][0].update({
        "origin": "generated",
        "provider": "provider",
        "model": "model",
        "review_status": "approved",
        "decision_id": "d-generated-review",
        "candidate_paths": [output_path],
    })
    decision_log = _generated_review_decision_log(
        project_id,
        output_path,
        ["S1"],
    )
    project = _stage_asset_assignment_gate(
        tmp_path,
        project_id,
        ledger,
        decision_log=decision_log,
    )

    validate_checkpoint(
        _commercial_checkpoint(
            "assets_gate",
            {"asset_ledger": ledger},
            status="completed",
            project_id=project_id,
        ),
        project_dir=project,
    )


def test_assets_gate_completed_accepts_complete_actual_i2i(
    tmp_path: Path,
) -> None:
    project_id = "actual-i2i-complete"
    output_path = "assets/images/S1.png"
    ledger = _asset_assignment_ledger()
    ledger["entries"][0].update({
        "origin": "i2i",
        "provider": "provider",
        "model": "model",
        "review_status": "approved",
        "decision_id": "d-i2i-review-S1",
        "candidate_paths": [output_path],
    })
    decision_log = _generated_review_decision_log(
        project_id,
        output_path,
        ["S1"],
        decision_id="d-i2i-review-S1",
    )
    project = _stage_asset_assignment_gate(
        tmp_path,
        project_id,
        ledger,
        decision_log=decision_log,
    )

    validate_checkpoint(
        _commercial_checkpoint(
            "assets_gate",
            {"asset_ledger": ledger},
            status="completed",
            project_id=project_id,
        ),
        project_dir=project,
    )


def test_assets_gate_completed_allows_closed_assignment_matrix(
    tmp_path: Path,
) -> None:
    ledger = _asset_assignment_ledger(
        reuse=True,
        i2i_review_status="approved",
    )
    decision_log = {
        "version": "1.0",
        "project_id": "closed",
        "decisions": [{
            "decision_id": "d-asset-reuse-01",
            "stage": "assets_gate",
            "category": "asset_decision",
            "subject": "assets/images/01.png",
            "asset_path": "assets/images/01.png",
            "beat_ids": ["S1", "S4"],
            "options_considered": [
                {
                    "option_id": "approved",
                    "label": "批准跨 Beat 复用",
                    "score": 1.0,
                    "reason": "同一真实商品图可覆盖 S1 与 S4。",
                    "action": "reuse",
                },
                {
                    "option_id": "rejected",
                    "label": "不复用并补图",
                    "score": 0.4,
                    "reason": "可避免重复，但当前闭环无需新增图片。",
                    "rejected_because": "用户已批准复用现有真实商品图。",
                    "action": "do_not_reuse",
                },
            ],
            "selected": "approved",
            "reason": "用户确认 01.png 可同时用于 S1 与 S4。",
            "user_visible": True,
            "user_approved": True,
            "user_response_text": "同意 01.png 在 S1 与 S4 复用。",
        }],
    }
    decision_log["decisions"].append(
        _generated_review_decision_log(
            "closed",
            "assets/images/i2i-S6.png",
            ["S6"],
            decision_id="d-i2i-review-S6",
        )["decisions"][0]
    )
    project = _stage_asset_assignment_gate(
        tmp_path,
        "closed",
        ledger,
        decision_log=decision_log,
    )

    validate_checkpoint(
        _commercial_checkpoint(
            "assets_gate",
            {"asset_ledger": ledger},
            status="completed",
            project_id="closed",
        ),
        project_dir=project,
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

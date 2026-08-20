"""Tripwires for the commercial asset-assignment Skill protocol."""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest

from lib.asset_precheck import validate_beat_assignment_matrix
from schemas.artifacts import validate_artifact


ROOT = Path(__file__).resolve().parents[2]
USERCHECK_DIR = (
    ROOT / "skills" / "bootstrap" / "openmontage-bootstrap-03-usercheck"
)
USERCHECK = USERCHECK_DIR / "SKILL.md"
ASSET_GATE = USERCHECK_DIR / "references" / "asset-preprocess-gate.md"
FAST_REFERENCE = (
    USERCHECK_DIR / "references" / "commercial-video-15s-review.md"
)
PRODUCE = (
    ROOT
    / "skills"
    / "bootstrap"
    / "openmontage-bootstrap-04-produce"
    / "SKILL.md"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json_after(text: str, heading: str) -> dict:
    pattern = rf"{re.escape(heading)}.*?```json\s*(.*?)\s*```"
    match = re.search(pattern, text, flags=re.DOTALL)
    assert match, f"missing JSON example after heading: {heading}"
    return json.loads(match.group(1))


def test_usercheck_requires_closed_beat_asset_matrix_before_table_3() -> None:
    text = _read(USERCHECK) + _read(ASSET_GATE)
    for token in (
        "beat × 所需画面 × 候选图片",
        "used",
        "reuse_pending",
        "unused",
        "补传",
        "I2I",
        "显式复用",
        "降级/不补",
        "assets_gate=completed",
    ):
        assert token in text
    assert "总张数够" in text and "关键角度" in text
    assert "video provider" in text and "Pixverse" in text


def test_i2i_lifecycle_and_review_gate_are_explicit_for_every_mode() -> None:
    text = _read(USERCHECK) + _read(ASSET_GATE) + _read(FAST_REFERENCE)
    for token in (
        "planned→generating→ready/review_pending→approved|rejected|failed",
        "copy_plan_zh",
        "shot_plan_zh",
        "asset_plan_zh",
        "candidate_paths",
        "retry_count",
        "decision_id",
        "output_path",
        "普通模式",
        "专业模式",
        "快速模式",
        "未经 approved",
    ):
        assert token in text
    assert "assets_gate 内部子闸" in text
    assert "不是第八阶段" in text


def test_fast_mode_cannot_replace_generated_image_review() -> None:
    text = _read(FAST_REFERENCE)

    for token in (
        "无生成图",
        "所有生成图",
        "review_status=\"approved\"",
        "普通模式批量审图",
        "专业模式逐张审图",
        "快速授权不能替代",
    ):
        assert token in text


def test_generated_actual_without_review_is_rejected_by_real_validator(
    tmp_path: Path,
) -> None:
    output_path = "assets/images/generated.png"
    real_output = tmp_path / output_path
    real_output.parent.mkdir(parents=True)
    real_output.write_bytes(b"generated-image")

    result = validate_beat_assignment_matrix(
        canonical_beat_ids=["B01"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["B01"],
            "status": "confirmed",
            "origin": "generated",
            "provider": "provider",
            "model": "model",
        }],
        project_dir=tmp_path,
    )

    assert result["ready"] is False
    assert "review_not_approved" in result["i2i_issues"][0]["reasons"]


def test_generated_approval_requires_real_candidates_and_scoped_decision() -> None:
    text = _read(USERCHECK) + _read(ASSET_GATE) + _read(PRODUCE)

    for token in (
        "candidate_paths` 非空",
        "批准输出必须属于 `candidate_paths`",
        "decision_id` 必须命中当前 `decision_log",
        "selected=\"approved\"",
        "asset_path` / `subject",
        "beat_ids",
        "计划 decision_id",
    ):
        assert token in text


def test_completed_asset_gate_documents_source_reference_and_inventory_closure() -> None:
    text = _read(USERCHECK) + _read(ASSET_GATE) + _read(PRODUCE)

    for token in (
        "planned image 来源声明",
        "planned_output / output / candidates / provider / model",
        "ref / ref_image",
        "唯一批准路径",
        "Beat + path",
        "未登记真实图片",
        "source / candidate / output",
        "decision_log 文件不存在",
        "跨项目 decision_log",
        "actual 生成链信号",
        "BMP / TIFF",
        "任何 planned image",
        "SVG 根元素",
        "外部实体",
        "has_generation_chain_signal",
        "unsafe_svg_declaration",
        "无论是否入账",
        "svg_too_large",
        "不读取全文件",
    ):
        assert token in text


def test_i2i_gap_is_planned_before_ref_image_is_assigned() -> None:
    text = _read(USERCHECK) + _read(ASSET_GATE) + _read(PRODUCE)

    for token in (
        "gap_fill=\"i2i\"",
        "assignment_status=\"i2i_planned\"",
        "planned_output_path",
        "ref_image` 可省略",
        "审图 approved 后",
    ):
        assert token in text


def test_i2i_planned_video_plan_state_matches_schema() -> None:
    validate_artifact("video_plan", {
        "segments": [{
            "id": "B03",
            "gap_fill": "i2i",
            "asset_source": "i2i",
            "assignment_status": "i2i_planned",
            "planned_output_path": "assets/images/i2i-B03.png",
            "provider": "image-provider",
            "model": "image-model",
        }],
    })


def test_asset_ledger_schema_rejects_planned_image_without_source_declaration() -> None:
    ledger = {
        "version": "1.0",
        "entries": [],
        "planned_entries": [{
            "beat": "B03",
            "kind": "image",
            "status": "approved",
            "output_path": "assets/images/i2i-B03.png",
        }],
        "summary": {
            "available_image_count": 0,
            "counts_by_class": {},
            "status_zh": "等待用户选择",
        },
    }

    with pytest.raises(jsonschema.ValidationError):
        validate_artifact("asset_ledger", ledger)


def test_asset_ledger_schema_rejects_actual_generation_signal_without_source() -> None:
    ledger = {
        "version": "1.0",
        "entries": [{
            "path": "assets/images/generated.png",
            "user_class": "product_hero",
            "status": "confirmed",
            "selected": True,
            "decision_id": "fake-decision",
        }],
        "summary": {
            "available_image_count": 1,
            "counts_by_class": {"product_hero": 1},
            "status_zh": "就绪",
        },
    }

    with pytest.raises(jsonschema.ValidationError):
        validate_artifact("asset_ledger", ledger)


def test_asset_ledger_schema_requires_unused_actual_explanation() -> None:
    ledger = {
        "version": "1.0",
        "entries": [{
            "path": "assets/images/unused.png",
            "user_class": "product_detail",
            "status": "confirmed",
            "selected": False,
        }],
        "summary": {
            "available_image_count": 1,
            "counts_by_class": {"product_detail": 1},
            "status_zh": "就绪",
        },
    }

    with pytest.raises(jsonschema.ValidationError):
        validate_artifact("asset_ledger", ledger)

    ledger["entries"][0]["note_zh"] = "当前分镜不使用这张细节图。"
    validate_artifact("asset_ledger", ledger)


@pytest.mark.parametrize("status", ["ready", "approved"])
def test_asset_ledger_schema_accepts_legacy_closed_user_upload_status(status) -> None:
    validate_artifact("asset_ledger", {
        "version": "1.0",
        "entries": [{
            "path": "assets/images/uploaded.png",
            "user_class": "product_hero",
            "status": status,
            "selected": True,
            "beats": ["S1"],
            "kind": "image",
            "origin": "user_upload",
        }],
        "summary": {
            "available_image_count": 1,
            "counts_by_class": {"product_hero": 1},
            "status_zh": "就绪",
        },
    })


def test_produce_rechecks_closed_matrix_before_start_and_paid_video_calls() -> None:
    text = _read(PRODUCE)
    for token in (
        "unified matrix",
        "asset_ledger",
        "missing",
        "orphan",
        "reuse_pending",
        "review_pending",
        "provider_missing",
        "file_missing",
        "assets_gate=completed",
        "每次付费视频调用前",
    ):
        assert token in text
    assert "只读取 approved" in text
    assert "退回 03" in text


def test_documented_asset_and_decision_examples_match_current_schemas() -> None:
    text = _read(ASSET_GATE)
    ledger = _json_after(text, "#### Schema-valid 最小 planned entry")
    reuse = _json_after(text, "#### Schema-valid 复用 decision")
    review = _json_after(text, "#### Schema-valid 审图 decision")
    fast_track = _json_after(
        _read(FAST_REFERENCE),
        "只有用户回复包含上述",
    )

    validate_artifact("asset_ledger", ledger)
    validate_artifact("decision_log", reuse)
    validate_artifact("decision_log", review)
    validate_artifact("decision_log", fast_track)

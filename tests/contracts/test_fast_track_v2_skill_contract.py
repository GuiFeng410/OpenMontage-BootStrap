"""Tripwires for the Backlot panel-intent and fast-track v2 Skill protocol."""

from __future__ import annotations

import json
import re
from pathlib import Path

from schemas.artifacts import validate_artifact


ROOT = Path(__file__).resolve().parents[2]
USERCHECK_DIR = (
    ROOT / "skills" / "bootstrap" / "openmontage-bootstrap-03-usercheck"
)
USERCHECK = USERCHECK_DIR / "SKILL.md"
FAST_REFERENCE = USERCHECK_DIR / "references" / "commercial-video-15s-review.md"
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


def test_usercheck_documents_panel_intent_confirmation_and_fallback() -> None:
    text = _read(USERCHECK) + _read(FAST_REFERENCE)

    for token in (
        "确认面板选择",
        "提交待确认",
        "produce_list_interaction_intents",
        "produce_plan_approval_bundle",
        "produce_apply_approval_bundle",
        "fast_track_v2",
        "approval_bundle",
        "decision",
    ):
        assert token in text
    assert "完整确认卡" in text or "Grill" in text
    assert "提升" in text or "生成" in text
    assert "直接出片" in text and (
        "不是审批证据" in text or "不是全程预授权" in text
    )


def test_produce_documents_fast_track_v2_evaluate_loop_and_paid_pause() -> None:
    text = _read(PRODUCE)

    for token in (
        "produce_fast_track_evaluate",
        "confirm_phrase",
        "signoff_ready",
        "pause",
        "continue",
        "fast_track_pause",
        "produce_write_checkpoint",
        "unit_price_cny",
    ):
        assert token in text
    assert "直接出片" in text and "审批证据" in text
    assert "pause" in text and "禁止" in text and "付费" in text


def test_produce_skips_to_evaluate_when_fast_track_v2_already_applied() -> None:
    text = _read(PRODUCE)

    assert "已 apply" in text
    assert "从 produce_fast_track_evaluate" in text
    assert "selected=fast_track_v2" in text or 'selected="fast_track_v2"' in text
    assert "无 intent 不得推进" not in text
    assert "当前无 intent 时不得推进" not in text


def test_v1_protocol_headings_remain_visible() -> None:
    assert "快速模式 v1.0" in _read(FAST_REFERENCE)
    assert "快速模式 v1.0" in _read(PRODUCE)


def test_fast_track_v2_decision_example_matches_current_schema() -> None:
    decision_log = _json_after(
        _read(FAST_REFERENCE),
        "#### Schema-valid 快速模式 v2 decision_log 示例",
    )

    validate_artifact("decision_log", decision_log)
    assert decision_log["decisions"][0]["selected"] == "fast_track_v2"

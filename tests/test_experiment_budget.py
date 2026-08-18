"""Tests for experimental API budget helpers and profile merge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.experiment_budget import (
    clamp_ai_share_pct,
    format_motion_mix_zh,
    merge_experiment_fields_into_profile,
    motion_mix_from_ai_share_pct,
    motion_mix_info,
    needs_budget_choice_confirm,
    needs_single_call_cost_tip,
    normalize_motion_mix,
    recommended_ai_seconds,
    resolve_experiment_budget,
    usd_to_cny,
    would_exceed_budget_cny,
)
from openmontage.mcp.bootstrap.tools import (
    produce_budget_cny_snapshot,
    produce_init_project,
    produce_set_production_profile,
)


@pytest.fixture
def sandbox(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENMONTAGE_P1_ALLOW_WRITES", "true")
    return tmp_path


def test_default_standard_budget_is_8_cny() -> None:
    b = resolve_experiment_budget(None)
    assert b.api_budget_tier == "standard"
    assert b.budget_cny == 8
    assert b.budget_total_usd == pytest.approx(8 / 7.2, rel=1e-3)
    assert b.to_dict()["needs_choice_confirm"] is True


def test_five_budget_tiers() -> None:
    assert resolve_experiment_budget("micro").budget_cny == 1
    assert resolve_experiment_budget("lite").budget_cny == 3
    assert resolve_experiment_budget("经济").budget_cny == 5
    assert resolve_experiment_budget("充裕").budget_cny == 12
    assert resolve_experiment_budget(None, 1).api_budget_tier == "micro"


def test_budget_choice_confirm_threshold() -> None:
    assert needs_budget_choice_confirm(5) is False
    assert needs_budget_choice_confirm(8) is True
    assert needs_budget_choice_confirm(12) is True


def test_single_call_tip_is_per_call_not_cumulative() -> None:
    assert needs_single_call_cost_tip(4.9) is False
    assert needs_single_call_cost_tip(5.0) is True
    assert needs_single_call_cost_tip(next_estimate_usd=0.7, usd_cny_rate=7.2) is True  # 5.04


def test_gate_trips_when_projected_over_cap() -> None:
    exceeded, detail = would_exceed_budget_cny(
        spent_usd=1.0,
        reserved_usd=0.0,
        next_estimate_usd=0.2,
        budget_cny=8,
        usd_cny_rate=7.2,
    )
    # 1.2 USD * 7.2 = 8.64 > 8
    assert exceeded is True
    assert detail["options_zh"]
    assert detail["single_call_tip"]["tip_required"] is False  # 0.2*7.2=1.44 < 5


def test_cny_display_uses_usd_ledger() -> None:
    assert usd_to_cny(1.0, 7.2) == 7.2


def test_motion_mix_defaults_and_soft_plan() -> None:
    assert normalize_motion_mix(None) == "0:1"
    assert motion_mix_info("2:1")["warn_slideshow"] is True
    plan = recommended_ai_seconds(60, "1:1")
    assert plan["ai_seconds_target"] == 30
    assert plan["ai_seconds_min"] == 21
    assert plan["ai_seconds_max"] == 39


def test_ai_share_pct_maps_to_planned_mix() -> None:
    assert clamp_ai_share_pct(57) == 60
    assert clamp_ai_share_pct(None) == 100
    assert motion_mix_from_ai_share_pct(50) == "1:1"
    assert motion_mix_from_ai_share_pct(70) == "1:2"
    assert motion_mix_from_ai_share_pct(100) == "0:1"
    assert motion_mix_from_ai_share_pct(30) == "2:1"
    assert format_motion_mix_zh(ai_share_pct=70) == "AI 约 70% / 运镜约 30%"
    assert format_motion_mix_zh(motion_mix="1:1") == "AI 约 50% / 运镜约 50%"
    plan = recommended_ai_seconds(20, "1:1", ai_share_pct=70)
    assert plan["ai_seconds_target"] == 14.0


def test_merge_defaults_review_and_candidate() -> None:
    profile = merge_experiment_fields_into_profile(
        {"production_tier": "heavy", "visual_source": "paid_gen", "tts_source": "paid"}
    )
    assert profile["review_mode"] == "normal"
    assert profile["candidate_mode"] == "adaptive"
    assert profile["budget_cny"] == 8
    assert profile["pricing_note"] == "experimental_api_budget_cap_not_selling_price"
    assert profile["is_hard_gate"] is False
    assert profile["motion_mix"] == "0:1"
    assert profile["motion_mix_source"] == "default_recommend"
    assert profile["label_zh"] == "标准"
    assert profile["motion_mix_label_zh"] == "默认（几乎全 AI）"


def test_set_profile_persists_experiment_fields(sandbox: Path) -> None:
    produce_init_project("exp1", "Exp", "animated-explainer")
    result = produce_set_production_profile(
        "exp1",
        "heavy",
        api_budget_tier="standard",
        budget_cny="8",
        review_mode="normal",
        candidate_mode="adaptive",
        motion_target_band="60s_high_motion",
        motion_mix="1:2",
        motion_mix_source="user_selected",
        duration_seconds="60",
    )
    profile = result["production_profile"]
    assert profile["production_tier"] == "heavy"
    assert profile["budget_cny"] == 8
    assert profile["review_mode"] == "normal"
    assert profile["motion_target_band"] == "60s_high_motion"
    assert profile["motion_mix"] == "1:2"
    assert profile["motion_mix_source"] == "user_selected"
    assert profile["ai_share_pct"] == 70
    marker = json.loads((sandbox / "exp1" / "project.json").read_text(encoding="utf-8"))
    assert marker["production_profile"]["api_budget_tier"] == "standard"
    assert marker["production_profile"]["motion_mix"] == "1:2"


def test_budget_snapshot_gate(sandbox: Path) -> None:
    produce_init_project("exp2", "Exp2", "animated-explainer")
    produce_set_production_profile("exp2", "heavy", api_budget_tier="economy", budget_cny="5")
    ok = produce_budget_cny_snapshot("exp2", spent_usd=0.1, reserved_usd=0.0, next_estimate_usd=0.1)
    assert ok["allow_paid_call"] is True
    blocked = produce_budget_cny_snapshot(
        "exp2", spent_usd=0.6, reserved_usd=0.0, next_estimate_usd=0.2
    )
    # 0.8 * 7.2 = 5.76 > 5
    assert blocked["allow_paid_call"] is False


def test_budget_snapshot_single_call_tip(sandbox: Path) -> None:
    produce_init_project("exp3", "Exp3", "animated-explainer")
    produce_set_production_profile("exp3", "heavy", api_budget_tier="standard", budget_cny="8")
    # 0.8 USD * 7.2 = 5.76 >= 5 tip, but under ¥8 cap
    tippy = produce_budget_cny_snapshot(
        "exp3", spent_usd=0.0, reserved_usd=0.0, next_estimate_usd=0.8
    )
    assert tippy["allow_paid_call"] is True
    assert tippy["single_call_tip"]["tip_required"] is True

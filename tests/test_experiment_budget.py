"""Tests for experimental API budget helpers and profile merge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.experiment_budget import (
    merge_experiment_fields_into_profile,
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


def test_zh_tier_aliases() -> None:
    assert resolve_experiment_budget("经济").budget_cny == 5
    assert resolve_experiment_budget("充裕").budget_cny == 12


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


def test_cny_display_uses_usd_ledger() -> None:
    assert usd_to_cny(1.0, 7.2) == 7.2


def test_merge_defaults_review_and_candidate() -> None:
    profile = merge_experiment_fields_into_profile(
        {"production_tier": "heavy", "visual_source": "paid_gen", "tts_source": "paid"}
    )
    assert profile["review_mode"] == "normal"
    assert profile["candidate_mode"] == "adaptive"
    assert profile["budget_cny"] == 8
    assert profile["pricing_note"] == "experimental_api_budget_cap_not_selling_price"
    assert profile["is_hard_gate"] is False


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
    )
    profile = result["production_profile"]
    assert profile["production_tier"] == "heavy"
    assert profile["budget_cny"] == 8
    assert profile["review_mode"] == "normal"
    assert profile["motion_target_band"] == "60s_high_motion"
    marker = json.loads((sandbox / "exp1" / "project.json").read_text(encoding="utf-8"))
    assert marker["production_profile"]["api_budget_tier"] == "standard"


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

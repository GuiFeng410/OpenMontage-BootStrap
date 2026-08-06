"""Experiment API budget helpers (CNY display over CostTracker USD ledger).

Single-task experimental API budget caps are NOT product prices.
All authoritative spend remains in CostTracker (USD). This module only:
- maps ¥5 / ¥8 / ¥12 tiers
- converts for display / gate checks
- records FX snapshot metadata for first-accept cost reporting
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# Experimental API generation budget caps (CNY). Not selling prices.
API_BUDGET_TIERS: dict[str, int] = {
    "economy": 5,   # 经济
    "standard": 8,  # 标准（默认）
    "ample": 12,    # 充裕
}

API_BUDGET_TIER_LABELS_ZH: dict[str, str] = {
    "economy": "经济",
    "standard": "标准",
    "ample": "充裕",
}

# Default FX for display when no live rate is configured.
DEFAULT_USD_CNY = 7.2

MOTION_TARGET_BANDS: dict[str, tuple[int, int]] = {
    "30s_ref": (8, 12),
    "60s_cost_ref": (16, 24),
    "60s_high_motion": (40, 45),
}

REVIEW_MODES = frozenset({"normal", "pro"})
CANDIDATE_MODES = frozenset({"adaptive", "stable_dual"})


@dataclass(frozen=True)
class ExperimentBudget:
    """Resolved experimental budget for one produce run."""

    api_budget_tier: str
    budget_cny: int
    usd_cny_rate: float
    budget_total_usd: float
    label_zh: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_budget_tier": self.api_budget_tier,
            "budget_cny": self.budget_cny,
            "usd_cny_rate": self.usd_cny_rate,
            "budget_total_usd": round(self.budget_total_usd, 4),
            "label_zh": self.label_zh,
            "pricing_note": "experimental_api_budget_cap_not_selling_price",
        }


def normalize_api_budget_tier(raw: str | None, *, default: str = "standard") -> str:
    text = (raw or "").strip().lower()
    aliases = {
        "经济": "economy",
        "标准": "standard",
        "充裕": "ample",
        "eco": "economy",
        "default": "standard",
        "标准（默认）": "standard",
    }
    text = aliases.get(text, text)
    if text in API_BUDGET_TIERS:
        return text
    return default


def resolve_experiment_budget(
    api_budget_tier: str | None = None,
    budget_cny: int | float | str | None = None,
    *,
    usd_cny_rate: float = DEFAULT_USD_CNY,
) -> ExperimentBudget:
    """Resolve tier + CNY cap; USD ceiling is derived for CostTracker."""
    rate = float(usd_cny_rate) if usd_cny_rate and float(usd_cny_rate) > 0 else DEFAULT_USD_CNY
    tier = normalize_api_budget_tier(api_budget_tier)
    if budget_cny is not None and str(budget_cny).strip() != "":
        cny = int(float(budget_cny))
        # Prefer explicit CNY if it matches a known tier; else keep tier label, use CNY.
        for name, value in API_BUDGET_TIERS.items():
            if value == cny:
                tier = name
                break
    else:
        cny = API_BUDGET_TIERS[tier]
    return ExperimentBudget(
        api_budget_tier=tier,
        budget_cny=cny,
        usd_cny_rate=rate,
        budget_total_usd=round(cny / rate, 4),
        label_zh=API_BUDGET_TIER_LABELS_ZH.get(tier, tier),
    )


def usd_to_cny(amount_usd: float, usd_cny_rate: float = DEFAULT_USD_CNY) -> float:
    rate = float(usd_cny_rate) if usd_cny_rate > 0 else DEFAULT_USD_CNY
    return round(float(amount_usd) * rate, 4)


def cny_display_snapshot(
    tracker_snapshot: Mapping[str, Any],
    *,
    usd_cny_rate: float = DEFAULT_USD_CNY,
    budget_cny: int | None = None,
) -> dict[str, Any]:
    """CNY view over CostTracker.cost_snapshot() — does not replace the USD ledger."""
    spent_usd = float(tracker_snapshot.get("total_spent_usd") or 0.0)
    reserved_usd = float(tracker_snapshot.get("total_reserved_usd") or 0.0)
    remaining_usd = float(tracker_snapshot.get("budget_remaining_usd") or 0.0)
    spent_cny = usd_to_cny(spent_usd, usd_cny_rate)
    reserved_cny = usd_to_cny(reserved_usd, usd_cny_rate)
    out: dict[str, Any] = {
        "currency_display": "CNY",
        "ledger_currency": "USD",
        "usd_cny_rate": usd_cny_rate,
        "total_spent_usd": round(spent_usd, 4),
        "total_spent_cny": spent_cny,
        "total_reserved_usd": round(reserved_usd, 4),
        "total_reserved_cny": reserved_cny,
        "budget_remaining_usd": round(remaining_usd, 4),
        "budget_remaining_cny": usd_to_cny(remaining_usd, usd_cny_rate),
    }
    if budget_cny is not None:
        out["budget_cny"] = int(budget_cny)
        out["budget_remaining_vs_cap_cny"] = round(float(budget_cny) - spent_cny - reserved_cny, 4)
    return out


def would_exceed_budget_cny(
    *,
    spent_usd: float,
    reserved_usd: float,
    next_estimate_usd: float,
    budget_cny: int,
    usd_cny_rate: float = DEFAULT_USD_CNY,
) -> tuple[bool, dict[str, Any]]:
    """Gate check before a paid call. True => stop and offer options."""
    projected_usd = float(spent_usd) + float(reserved_usd) + float(next_estimate_usd)
    projected_cny = usd_to_cny(projected_usd, usd_cny_rate)
    exceeded = projected_cny > float(budget_cny) + 1e-9
    detail = {
        "exceeded": exceeded,
        "budget_cny": int(budget_cny),
        "projected_spend_cny": projected_cny,
        "projected_spend_usd": round(projected_usd, 4),
        "usd_cny_rate": usd_cny_rate,
        "options_zh": [
            "回退到已批准静帧/Remotion",
            "升实验档（经济→标准→充裕）",
            "降低 AI 动态占比后继续",
        ],
    }
    return exceeded, detail


def normalize_review_mode(raw: str | None, *, default: str = "normal") -> str:
    text = (raw or "").strip().lower()
    aliases = {
        "普通": "normal",
        "标准": "normal",
        "专业": "pro",
        "professional": "pro",
        "pro_mode": "pro",
    }
    text = aliases.get(text, text)
    return text if text in REVIEW_MODES else default


def normalize_candidate_mode(raw: str | None, *, default: str = "adaptive") -> str:
    text = (raw or "").strip().lower()
    aliases = {
        "自适应": "adaptive",
        "稳定": "stable_dual",
        "双候选": "stable_dual",
        "dual": "stable_dual",
        "stable": "stable_dual",
    }
    text = aliases.get(text, text)
    return text if text in CANDIDATE_MODES else default


def normalize_motion_target_band(raw: str | None, *, duration_seconds: int | None = None) -> str:
    text = (raw or "").strip().lower()
    aliases = {
        "16-24": "60s_cost_ref",
        "16–24": "60s_cost_ref",
        "40-45": "60s_high_motion",
        "40–45": "60s_high_motion",
        "高动态": "60s_high_motion",
        "成本对照": "60s_cost_ref",
    }
    text = aliases.get(text, text)
    if text in MOTION_TARGET_BANDS:
        return text
    if duration_seconds is not None and duration_seconds <= 35:
        return "30s_ref"
    return "60s_cost_ref"


def motion_target_range(band: str) -> dict[str, Any]:
    key = band if band in MOTION_TARGET_BANDS else "60s_cost_ref"
    lo, hi = MOTION_TARGET_BANDS[key]
    return {
        "motion_target_band": key,
        "true_video_seconds_target_min": lo,
        "true_video_seconds_target_max": hi,
        "is_hard_gate": False,
        "note_zh": "实验目标，非普遍质量硬门槛；不得单靠 AI 秒数否决成片",
    }


def merge_experiment_fields_into_profile(
    profile: dict[str, Any],
    *,
    api_budget_tier: str | None = None,
    budget_cny: int | float | str | None = None,
    review_mode: str | None = None,
    candidate_mode: str | None = None,
    motion_target_band: str | None = None,
    duration_seconds: int | None = None,
    usd_cny_rate: float = DEFAULT_USD_CNY,
    style_label_zh: str | None = None,
    style_playbook: str | None = None,
) -> dict[str, Any]:
    """Attach experiment fields onto an existing production_profile dict."""
    out = dict(profile)
    budget = resolve_experiment_budget(api_budget_tier, budget_cny, usd_cny_rate=usd_cny_rate)
    out.update(budget.to_dict())
    out["review_mode"] = normalize_review_mode(review_mode)
    out["candidate_mode"] = normalize_candidate_mode(candidate_mode)
    band = normalize_motion_target_band(motion_target_band, duration_seconds=duration_seconds)
    out.update(motion_target_range(band))
    if style_label_zh:
        out["style_label_zh"] = str(style_label_zh).strip()
    if style_playbook:
        out["style_playbook"] = str(style_playbook).strip()
    return out

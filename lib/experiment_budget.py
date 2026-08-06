"""Experiment API budget helpers (CNY display over CostTracker USD ledger).

Single-task experimental API budget caps are NOT product prices.
All authoritative spend remains in CostTracker (USD). This module only:
- maps ¥1 / ¥3 / ¥5 / ¥8 / ¥12 tiers
- converts for display / gate checks
- normalizes motion_mix (Remotion : AI) soft targets
- records FX snapshot metadata for first-accept cost reporting
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# Experimental API generation budget caps (CNY). Not selling prices.
API_BUDGET_TIERS: dict[str, int] = {
    "micro": 1,  # 微额
    "lite": 3,  # 轻量
    "economy": 5,  # 经济
    "standard": 8,  # 标准（默认；选档须主动询问）
    "ample": 12,  # 充裕
}

API_BUDGET_TIER_LABELS_ZH: dict[str, str] = {
    "micro": "微额",
    "lite": "轻量",
    "economy": "经济",
    "standard": "标准",
    "ample": "充裕",
}

# Selecting this CNY (or higher) requires an active ask in table 1.
BUDGET_CHOICE_CONFIRM_CNY = 8

# Single planned beat/call estimate at or above this CNY => tip only (not a hard gate).
SINGLE_CALL_COST_TIP_CNY = 5

# Default FX for display when no live rate is configured.
DEFAULT_USD_CNY = 7.2

MOTION_TARGET_BANDS: dict[str, tuple[int, int]] = {
    "30s_ref": (8, 12),
    "60s_cost_ref": (16, 24),
    "60s_high_motion": (40, 45),
}

# Remotion-move : AI-generate soft target ratios (planning guide, not final hard gate).
MOTION_MIX_OPTIONS: dict[str, dict[str, Any]] = {
    "1:1": {
        "ai_fraction": 0.5,
        "label_zh": "推荐（普通默认）",
        "warn_cost": False,
        "warn_identity": False,
        "warn_slideshow": False,
        "is_default": True,
    },
    "1:2": {
        "ai_fraction": 2 / 3,
        "label_zh": "更动感",
        "warn_cost": True,
        "warn_identity": True,
        "warn_slideshow": False,
        "is_default": False,
    },
    "0:1": {
        "ai_fraction": 1.0,
        "label_zh": "几乎全 AI",
        "warn_cost": True,
        "warn_identity": True,
        "warn_slideshow": False,
        "is_default": False,
    },
    "2:1": {
        "ai_fraction": 1 / 3,
        "label_zh": "更省可选；可能有幻灯片感",
        "warn_cost": False,
        "warn_identity": False,
        "warn_slideshow": True,
        "is_default": False,
    },
}

DEFAULT_MOTION_MIX = "1:1"
MOTION_MIX_TOLERANCE = 0.15  # ±15% of duration for "大概符合"

REVIEW_MODES = frozenset({"normal", "pro"})
CANDIDATE_MODES = frozenset({"adaptive", "stable_dual"})
MOTION_MIX_SOURCES = frozenset({"default_recommend", "user_selected"})


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
            "needs_choice_confirm": needs_budget_choice_confirm(self.budget_cny),
        }


def normalize_api_budget_tier(raw: str | None, *, default: str = "standard") -> str:
    text = (raw or "").strip().lower()
    aliases = {
        "微额": "micro",
        "轻量": "lite",
        "经济": "economy",
        "标准": "standard",
        "充裕": "ample",
        "eco": "economy",
        "default": "standard",
        "标准（默认）": "standard",
        "1": "micro",
        "3": "lite",
        "5": "economy",
        "8": "standard",
        "12": "ample",
    }
    text = aliases.get(text, text)
    if text in API_BUDGET_TIERS:
        return text
    # Legacy numeric-looking tier names
    try:
        cny = int(float(text))
        for name, value in API_BUDGET_TIERS.items():
            if value == cny:
                return name
    except (TypeError, ValueError):
        pass
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


def needs_budget_choice_confirm(budget_cny: int | float | str | None) -> bool:
    """True when table-1 budget selection must actively ask the user (¥8+)."""
    try:
        return float(budget_cny) >= float(BUDGET_CHOICE_CONFIRM_CNY) - 1e-9
    except (TypeError, ValueError):
        return True


def needs_single_call_cost_tip(
    next_estimate_cny: float | None = None,
    *,
    next_estimate_usd: float | None = None,
    usd_cny_rate: float = DEFAULT_USD_CNY,
) -> bool:
    """True when a single planned call/beat estimate is ≥ ¥5 (tip only, not a hard gate)."""
    if next_estimate_cny is not None:
        amount = float(next_estimate_cny)
    elif next_estimate_usd is not None:
        amount = usd_to_cny(float(next_estimate_usd), usd_cny_rate)
    else:
        return False
    return amount >= float(SINGLE_CALL_COST_TIP_CNY) - 1e-9


def single_call_cost_tip_payload(
    *,
    next_estimate_cny: float | None = None,
    next_estimate_usd: float | None = None,
    usd_cny_rate: float = DEFAULT_USD_CNY,
    beat_id: str = "",
) -> dict[str, Any]:
    """User-facing tip payload for a costly single planned beat/call."""
    if next_estimate_cny is None and next_estimate_usd is not None:
        next_estimate_cny = usd_to_cny(float(next_estimate_usd), usd_cny_rate)
    tip = needs_single_call_cost_tip(next_estimate_cny)
    return {
        "tip_required": tip,
        "threshold_cny": SINGLE_CALL_COST_TIP_CNY,
        "next_estimate_cny": None if next_estimate_cny is None else round(float(next_estimate_cny), 4),
        "beat_id": beat_id or None,
        "message_zh": (
            f"本段单笔计划费用约 ¥{float(next_estimate_cny):.2f}（≥¥{SINGLE_CALL_COST_TIP_CNY}），"
            "继续生成前请知悉；非强制停烧。"
            if tip and next_estimate_cny is not None
            else None
        ),
        "is_hard_gate": False,
    }


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
    next_cny = usd_to_cny(float(next_estimate_usd), usd_cny_rate)
    detail = {
        "exceeded": exceeded,
        "budget_cny": int(budget_cny),
        "projected_spend_cny": projected_cny,
        "projected_spend_usd": round(projected_usd, 4),
        "next_estimate_cny": next_cny,
        "single_call_tip": single_call_cost_tip_payload(
            next_estimate_cny=next_cny, usd_cny_rate=usd_cny_rate
        ),
        "usd_cny_rate": usd_cny_rate,
        "options_zh": [
            "回退到已批准静帧/Remotion",
            "升实验档（微额→轻量→经济→标准→充裕）",
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


def normalize_motion_mix(raw: str | None, *, default: str = DEFAULT_MOTION_MIX) -> str:
    text = (raw or "").strip().replace("：", ":").replace(" ", "")
    aliases = {
        "1比1": "1:1",
        "一半": "1:1",
        "推荐": "1:1",
        "默认": "1:1",
        "1比2": "1:2",
        "全ai": "0:1",
        "全视频": "0:1",
        "0比1": "0:1",
        "2比1": "2:1",
        "省钱": "2:1",
    }
    lowered = text.lower()
    text = aliases.get(lowered, aliases.get(text, text))
    if text in MOTION_MIX_OPTIONS:
        return text
    return default if default in MOTION_MIX_OPTIONS else DEFAULT_MOTION_MIX


def normalize_motion_mix_source(raw: str | None, *, default: str = "default_recommend") -> str:
    text = (raw or "").strip().lower()
    aliases = {
        "default": "default_recommend",
        "recommend": "default_recommend",
        "推荐": "default_recommend",
        "默认": "default_recommend",
        "user": "user_selected",
        "手动": "user_selected",
        "用户": "user_selected",
    }
    text = aliases.get(text, text)
    return text if text in MOTION_MIX_SOURCES else default


def motion_mix_info(mix: str | None = None) -> dict[str, Any]:
    key = normalize_motion_mix(mix)
    meta = MOTION_MIX_OPTIONS[key]
    ai_pct = round(float(meta["ai_fraction"]) * 100)
    remotion_pct = 100 - ai_pct if key != "0:1" else 0
    if key == "0:1":
        remotion_pct = 0
        ai_pct = 100
    return {
        "motion_mix": key,
        "ai_fraction": meta["ai_fraction"],
        "ai_share_pct": ai_pct,
        "remotion_share_pct": remotion_pct,
        "motion_mix_label_zh": meta["label_zh"],
        "warn_cost": bool(meta["warn_cost"]),
        "warn_identity": bool(meta["warn_identity"]),
        "warn_slideshow": bool(meta["warn_slideshow"]),
        "is_default_mix": bool(meta["is_default"]),
        "mix_is_hard_gate": False,
        "motion_mix_note_zh": (
            "推荐目标：表3按整片AI生成总秒数大概排布（±约15%即可）；"
            "beat可自由切分；审查中可改某段方式，终稿不强制贴死比例。"
        ),
    }


def recommended_ai_seconds(duration_seconds: int | float, motion_mix: str | None = None) -> dict[str, Any]:
    """Soft AI-second target band derived from duration × mix (±tolerance)."""
    info = motion_mix_info(motion_mix)
    duration = max(0.0, float(duration_seconds))
    target = duration * float(info["ai_fraction"])
    slack = duration * MOTION_MIX_TOLERANCE
    return {
        **info,
        "duration_seconds": duration,
        "ai_seconds_target": round(target, 2),
        "ai_seconds_min": round(max(0.0, target - slack), 2),
        "ai_seconds_max": round(min(duration, target + slack), 2),
        "tolerance": MOTION_MIX_TOLERANCE,
    }


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
    motion_mix: str | None = None,
    motion_mix_source: str | None = None,
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
    mix = normalize_motion_mix(motion_mix)
    if motion_mix_source and str(motion_mix_source).strip():
        source = normalize_motion_mix_source(motion_mix_source)
    elif motion_mix and str(motion_mix).strip() and normalize_motion_mix(motion_mix) != DEFAULT_MOTION_MIX:
        source = "user_selected"
    else:
        source = "default_recommend"
    out["motion_mix"] = mix
    out["motion_mix_source"] = source
    out.update({k: v for k, v in motion_mix_info(mix).items() if k != "motion_mix"})
    if duration_seconds is not None:
        out["motion_mix_plan"] = recommended_ai_seconds(duration_seconds, mix)
    if style_label_zh:
        out["style_label_zh"] = str(style_label_zh).strip()
    if style_playbook:
        out["style_playbook"] = str(style_playbook).strip()
    return out

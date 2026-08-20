"""User-facing confirmation stops for commercial review modes.

Machine pipeline stays seven stages. This module only decides which stages
the person must confirm, and how to label resume progress on the library.
"""

from __future__ import annotations

from typing import Any

COMMERCIAL_STAGE_ORDER = (
    "brief_locked",
    "assets_gate",
    "sample_review",
    "segment_build",
    "draft_review",
    "final_compose",
    "delivery_signoff",
)

STAGE_LABEL_ZH = {
    "brief_locked": "方案确认",
    "assets_gate": "素材检查",
    "sample_review": "试片确认",
    "segment_build": "分段制作",
    "draft_review": "初稿审查",
    "final_compose": "合成终稿",
    "delivery_signoff": "交付确认",
}

CONFIRM_STOP_IDS = {
    "minimal": ("brief_locked", "assets_gate", "delivery_signoff"),
    "normal": (
        "brief_locked",
        "assets_gate",
        "sample_review",
        "draft_review",
        "delivery_signoff",
    ),
    "pro": COMMERCIAL_STAGE_ORDER,
}

MODE_LABEL_ZH = {
    "minimal": "极简",
    "normal": "普通",
    "pro": "专业",
}

TIER_LABEL_ZH = {
    "light": "轻",
    "medium": "中",
    "heavy": "重",
}

_AUTO_GENERATE_STAGES = frozenset(
    {
        "sample_review",
        "segment_build",
        "draft_review",
        "final_compose",
    }
)


def normalize_review_preset(raw: Any) -> str | None:
    value = str(raw or "").strip()
    if value in CONFIRM_STOP_IDS:
        return value
    return None


def confirm_stop_ids(preset: str | None) -> tuple[str, ...]:
    """Legacy projects without a preset keep all seven stages visible."""
    key = normalize_review_preset(preset)
    if key is None:
        return COMMERCIAL_STAGE_ORDER
    return CONFIRM_STOP_IDS[key]


def review_mode_zh(preset: str | None, stored_review: str | None = None) -> str:
    key = normalize_review_preset(preset) or normalize_review_preset(stored_review)
    if key:
        return MODE_LABEL_ZH[key]
    return MODE_LABEL_ZH.get(str(stored_review or ""), str(stored_review or "普通"))


def production_tier_zh(raw: Any) -> str:
    value = str(raw or "").strip()
    return TIER_LABEL_ZH.get(value, value)


def user_progress(
    stages: list[dict[str, Any]],
    preset: str | None,
) -> dict[str, Any]:
    """First user-facing stop that is not completed, plus generate-in-flight."""
    by_name = {
        str(item.get("name") or ""): item
        for item in stages
        if isinstance(item, dict)
    }
    stops = confirm_stop_ids(preset)
    key = normalize_review_preset(preset)

    def status_of(name: str) -> str:
        return str((by_name.get(name) or {}).get("status") or "pending")

    assets_done = status_of("assets_gate") == "completed"
    delivery_done = status_of("delivery_signoff") == "completed"
    if key == "minimal" and assets_done and not delivery_done:
        auto_states = [status_of(name) for name in _AUTO_GENERATE_STAGES]
        if any(state == "failed" for state in auto_states):
            return {
                "stage_id": "generating",
                "label_zh": "生成失败，回聊天",
                "status": "failed",
            }
        if any(state in {"in_progress", "awaiting_human"} for state in auto_states):
            return {
                "stage_id": "generating",
                "label_zh": "生成中",
                "status": "in_progress",
            }
        return {
            "stage_id": "delivery_signoff",
            "label_zh": "待交付",
            "status": "pending",
        }

    for name in stops:
        state = status_of(name)
        if state != "completed":
            return {
                "stage_id": name,
                "label_zh": STAGE_LABEL_ZH.get(name, name),
                "status": state,
            }
    last = stops[-1]
    return {
        "stage_id": last,
        "label_zh": "已完成" if delivery_done else STAGE_LABEL_ZH.get(last, last),
        "status": "completed",
    }


def honest_user_stage_zh(
    progress: dict[str, Any],
    *,
    has_final: bool,
    producing: bool,
    paused: bool,
) -> str:
    """Library/board stop label that does not fake delivery or producing."""
    label = str((progress or {}).get("label_zh") or "")
    fake_busy = label in {"待交付", "交付确认", "生成中", "制作中"}
    if has_final:
        if label == "生成中":
            return "待交付"
        return label
    if fake_busy:
        if producing:
            return "生成中"
        return "已中断"
    return label

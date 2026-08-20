"""Chat-shaped project progress snapshot shared by MCP and later board facades."""

from __future__ import annotations

import json
from typing import Any

from lib.application.errors import ApplicationError
from lib.checkpoint import (
    PROJECT_MARKER_FILENAME,
    get_completed_stages,
    get_latest_checkpoint,
    get_next_stage,
)
from lib.error_codes import NOT_FOUND
from lib.paths import get_workspace

_PROFILE_KEYS = ("production_tier", "visual_source", "tts_source")
_PRODUCTION_TIERS = frozenset({"light", "medium", "heavy"})
_VISUAL_SOURCES = frozenset({"template", "stock", "paid_gen"})
_TTS_SOURCES = frozenset({"edge_tts", "piper", "paid"})
_TIER_DEFAULTS: dict[str, dict[str, str]] = {
    "light": {"visual_source": "template", "tts_source": "edge_tts"},
    "medium": {"visual_source": "stock", "tts_source": "edge_tts"},
    "heavy": {"visual_source": "paid_gen", "tts_source": "paid"},
}
_EXPERIMENT_PROFILE_KEYS = (
    "api_budget_tier",
    "budget_cny",
    "budget_total_usd",
    "usd_cny_rate",
    "label_zh",
    "pricing_note",
    "needs_choice_confirm",
    "review_mode",
    "candidate_mode",
    "motion_target_band",
    "true_video_seconds_target_min",
    "true_video_seconds_target_max",
    "is_hard_gate",
    "note_zh",
    "motion_mix",
    "motion_mix_source",
    "ai_fraction",
    "ai_share_pct",
    "remotion_share_pct",
    "motion_mix_label_zh",
    "warn_cost",
    "warn_identity",
    "warn_slideshow",
    "is_default_mix",
    "mix_is_hard_gate",
    "motion_mix_note_zh",
    "motion_mix_plan",
    "duration_seconds",
    "style_label_zh",
    "style_playbook",
)


class _ProfileError(Exception):
    """Invalid production_profile fields; snapshot still returns raw values."""


def _pick_profile_fields(mapping: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(mapping, dict):
        return {}
    nested = mapping.get("production_profile")
    source = nested if isinstance(nested, dict) else mapping
    out: dict[str, str] = {}
    for key in _PROFILE_KEYS:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


def _pick_experiment_fields(mapping: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}
    nested = mapping.get("production_profile")
    source = nested if isinstance(nested, dict) else mapping
    out: dict[str, Any] = {}
    for key in _EXPERIMENT_PROFILE_KEYS:
        if key not in source:
            continue
        value = source.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value
    return out


def _normalize_production_profile(
    production_tier: str,
    visual_source: str = "",
    tts_source: str = "",
) -> dict[str, str]:
    tier = (production_tier or "").strip().lower()
    if tier not in _PRODUCTION_TIERS:
        raise _ProfileError(
            f"production_tier must be one of {sorted(_PRODUCTION_TIERS)}; got {production_tier!r}"
        )
    defaults = _TIER_DEFAULTS[tier]
    visual = (visual_source or "").strip().lower() or defaults["visual_source"]
    tts = (tts_source or "").strip().lower() or defaults["tts_source"]
    if visual not in _VISUAL_SOURCES:
        raise _ProfileError(
            f"visual_source must be one of {sorted(_VISUAL_SOURCES)}; got {visual_source!r}"
        )
    if tts not in _TTS_SOURCES:
        raise _ProfileError(
            f"tts_source must be one of {sorted(_TTS_SOURCES)}; got {tts_source!r}"
        )
    return {
        "production_tier": tier,
        "visual_source": visual,
        "tts_source": tts,
    }


def resolve_production_profile(
    marker: dict[str, Any] | None,
    latest_checkpoint: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Prefer project.json profile; fall back to latest checkpoint artifacts."""
    picked = _pick_profile_fields(marker)
    experiment = _pick_experiment_fields(marker)
    if "production_tier" not in picked and isinstance(latest_checkpoint, dict):
        artifacts = latest_checkpoint.get("artifacts")
        picked = {**_pick_profile_fields(artifacts), **picked}
        experiment = {**_pick_experiment_fields(artifacts), **experiment}
    if "production_tier" not in picked:
        return None
    try:
        profile = _normalize_production_profile(
            picked.get("production_tier", ""),
            picked.get("visual_source", ""),
            picked.get("tts_source", ""),
        )
    except _ProfileError:
        return {
            "production_tier": picked.get("production_tier"),
            "visual_source": picked.get("visual_source"),
            "tts_source": picked.get("tts_source"),
            "valid": False,
            **experiment,
        }
    if experiment:
        profile = {**profile, **experiment}
    return profile


def read_project_snapshot(project_id: str) -> dict[str, Any]:
    """Return chat-shaped progress matching produce_read_state / run_get_project_state."""
    workspace = get_workspace()
    pdir = workspace.project_dir(project_id)
    if not pdir.exists():
        raise ApplicationError(f"Project not found: {project_id}", code=NOT_FOUND)
    root = workspace.projects_dir
    marker_path = pdir / PROJECT_MARKER_FILENAME
    marker = {}
    if marker_path.exists():
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    pipeline_type = marker.get("pipeline_type")
    latest = get_latest_checkpoint(root, project_id)
    completed = get_completed_stages(root, project_id, pipeline_type)
    nxt = get_next_stage(root, project_id, pipeline_type)
    awaiting = None
    if latest and latest.get("status") == "awaiting_human":
        awaiting = {
            "stage": latest.get("stage"),
            "human_approval_required": latest.get("human_approval_required"),
        }
    return {
        "project_id": project_id,
        "project_dir": str(pdir),
        "marker": marker,
        "production_profile": resolve_production_profile(marker, latest),
        "completed_stages": completed,
        "next_stage": nxt,
        "awaiting_human": awaiting,
        "latest_checkpoint_stage": (latest or {}).get("stage"),
        "latest_checkpoint_status": (latest or {}).get("status"),
    }

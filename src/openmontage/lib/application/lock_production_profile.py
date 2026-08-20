"""Persist production_profile onto project.json. Does not call generate."""

from __future__ import annotations

from typing import Any

from lib.application.errors import ApplicationError
from lib.checkpoint import PROJECT_MARKER_FILENAME
from lib.error_codes import BAD_REQUEST, NOT_FOUND
from lib.paths import get_workspace
from lib.persistence.json_store import JsonStore

_PRODUCTION_TIERS = frozenset({"light", "medium", "heavy"})
_VISUAL_SOURCES = frozenset({"template", "stock", "paid_gen"})
_TTS_SOURCES = frozenset({"edge_tts", "piper", "paid"})
_TIER_DEFAULTS: dict[str, dict[str, str]] = {
    "light": {"visual_source": "template", "tts_source": "edge_tts"},
    "medium": {"visual_source": "stock", "tts_source": "edge_tts"},
    "heavy": {"visual_source": "paid_gen", "tts_source": "paid"},
}
_EXPERIMENT_EXISTING_KEYS = ("api_budget_tier", "budget_cny", "review_mode", "motion_mix")


def _normalize_production_profile(
    production_tier: str,
    visual_source: str = "",
    tts_source: str = "",
) -> dict[str, str]:
    tier = (production_tier or "").strip().lower()
    if tier not in _PRODUCTION_TIERS:
        raise ApplicationError(
            f"production_tier must be one of {sorted(_PRODUCTION_TIERS)}; got {production_tier!r}",
            code=BAD_REQUEST,
        )
    defaults = _TIER_DEFAULTS[tier]
    visual = (visual_source or "").strip().lower() or defaults["visual_source"]
    tts = (tts_source or "").strip().lower() or defaults["tts_source"]
    if visual not in _VISUAL_SOURCES:
        raise ApplicationError(
            f"visual_source must be one of {sorted(_VISUAL_SOURCES)}; got {visual_source!r}",
            code=BAD_REQUEST,
        )
    if tts not in _TTS_SOURCES:
        raise ApplicationError(
            f"tts_source must be one of {sorted(_TTS_SOURCES)}; got {tts_source!r}",
            code=BAD_REQUEST,
        )
    return {
        "production_tier": tier,
        "visual_source": visual,
        "tts_source": tts,
    }


def _read_marker(project_id: str) -> dict[str, Any]:
    path = get_workspace().project_dir(project_id) / PROJECT_MARKER_FILENAME
    try:
        loaded = JsonStore.read_object(path, missing="none")
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def lock_production_profile(
    project_id: str,
    production_tier: str,
    *,
    visual_source: str = "",
    tts_source: str = "",
    api_budget_tier: str = "",
    budget_cny: str = "",
    review_mode: str = "",
    candidate_mode: str = "",
    motion_target_band: str = "",
    motion_mix: str = "",
    motion_mix_source: str = "",
    style_label_zh: str = "",
    style_playbook: str = "",
    usd_cny_rate: str = "",
    duration_seconds: str = "",
) -> dict[str, Any]:
    """Persist light/medium/heavy profile onto project.json. Does not call generate."""
    workspace = get_workspace()
    pdir = workspace.project_dir(project_id)
    if not pdir.exists():
        raise ApplicationError(f"Project not found: {project_id}", code=NOT_FOUND)
    profile: dict[str, Any] = _normalize_production_profile(
        production_tier, visual_source, tts_source
    )
    wants_experiment = any(
        [
            str(api_budget_tier).strip(),
            str(budget_cny).strip(),
            str(review_mode).strip(),
            str(candidate_mode).strip(),
            str(motion_target_band).strip(),
            str(motion_mix).strip(),
            str(motion_mix_source).strip(),
            str(style_label_zh).strip(),
            str(style_playbook).strip(),
            str(usd_cny_rate).strip(),
            str(duration_seconds).strip(),
        ]
    )
    marker = _read_marker(project_id)
    if not marker:
        raise ApplicationError(
            f"Project marker missing for: {project_id}",
            code=NOT_FOUND,
        )
    existing = (
        marker.get("production_profile")
        if isinstance(marker.get("production_profile"), dict)
        else {}
    )
    profile = {**existing, **profile}
    has_existing_experiment = any(k in existing for k in _EXPERIMENT_EXISTING_KEYS)
    if wants_experiment or has_existing_experiment:
        from lib.experiment_budget import DEFAULT_USD_CNY, merge_experiment_fields_into_profile

        rate = float(usd_cny_rate) if str(usd_cny_rate).strip() else float(
            existing.get("usd_cny_rate") or DEFAULT_USD_CNY
        )
        dur_raw = str(duration_seconds).strip() or existing.get("duration_seconds")
        try:
            duration_i = int(float(dur_raw)) if dur_raw not in (None, "") else None
        except (TypeError, ValueError):
            duration_i = None
        profile = merge_experiment_fields_into_profile(
            profile,
            api_budget_tier=(api_budget_tier or existing.get("api_budget_tier") or "standard"),
            budget_cny=budget_cny or existing.get("budget_cny"),
            review_mode=review_mode or existing.get("review_mode") or "normal",
            candidate_mode=candidate_mode or existing.get("candidate_mode") or "adaptive",
            motion_target_band=motion_target_band or existing.get("motion_target_band"),
            motion_mix=motion_mix or existing.get("motion_mix") or "0:1",
            motion_mix_source=motion_mix_source or existing.get("motion_mix_source") or "",
            duration_seconds=duration_i,
            style_label_zh=style_label_zh or existing.get("style_label_zh"),
            style_playbook=style_playbook or existing.get("style_playbook"),
            usd_cny_rate=rate,
        )
        if duration_i is not None:
            profile["duration_seconds"] = duration_i
    marker["production_profile"] = profile
    path = pdir / PROJECT_MARKER_FILENAME
    JsonStore.write_atomic(path, marker)
    return {
        "project_id": project_id,
        "marker_path": str(path),
        "production_profile": profile,
    }

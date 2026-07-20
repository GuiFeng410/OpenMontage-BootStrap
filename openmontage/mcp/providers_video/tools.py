"""providers-video — paid/cloud video gen with confirm gates (C-常用)."""

from __future__ import annotations

import json
import os
from typing import Any

from openmontage.mcp.common.errors import ConfigError, DoctorError
from openmontage.mcp.common.registry import get_registry, get_tool, tool_result_to_dict
from openmontage.mcp.common.sandbox import require_projects_root, resolve_under_projects

# C-常用 video whitelist (official Kling, not fal kling_video).
PROVIDER_TOOLS: dict[str, str] = {
    "kling": "kling_official_video",
    "seedance": "seedance_video",
    "sora": "sora_video",
    "veo": "veo_video",
    "minimax": "minimax_video",
    "runway": "runway_video",
}

TOOL_TO_PROVIDER = {v: k for k, v in PROVIDER_TOOLS.items()}

ENV_HINTS: dict[str, list[str]] = {
    "kling": ["KLING_API_KEY"],
    "seedance": ["FAL_KEY", "FAL_AI_API_KEY"],
    "sora": ["OPENAI_API_KEY"],
    "veo": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "FAL_KEY", "FAL_AI_API_KEY"],
    "minimax": ["FAL_KEY", "FAL_AI_API_KEY"],
    "runway": ["RUNWAY_API_KEY", "RUNWAYML_API_SECRET"],
}

# Short sample clip defaults per provider (provider-specific field names).
SAMPLE_DURATION_EXTRAS: dict[str, dict[str, Any]] = {
    "kling": {"duration": "5"},
    "seedance": {"duration": "5"},
    "sora": {"seconds": "4"},
    "veo": {"duration": "4s"},
    "minimax": {},  # tool has no duration input
    "runway": {"duration": 5},
}


def _allowed_providers() -> set[str] | None:
    raw = os.environ.get("OPENMONTAGE_ALLOWED_PROVIDERS", "").strip()
    if not raw:
        return None
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _max_cost_usd() -> float | None:
    raw = os.environ.get("OPENMONTAGE_MAX_COST_USD", "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"Invalid OPENMONTAGE_MAX_COST_USD: {raw}") from exc


def _resolve_tool_name(provider_or_tool: str) -> tuple[str, str]:
    key = (provider_or_tool or "").strip().lower()
    if not key:
        raise DoctorError("provider_or_tool is required", code="bad_request")
    if key in PROVIDER_TOOLS:
        provider, tool_name = key, PROVIDER_TOOLS[key]
    elif key in TOOL_TO_PROVIDER:
        tool_name, provider = key, TOOL_TO_PROVIDER[key]
    else:
        raise DoctorError(
            f"Unknown video provider/tool {provider_or_tool!r}. "
            f"Allowed providers: {sorted(PROVIDER_TOOLS)}",
            code="bad_request",
        )
    allowed = _allowed_providers()
    if allowed is not None and provider not in allowed:
        raise ConfigError(
            f"Provider {provider!r} not in OPENMONTAGE_ALLOWED_PROVIDERS={sorted(allowed)}"
        )
    return provider, tool_name


def _parse_extras(extras_json: str) -> dict[str, Any]:
    if not extras_json or not extras_json.strip():
        return {}
    try:
        data = json.loads(extras_json)
    except json.JSONDecodeError as exc:
        raise DoctorError(f"extras_json invalid: {exc}", code="bad_request") from exc
    if not isinstance(data, dict):
        raise DoctorError("extras_json must be a JSON object", code="bad_request")
    return data


def _sandbox_output(path: str | None, default_rel: str) -> str:
    if not path:
        path = default_rel
    resolved = resolve_under_projects(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)


def _apply_sample_duration(provider: str, extras: dict[str, Any]) -> dict[str, Any]:
    """Inject short-clip defaults for sample unless caller already set duration."""
    out = dict(extras)
    defaults = SAMPLE_DURATION_EXTRAS.get(provider, {})
    if "duration" not in out and "seconds" not in out:
        out.update(defaults)
    return out


def list_video_providers() -> dict[str, Any]:
    reg = get_registry()
    tools = getattr(reg, "_tools", {}) or {}
    allowed = _allowed_providers()
    rows = []
    for provider, tool_name in sorted(PROVIDER_TOOLS.items()):
        if allowed is not None and provider not in allowed:
            continue
        tool = tools.get(tool_name)
        env_names = ENV_HINTS.get(provider, [])
        key_present = any(os.environ.get(e) for e in env_names)
        if tool is None:
            rows.append(
                {
                    "provider": provider,
                    "tool_name": tool_name,
                    "status": "missing",
                    "available": False,
                    "key_configured": key_present,
                    "env_vars": env_names,
                }
            )
            continue
        info = tool.get_info()
        status = info.get("status")
        rows.append(
            {
                "provider": provider,
                "tool_name": tool_name,
                "status": status,
                "available": status == "available",
                "key_configured": key_present,
                "env_vars": env_names,
                "install_instructions": info.get("install_instructions"),
                "best_for": info.get("best_for"),
            }
        )
    return {
        "providers": rows,
        "projects_dir": str(require_projects_root()) if os.environ.get("OPENMONTAGE_PROJECTS_DIR") else None,
        "allowed_providers": sorted(allowed) if allowed else None,
        "max_cost_usd": _max_cost_usd(),
        "sample_note": "video_sample forces short duration (≈4–5s) when duration/seconds omitted.",
        "note": (
            "Stock footage is out of scope. "
            "This MCP never silently switches providers on failure."
        ),
    }


def video_dry_run(provider_or_tool: str, prompt: str, extras_json: str = "{}") -> dict[str, Any]:
    if not prompt.strip():
        raise DoctorError("prompt is required", code="bad_request")
    provider, tool_name = _resolve_tool_name(provider_or_tool)
    extras = _parse_extras(extras_json)
    tool = get_tool(tool_name)
    inputs = {"prompt": prompt, **extras}
    dry = tool.dry_run(inputs)
    try:
        estimate = float(tool.estimate_cost(inputs))
    except Exception:  # noqa: BLE001
        estimate = float(dry.get("estimated_cost_usd") or 0)
    max_cost = _max_cost_usd()
    over = max_cost is not None and estimate > max_cost
    info = tool.get_info()
    return {
        "provider": provider,
        "tool_name": tool_name,
        "model": (
            extras.get("model")
            or extras.get("model_id")
            or extras.get("model_name")
            or extras.get("model_variant")
            or info.get("model")
        ),
        "estimated_cost_usd": estimate,
        "max_cost_usd": max_cost,
        "within_budget": not over,
        "dry_run": dry,
        "status": info.get("status"),
        "key_configured": any(os.environ.get(e) for e in ENV_HINTS.get(provider, [])),
        "next_step": (
            "Call video_sample with confirm_estimate=true after the user accepts this estimate."
            if not over
            else "Estimate exceeds OPENMONTAGE_MAX_COST_USD; shorten duration or raise budget."
        ),
    }


def video_sample(
    provider_or_tool: str,
    prompt: str,
    output_path: str = "",
    extras_json: str = "{}",
    confirm_estimate: bool = False,
) -> dict[str, Any]:
    require_projects_root()
    if not confirm_estimate:
        raise ConfigError(
            "video_sample requires confirm_estimate=true after presenting video_dry_run to the user."
        )
    if not prompt.strip():
        raise DoctorError("prompt is required", code="bad_request")
    provider, tool_name = _resolve_tool_name(provider_or_tool)
    extras = _apply_sample_duration(provider, _parse_extras(extras_json))
    out = _sandbox_output(output_path or "assets/video/sample_paid.mp4", "assets/video/sample_paid.mp4")
    tool = get_tool(tool_name)
    inputs = {"prompt": prompt, "output_path": out, **extras}
    estimate = float(tool.estimate_cost(inputs))
    max_cost = _max_cost_usd()
    if max_cost is not None and estimate > max_cost:
        raise ConfigError(
            f"Estimated ${estimate:.4f} exceeds OPENMONTAGE_MAX_COST_USD={max_cost}"
        )
    result = tool.execute(inputs)
    payload = tool_result_to_dict(result)
    if not payload.get("success"):
        raise DoctorError(
            f"{tool_name} sample failed: {payload.get('error')}. "
            "No silent provider fallback. Choose another provider explicitly.",
            code="provider_failed",
        )
    payload["provider"] = provider
    payload["tool_name"] = tool_name
    payload["output_path"] = out
    payload["sample_only"] = True
    payload["sample_extras_applied"] = extras
    payload["estimated_cost_usd"] = estimate
    payload["cost_usd"] = payload.get("cost_usd") if payload.get("cost_usd") is not None else estimate
    return payload


def video_generate(
    provider_or_tool: str,
    prompt: str,
    output_path: str,
    extras_json: str = "{}",
    confirm: bool = False,
    confirm_sample_ok: bool = False,
) -> dict[str, Any]:
    require_projects_root()
    if not confirm:
        raise ConfigError(
            "video_generate requires confirm=true (user approved paid generation)."
        )
    if not confirm_sample_ok:
        raise ConfigError(
            "video_generate requires confirm_sample_ok=true after the user approved video_sample."
        )
    if not prompt.strip():
        raise DoctorError("prompt is required", code="bad_request")
    if not output_path.strip():
        raise DoctorError("output_path is required", code="bad_request")
    provider, tool_name = _resolve_tool_name(provider_or_tool)
    extras = _parse_extras(extras_json)
    out = _sandbox_output(output_path, "assets/video/gen_paid.mp4")
    tool = get_tool(tool_name)
    inputs = {"prompt": prompt, "output_path": out, **extras}
    estimate = float(tool.estimate_cost(inputs))
    max_cost = _max_cost_usd()
    if max_cost is not None and estimate > max_cost:
        raise ConfigError(
            f"Estimated ${estimate:.4f} exceeds OPENMONTAGE_MAX_COST_USD={max_cost}"
        )
    result = tool.execute(inputs)
    payload = tool_result_to_dict(result)
    if not payload.get("success"):
        raise DoctorError(
            f"{tool_name} generate failed: {payload.get('error')}. "
            "No silent provider fallback.",
            code="provider_failed",
        )
    payload["provider"] = provider
    payload["tool_name"] = tool_name
    payload["output_path"] = out
    payload["estimated_cost_usd"] = estimate
    payload["cost_usd"] = payload.get("cost_usd") if payload.get("cost_usd") is not None else estimate
    return payload

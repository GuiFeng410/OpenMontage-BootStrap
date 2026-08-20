"""P2 providers-tts tool implementations — paid/cloud TTS with confirm gates."""

from __future__ import annotations

import json
import os
from typing import Any

from openmontage.mcp.common.errors import ConfigError, DoctorError
from openmontage.mcp.common.registry import get_registry, get_tool, tool_result_to_dict
from openmontage.mcp.common.sandbox import require_projects_root, resolve_under_projects

# Stable whitelist for P2 advanced TTS (piper stays on openmontage-media).
PROVIDER_TOOLS: dict[str, str] = {
    "openai": "openai_tts",
    "elevenlabs": "elevenlabs_tts",
    "dashscope": "dashscope_tts",
    "doubao": "doubao_tts",
    "google": "google_tts",
    "kling": "kling_tts",
}

TOOL_TO_PROVIDER = {v: k for k, v in PROVIDER_TOOLS.items()}

ENV_HINTS: dict[str, list[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "elevenlabs": ["ELEVENLABS_API_KEY"],
    "dashscope": ["DASHSCOPE_API_KEY"],
    "doubao": ["DOUBAO_SPEECH_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "kling": ["KLING_API_KEY"],
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
            f"Unknown TTS provider/tool {provider_or_tool!r}. "
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


def list_tts_providers() -> dict[str, Any]:
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
        "note": (
            "Piper/zero-key TTS stays on openmontage-media. "
            "This MCP never silently switches providers on failure."
        ),
    }


def tts_dry_run(provider_or_tool: str, text: str, extras_json: str = "{}") -> dict[str, Any]:
    if not text.strip():
        raise DoctorError("text is required", code="bad_request")
    provider, tool_name = _resolve_tool_name(provider_or_tool)
    extras = _parse_extras(extras_json)
    tool = get_tool(tool_name)
    inputs = {"text": text, **extras}
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
        "model": extras.get("model") or extras.get("model_id") or info.get("model"),
        "estimated_cost_usd": estimate,
        "max_cost_usd": max_cost,
        "within_budget": not over,
        "dry_run": dry,
        "status": info.get("status"),
        "key_configured": any(os.environ.get(e) for e in ENV_HINTS.get(provider, [])),
        "next_step": (
            "Call tts_sample with confirm_estimate=true after the user accepts this estimate."
            if not over
            else "Estimate exceeds OPENMONTAGE_MAX_COST_USD; shrink text or raise budget."
        ),
    }


def tts_sample(
    provider_or_tool: str,
    text: str,
    output_path: str = "",
    extras_json: str = "{}",
    confirm_estimate: bool = False,
) -> dict[str, Any]:
    require_projects_root()
    if not confirm_estimate:
        raise ConfigError(
            "tts_sample requires confirm_estimate=true after presenting tts_dry_run to the user."
        )
    if not text.strip():
        raise DoctorError("text is required", code="bad_request")
    provider, tool_name = _resolve_tool_name(provider_or_tool)
    extras = _parse_extras(extras_json)
    out = _sandbox_output(output_path or "assets/audio/sample_paid.wav", "assets/audio/sample_paid.wav")
    tool = get_tool(tool_name)
    inputs = {"text": text, "output_path": out, "sample_mode": True, **extras}
    estimate = float(tool.estimate_cost(inputs))
    max_cost = _max_cost_usd()
    if max_cost is not None and estimate > max_cost:
        raise ConfigError(
            f"Estimated ${estimate:.4f} exceeds OPENMONTAGE_MAX_COST_USD={max_cost}"
        )
    result = tool.execute(inputs)
    payload = tool_result_to_dict(result)
    if not payload.get("success"):
        # Explicit: do NOT call fallback tools
        raise DoctorError(
            f"{tool_name} sample failed: {payload.get('error')}. "
            "No silent provider fallback. Choose another provider explicitly or use Piper via openmontage-media.",
            code="provider_failed",
        )
    payload["provider"] = provider
    payload["tool_name"] = tool_name
    payload["output_path"] = out
    payload["sample_only"] = True
    payload["estimated_cost_usd"] = estimate
    payload["cost_usd"] = payload.get("cost_usd") if payload.get("cost_usd") is not None else estimate
    return payload


def tts_generate(
    provider_or_tool: str,
    text: str,
    output_path: str,
    extras_json: str = "{}",
    confirm: bool = False,
    confirm_sample_ok: bool = False,
) -> dict[str, Any]:
    require_projects_root()
    if not confirm:
        raise ConfigError(
            "tts_generate requires confirm=true (user approved paid/batch generation)."
        )
    if not confirm_sample_ok:
        raise ConfigError(
            "tts_generate requires confirm_sample_ok=true after the user approved tts_sample."
        )
    if not text.strip():
        raise DoctorError("text is required", code="bad_request")
    if not output_path.strip():
        raise DoctorError("output_path is required", code="bad_request")
    provider, tool_name = _resolve_tool_name(provider_or_tool)
    extras = _parse_extras(extras_json)
    out = _sandbox_output(output_path, "assets/audio/narration_paid.wav")
    tool = get_tool(tool_name)
    inputs = {"text": text, "output_path": out, "sample_mode": False, **extras}
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

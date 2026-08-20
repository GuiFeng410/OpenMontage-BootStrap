"""P0 doctor tool implementations (read-only by default)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import ensure_import_roots, get_workspace
from openmontage.mcp.common.errors import ConfigError, DoctorError
from openmontage.mcp.common.sandbox import project_dir, projects_root, require_projects_root, resolve_under_projects

REPO_ROOT = get_workspace().repo_root

# Host extraDirs (G5). Do not point extraDirs at skills/ itself.
_SKILL_EXTRA_DIR_PARTS = (
    ("skills", "bootstrap"),
    ("skills", "providers"),
    ("skills", "production"),
)


def _iter_skill_pack_dirs() -> list[Path]:
    """Direct children of extraDirs roots; fall back to openmontage/skills if none exist."""
    packs: list[Path] = []
    seen: set[str] = set()
    for parts in _SKILL_EXTRA_DIR_PARTS:
        root = REPO_ROOT.joinpath(*parts)
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and child.name not in seen:
                packs.append(child)
                seen.add(child.name)
    if not seen:
        legacy = REPO_ROOT / "openmontage" / "skills"
        if legacy.is_dir():
            for child in sorted(legacy.iterdir()):
                if child.is_dir() and child.name not in seen:
                    packs.append(child)
                    seen.add(child.name)
    return packs


PRODUCTION_TIERS = frozenset({"light", "medium", "heavy"})
VISUAL_SOURCES = frozenset({"template", "stock", "paid_gen"})
TTS_SOURCES = frozenset({"edge_tts", "piper", "paid"})
_PROFILE_KEYS = ("production_tier", "visual_source", "tts_source")
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
_TIER_DEFAULTS: dict[str, dict[str, str]] = {
    "light": {"visual_source": "template", "tts_source": "edge_tts"},
    "medium": {"visual_source": "stock", "tts_source": "edge_tts"},
    "heavy": {"visual_source": "paid_gen", "tts_source": "paid"},
}


def _which(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    if not path:
        return {"ok": False, "error": "not found", "path": None, "version": None}
    version = None
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        version = (proc.stdout or proc.stderr or "").strip().splitlines()[:1]
        version = version[0] if version else None
    except Exception as exc:  # noqa: BLE001
        version = f"version check failed: {exc}"
    return {"ok": True, "error": None, "path": path, "version": version}


def _fix_hint(binary: str) -> dict[str, list[str]]:
    hints = {
        "node": {
            "win32": ["winget install OpenJS.NodeJS.LTS", "or install from https://nodejs.org/"],
            "darwin": ["brew install node"],
            "linux": ["sudo apt install nodejs npm  # Debian/Ubuntu"],
        },
        "ffmpeg": {
            "win32": ["winget install Gyan.FFmpeg", "or https://ffmpeg.org/download.html"],
            "darwin": ["brew install ffmpeg"],
            "linux": ["sudo apt install ffmpeg"],
        },
        "ffprobe": {
            "win32": ["Install FFmpeg (includes ffprobe)"],
            "darwin": ["brew install ffmpeg"],
            "linux": ["sudo apt install ffmpeg"],
        },
        "npx": {
            "win32": ["Install Node.js LTS (includes npx)"],
            "darwin": ["brew install node"],
            "linux": ["Install Node.js 18+"],
        },
        "piper": {
            "win32": [
                "pip install piper-tts",
                "python -m piper.download_voices zh_CN-huayan-medium --download-dir <USER>\\.piper\\models",
            ],
            "darwin": [
                "pip install piper-tts",
                "python -m piper.download_voices zh_CN-huayan-medium --download-dir ~/.piper/models",
            ],
            "linux": [
                "pip install piper-tts",
                "python -m piper.download_voices zh_CN-huayan-medium --download-dir ~/.piper/models",
            ],
        },
    }
    return hints.get(binary, {"win32": [], "darwin": [], "linux": []})


def _ensure_repo_on_path() -> None:
    ensure_import_roots(REPO_ROOT)


def _registry():
    _ensure_repo_on_path()
    from tools.tool_registry import registry

    registry.discover()
    return registry


def _remotion_ok() -> dict[str, Any]:
    from lib.resources import get_resources

    composer = get_resources().remotion_composer()
    nm = composer / "node_modules"
    pkg = composer / "package.json"
    if not pkg.exists():
        return {"ok": False, "detail": "Remotion package.json missing (runtimes/remotion)"}
    if not nm.exists():
        return {
            "ok": False,
            "detail": "Remotion node_modules missing — run npm install in runtimes/remotion",
        }
    return {"ok": True, "detail": str(composer)}


def _piper_ok() -> dict[str, Any]:
    piper = shutil.which("piper") or shutil.which("piper-tts")
    model_dir = Path(
        os.environ.get("PIPER_MODEL_DIR")
        or (Path.home() / ".piper" / "models")
    ).expanduser()
    models = list(model_dir.glob("*.onnx")) if model_dir.exists() else []
    if not piper and not models:
        return {
            "ok": False,
            "detail": "piper binary and models not found",
            "model_dir": str(model_dir),
            "models": [],
        }
    return {
        "ok": bool(piper) and bool(models),
        "detail": "piper ready" if (piper and models) else "partial: binary or models missing",
        "binary": piper,
        "model_dir": str(model_dir),
        "models": [m.name for m in models[:20]],
    }


def _classify_tier(
    *,
    piper: dict[str, Any],
    remotion: dict[str, Any],
    ffmpeg_ok: bool,
    summary: dict[str, Any],
) -> str:
    caps = {c["capability"]: c for c in summary.get("capabilities", [])}
    has_image = (caps.get("image_generation") or {}).get("configured", 0) > 0
    has_video = (caps.get("video_generation") or {}).get("configured", 0) > 0
    has_music = (caps.get("music_generation") or {}).get("configured", 0) > 0
    has_tts_cloud = False
    tts = caps.get("tts") or {}
    for p in tts.get("available_providers") or []:
        if p and p not in {"piper", "openmontage"}:
            has_tts_cloud = True
            break

    if has_video and (has_image or has_tts_cloud):
        return "full"
    if has_image and (has_music or has_tts_cloud or piper.get("ok")):
        return "standard"
    if has_image and (piper.get("ok") or has_tts_cloud) and (remotion.get("ok") or ffmpeg_ok):
        return "starter"
    if piper.get("ok") and remotion.get("ok") and ffmpeg_ok:
        return "zero-key"
    if ffmpeg_ok:
        return "unknown"
    return "unknown"


def run_doctor(*, deep: bool = False) -> dict[str, Any]:
    plat = sys.platform
    binaries = {
        "python": {
            "ok": True,
            "path": sys.executable,
            "version": sys.version.split()[0],
            "error": None,
        },
        "node": _which("node"),
        "ffmpeg": _which("ffmpeg"),
        "ffprobe": _which("ffprobe"),
        "npx": _which("npx"),
    }
    for name, info in list(binaries.items()):
        if name == "python":
            continue
        if not info.get("ok"):
            info["fix_hint"] = _fix_hint(name).get(plat) or _fix_hint(name).get("linux")

    remotion = _remotion_ok()
    piper = _piper_ok()
    if not piper.get("ok"):
        piper["fix_hint"] = _fix_hint("piper").get(plat) or _fix_hint("piper").get("linux")

    hyperframes = {"ok": False, "detail": "not probed in P0 shallow mode"}
    summary: dict[str, Any] = {}
    registry_meta: dict[str, Any] = {"tool_count": 0, "available_count": 0, "by_capability_top": []}
    quick_unlocks: list[dict[str, Any]] = []
    warnings: list[str] = []

    try:
        reg = _registry()
        summary = reg.provider_menu_summary()
        tools = getattr(reg, "_tools", {}) or {}
        available = [t for t in tools.values() if t.get_status().value == "available"]
        registry_meta = {
            "tool_count": len(tools),
            "available_count": len(available),
            "by_capability_top": [
                {
                    "capability": c.get("capability"),
                    "configured": c.get("configured"),
                    "total": c.get("total"),
                }
                for c in (summary.get("capabilities") or [])[:12]
            ],
        }
        runtimes = summary.get("composition_runtimes") or {}
        if "hyperframes" in runtimes:
            hyperframes = {
                "ok": bool(runtimes.get("hyperframes")),
                "detail": "from video_compose.render_engines",
            }
        for offer in summary.get("setup_offers") or []:
            quick_unlocks.append(
                {
                    "what": f"{offer.get('capability')}:{offer.get('tool')}",
                    "commands": {
                        plat: [offer.get("install_instructions") or "See install_instructions"]
                    },
                    "install_instructions": offer.get("install_instructions"),
                }
            )
        for w in summary.get("runtime_warnings") or []:
            warnings.append(str(w))
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"registry discovery failed: {exc}")

    if deep:
        warnings.append("deep=true currently reuses full registry discover; no extra probes yet")

    ffmpeg_ok = bool(binaries["ffmpeg"].get("ok"))
    tier = _classify_tier(
        piper=piper,
        remotion=remotion,
        ffmpeg_ok=ffmpeg_ok,
        summary=summary,
    )

    skill_packs = []
    for child in _iter_skill_pack_dirs():
        if (child / "SKILL.md").exists() or (child / "skill.md").exists():
            skill_packs.append(child.name)

    media_module = importlib.util.find_spec("openmontage.mcp.media.server") is not None
    explainer_skill = "openmontage-animated-explainer" in skill_packs
    can_produce = bool(
        media_module
        and explainer_skill
        and piper.get("ok")
        and remotion.get("ok")
        and ffmpeg_ok
    )
    next_p1 = []
    if not piper.get("ok"):
        next_p1.append("piper-tts + Chinese voice model")
    if not remotion.get("ok"):
        next_p1.append("runtimes/remotion npm install")
    if not ffmpeg_ok:
        next_p1.append("ffmpeg on PATH")
    if not media_module:
        next_p1.append("P1 openmontage-media MCP")
    if not explainer_skill:
        next_p1.append("openmontage-animated-explainer Skill Pack")
    if can_produce:
        next_p1 = ["Ready for zero-key animated-explainer (register media MCP + production agent)"]

    return {
        "tier": tier,
        "platform": plat,
        "machine": platform.platform(),
        "binaries": binaries,
        "runtimes": {
            "remotion": remotion,
            "hyperframes": hyperframes,
            "piper": piper,
        },
        "registry": registry_meta,
        "provider_menu_summary": summary if deep else {
            "composition_runtimes": summary.get("composition_runtimes"),
            "capabilities_count": len(summary.get("capabilities") or []),
            "setup_offers_count": len(summary.get("setup_offers") or []),
        },
        "quick_unlocks": quick_unlocks[:10],
        "hardware_unlocks": [],
        "installed_skill_packs": skill_packs,
        "projects_dir": str(projects_root()) if projects_root() else None,
        "can_produce_video_now": can_produce,
        "next_install_for_p1": next_p1,
        "p0_write_policy": {
            "default_agent_writes": False,
            "p1_sandbox_writes": p1_writes_enabled(),
            "note": (
                "Default Agent: no host writes. Production Agent: enable "
                "OPENMONTAGE_P1_ALLOW_WRITES=true and keep all paths under "
                "OPENMONTAGE_PROJECTS_DIR sandbox; attach openmontage-media MCP."
            ),
        },
        "_warnings": warnings,
    }


def run_provider_menu_summary() -> dict[str, Any]:
    reg = _registry()
    return reg.provider_menu_summary()


def run_list_pipelines() -> dict[str, Any]:
    _ensure_repo_on_path()
    from lib.pipeline_loader import list_pipelines
    from lib.resources import get_resources

    defs = get_resources().pipeline_defs()
    names = []
    try:
        names = list_pipelines()
    except Exception:
        names = sorted(p.stem for p in defs.glob("*.yaml")) if defs.exists() else []

    packs = [p.name for p in _iter_skill_pack_dirs()]

    return {
        "pipeline_defs_present": names,
        "skill_packs_present": packs,
        "note": "File presence ≠ Skill Pack installed into OpenClaw. P0 only reports repo contents.",
    }


def run_list_projects() -> dict[str, Any]:
    root = require_projects_root()
    if not root.exists():
        return {"projects_dir": str(root), "projects": [], "note": "projects dir does not exist yet"}
    projects = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        marker = child / "project.json"
        meta: dict[str, Any] = {"project_id": child.name, "has_marker": marker.exists()}
        if marker.exists():
            try:
                meta.update(json.loads(marker.read_text(encoding="utf-8")))
            except Exception as exc:  # noqa: BLE001
                meta["marker_error"] = str(exc)
        projects.append(meta)
    return {"projects_dir": str(root), "projects": projects}


def _marker_path(project_id: str) -> Path:
    _ensure_repo_on_path()
    from lib.checkpoint import PROJECT_MARKER_FILENAME

    return project_dir(project_id) / PROJECT_MARKER_FILENAME


def _read_marker(project_id: str) -> dict[str, Any]:
    path = _marker_path(project_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_marker(project_id: str, marker: dict[str, Any]) -> Path:
    path = _marker_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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


def _normalize_production_profile(
    production_tier: str,
    visual_source: str = "",
    tts_source: str = "",
) -> dict[str, str]:
    tier = (production_tier or "").strip().lower()
    if tier not in PRODUCTION_TIERS:
        raise DoctorError(
            f"production_tier must be one of {sorted(PRODUCTION_TIERS)}; got {production_tier!r}",
            code="bad_request",
        )
    defaults = _TIER_DEFAULTS[tier]
    visual = (visual_source or "").strip().lower() or defaults["visual_source"]
    tts = (tts_source or "").strip().lower() or defaults["tts_source"]
    if visual not in VISUAL_SOURCES:
        raise DoctorError(
            f"visual_source must be one of {sorted(VISUAL_SOURCES)}; got {visual_source!r}",
            code="bad_request",
        )
    if tts not in TTS_SOURCES:
        raise DoctorError(
            f"tts_source must be one of {sorted(TTS_SOURCES)}; got {tts_source!r}",
            code="bad_request",
        )
    return {
        "production_tier": tier,
        "visual_source": visual,
        "tts_source": tts,
    }


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


def resolve_production_profile(
    marker: dict[str, Any] | None,
    latest_checkpoint: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Prefer project.json profile; fall back to latest checkpoint artifacts."""
    from lib.application.read_project_snapshot import (
        resolve_production_profile as resolve_profile,
    )

    return resolve_profile(marker, latest_checkpoint)


def _build_production_profile_marker_update(
    project_id: str,
    fields: dict[str, Any],
) -> dict[str, Any] | None:
    picked = _pick_profile_fields(fields)
    if "production_tier" not in picked:
        return None
    profile = _normalize_production_profile(
        picked.get("production_tier", ""),
        picked.get("visual_source", ""),
        picked.get("tts_source", ""),
    )
    experiment = _pick_experiment_fields(fields)
    if experiment:
        _ensure_repo_on_path()
        from lib.experiment_budget import merge_experiment_fields_into_profile

        profile = merge_experiment_fields_into_profile(
            profile,
            api_budget_tier=str(experiment.get("api_budget_tier") or "") or None,
            budget_cny=experiment.get("budget_cny"),
            review_mode=str(experiment.get("review_mode") or "") or None,
            candidate_mode=str(experiment.get("candidate_mode") or "") or None,
            motion_target_band=str(experiment.get("motion_target_band") or "") or None,
            motion_mix=str(experiment.get("motion_mix") or "") or None,
            motion_mix_source=str(experiment.get("motion_mix_source") or "") or None,
            duration_seconds=experiment.get("duration_seconds"),
            style_label_zh=str(experiment.get("style_label_zh") or "") or None,
            style_playbook=str(experiment.get("style_playbook") or "") or None,
        )
    marker = _read_marker(project_id)
    if not marker.get("project_id"):
        raise DoctorError(f"Project not found: {project_id}", code="not_found")
    # Preserve previously stored experiment fields when checkpoint omits them.
    existing = marker.get("production_profile")
    if isinstance(existing, dict):
        for key in _EXPERIMENT_PROFILE_KEYS:
            if key not in profile and key in existing:
                profile[key] = existing[key]
    marker["production_profile"] = profile
    return marker


def _sync_production_profile_to_marker(
    project_id: str,
    fields: dict[str, Any],
) -> dict[str, Any] | None:
    """Backward-compatible direct sync for non-checkpoint callers."""
    marker = _build_production_profile_marker_update(project_id, fields)
    if marker is None:
        return None
    _write_marker(project_id, marker)
    return marker["production_profile"]


def run_set_production_profile(
    project_id: str,
    production_tier: str,
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
    """Persist light/medium/heavy profile onto project.json (requires P1 writes).

    Optional experiment fields (api budget / review mode / candidate mode /
    motion_mix) are merged into the same production_profile object. They are
    experimental API budget caps, not selling prices.
    """
    require_p1_writes()
    require_projects_root()
    from lib.application.errors import ApplicationError
    from lib.application.lock_production_profile import lock_production_profile

    try:
        return lock_production_profile(
            project_id,
            production_tier,
            visual_source=visual_source,
            tts_source=tts_source,
            api_budget_tier=api_budget_tier,
            budget_cny=budget_cny,
            review_mode=review_mode,
            candidate_mode=candidate_mode,
            motion_target_band=motion_target_band,
            motion_mix=motion_mix,
            motion_mix_source=motion_mix_source,
            style_label_zh=style_label_zh,
            style_playbook=style_playbook,
            usd_cny_rate=usd_cny_rate,
            duration_seconds=duration_seconds,
        )
    except ApplicationError as exc:
        raise DoctorError(exc.message, code=exc.code) from exc


def run_get_project_state(project_id: str) -> dict[str, Any]:
    require_projects_root()
    from lib.application.read_project_snapshot import ApplicationError, read_project_snapshot

    try:
        return read_project_snapshot(project_id)
    except ApplicationError as exc:
        raise DoctorError(exc.message, code=exc.code) from exc


def run_get_next_stage(project_id: str) -> dict[str, Any]:
    state = run_get_project_state(project_id)
    pipeline_type = (state.get("marker") or {}).get("pipeline_type")
    stage = state.get("next_stage")
    human = False
    if stage and pipeline_type:
        try:
            _ensure_repo_on_path()
            from lib.pipeline_loader import get_stage_human_approval_default, load_pipeline_readonly

            manifest = load_pipeline_readonly(pipeline_type)
            human = bool(get_stage_human_approval_default(manifest, stage))
        except Exception:  # noqa: BLE001
            human = False
    return {
        "project_id": project_id,
        "next_stage": stage,
        "human_approval_default": human,
        "awaiting_human": state.get("awaiting_human"),
        "done": stage is None,
    }


def run_validate_artifact(path: str, artifact_type: str | None = None) -> dict[str, Any]:
    _ensure_repo_on_path()
    import jsonschema

    resolved = resolve_under_projects(path)
    if not resolved.exists():
        raise DoctorError(f"Artifact not found: {resolved}", code="not_found")
    data = json.loads(resolved.read_text(encoding="utf-8"))
    from lib.resources import get_resources

    schema_dir = get_resources().artifact_schemas()
    schema_name = artifact_type or resolved.stem
    # allow research_brief.json → research_brief.schema.json
    candidates = [
        schema_dir / f"{schema_name}.schema.json",
        schema_dir / f"{schema_name.replace('-', '_')}.schema.json",
    ]
    schema_path = next((c for c in candidates if c.exists()), None)
    if schema_path is None:
        return {
            "path": str(resolved),
            "validated": False,
            "reason": f"No schema found for artifact_type={schema_name!r}",
            "schema_path": None,
        }
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=data, schema=schema)
        return {
            "path": str(resolved),
            "validated": True,
            "schema_path": str(schema_path),
            "artifact_type": schema_name,
        }
    except jsonschema.ValidationError as exc:
        return {
            "path": str(resolved),
            "validated": False,
            "schema_path": str(schema_path),
            "artifact_type": schema_name,
            "error": exc.message,
        }


def run_validate_checkpoint(path: str) -> dict[str, Any]:
    _ensure_repo_on_path()
    from lib.checkpoint import validate_checkpoint

    resolved = resolve_under_projects(path)
    if not resolved.exists():
        raise DoctorError(f"Checkpoint not found: {resolved}", code="not_found")
    data = json.loads(resolved.read_text(encoding="utf-8"))
    project_dir = resolved.parent
    for candidate in resolved.parents:
        if (candidate / "project.json").is_file():
            project_dir = candidate
            break
    try:
        validate_checkpoint(data, project_dir=project_dir)
        return {"path": str(resolved), "validated": True}
    except Exception as exc:  # noqa: BLE001
        return {"path": str(resolved), "validated": False, "error": str(exc)}


def run_estimate_cost(tool_name: str, inputs_json: str = "{}") -> dict[str, Any]:
    reg = _registry()
    tool = getattr(reg, "_tools", {}).get(tool_name)
    if tool is None:
        raise DoctorError(f"Unknown tool: {tool_name}", code="not_found")
    try:
        inputs = json.loads(inputs_json) if inputs_json else {}
        if not isinstance(inputs, dict):
            raise ValueError("inputs must be a JSON object")
    except Exception as exc:  # noqa: BLE001
        raise DoctorError(f"Invalid inputs_json: {exc}", code="bad_request") from exc
    return {
        "tool": tool_name,
        "estimated_cost_usd": float(tool.estimate_cost(inputs)),
        "estimated_runtime_seconds": float(tool.estimate_runtime(inputs)),
        "status": tool.get_status().value,
        "dry_run": tool.dry_run(inputs),
    }


def writes_enabled() -> bool:
    return os.environ.get("OPENMONTAGE_P0_ALLOW_WRITES", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def p1_writes_enabled() -> bool:
    flag = os.environ.get("OPENMONTAGE_P1_ALLOW_WRITES", "").strip().lower()
    return flag in {"1", "true", "yes", "on"} or writes_enabled()


def require_p1_writes() -> None:
    if not p1_writes_enabled():
        raise ConfigError(
            "Sandbox project writes require OPENMONTAGE_P1_ALLOW_WRITES=true "
            "on the production Agent (default Agent remains read-only)."
        )


def run_init_project_denied() -> dict[str, Any]:
    """Default Agent: refuse host writes (P0 policy)."""
    raise ConfigError(
        "init_project is disabled for the default Agent. "
        "Use the production Agent with OPENMONTAGE_P1_ALLOW_WRITES=true; "
        "files stay under OPENMONTAGE_PROJECTS_DIR only."
    )


def run_init_project(
    project_id: str,
    title: str,
    pipeline_type: str,
    mode: str = "create_new",
) -> dict[str, Any]:
    require_p1_writes()
    require_projects_root()
    from lib.application.create_project import create_project
    from lib.application.errors import ApplicationError

    try:
        return create_project(
            title=title,
            pipeline_type=pipeline_type,
            mode=mode,
            requested_project_id=project_id,
        )
    except ApplicationError as exc:
        raise DoctorError(exc.message, code=exc.code) from exc


def run_import_project_images(
    source_project_id: str,
    target_project_id: str,
    filenames_json: str,
) -> dict[str, Any]:
    """Copy selected source images into another project without state/media reuse."""
    require_p1_writes()
    if source_project_id == target_project_id:
        raise DoctorError(
            "source_project_id and target_project_id must be different",
            code="bad_request",
        )
    source_dir = project_dir(source_project_id)
    target_dir = project_dir(target_project_id)
    if not (source_dir / "project.json").is_file():
        raise DoctorError(
            f"Source project {source_project_id!r} does not exist",
            code="not_found",
        )
    if not (target_dir / "project.json").is_file():
        raise DoctorError(
            f"Target project {target_project_id!r} does not exist",
            code="not_found",
        )
    try:
        filenames = json.loads(filenames_json)
    except json.JSONDecodeError as exc:
        raise DoctorError(
            f"filenames_json invalid: {exc}",
            code="bad_request",
        ) from exc
    if not isinstance(filenames, list) or not filenames:
        raise DoctorError(
            "filenames_json must be a non-empty array",
            code="bad_request",
        )

    allowed_extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
    source_images = (source_dir / "assets" / "images").resolve()
    target_images = target_dir / "assets" / "images"
    pending: list[tuple[str, Path, Path]] = []
    for raw_name in filenames:
        if not isinstance(raw_name, str) or Path(raw_name).name != raw_name or "/" in raw_name or "\\" in raw_name:
            raise DoctorError(
                "Each imported image must be a plain filename from source assets/images",
                code="bad_request",
            )
        if Path(raw_name).suffix.lower() not in allowed_extensions:
            raise DoctorError(
                f"Unsupported image extension: {raw_name}",
                code="bad_request",
            )
        source = (source_images / raw_name).resolve()
        try:
            source.relative_to(source_images)
        except ValueError as exc:
            raise DoctorError(
                f"Image path escapes source project: {raw_name}",
                code="sandbox_violation",
            ) from exc
        if not source.is_file():
            raise DoctorError(
                f"Source image not found: {raw_name}",
                code="not_found",
            )
        target = target_images / raw_name
        if target.exists():
            raise DoctorError(
                f"Target image already exists: {raw_name}",
                code="conflict",
            )
        pending.append((raw_name, source, target))

    imported = []
    target_images.mkdir(parents=True, exist_ok=True)
    for name, source, target in pending:
        shutil.copy2(source, target)
        imported.append({
            "file": name,
            "source_project_id": source_project_id,
            "source_path": f"assets/images/{name}",
            "target_path": f"assets/images/{name}",
        })
    return {
        "source_project_id": source_project_id,
        "target_project_id": target_project_id,
        "imported": imported,
        "copied_checkpoints": 0,
        "copied_generated_media": 0,
        "message_zh": "仅复制了明确选择的原始图片；未继承旧检查点、视频或渲染产物。",
    }


def run_read_artifact(path: str) -> dict[str, Any]:
    resolved = resolve_under_projects(path)
    if not resolved.exists():
        raise DoctorError(f"Artifact not found: {resolved}", code="not_found")
    text = resolved.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    return {"path": str(resolved), "json": data, "text": text if data is None else None}


def run_write_artifact(path: str, content_json: str) -> dict[str, Any]:
    require_p1_writes()
    resolved = resolve_under_projects(path)
    try:
        payload = json.loads(content_json)
    except json.JSONDecodeError as exc:
        raise DoctorError(f"content_json invalid: {exc}", code="bad_request") from exc
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(resolved), "bytes": resolved.stat().st_size}


def run_write_checkpoint(
    project_id: str,
    stage: str,
    status: str,
    artifacts_json: str = "{}",
    pipeline_type: str = "",
    human_approval_required: bool = False,
    human_approved: bool = False,
    approval_note: str = "",
    metadata_json: str = "",
    cost_snapshot_json: str = "",
) -> dict[str, Any]:
    require_p1_writes()
    _ensure_repo_on_path()
    from lib.checkpoint import merge_write_checkpoint

    root = require_projects_root()
    project_dir(project_id)  # validate id
    try:
        supplied_artifacts = json.loads(artifacts_json) if artifacts_json else {}
    except json.JSONDecodeError as exc:
        raise DoctorError(f"artifacts_json invalid: {exc}", code="bad_request") from exc
    if not isinstance(supplied_artifacts, dict):
        raise DoctorError("artifacts_json must be an object", code="bad_request")
    try:
        supplied_metadata = json.loads(metadata_json) if metadata_json else {}
    except json.JSONDecodeError as exc:
        raise DoctorError(f"metadata_json invalid: {exc}", code="bad_request") from exc
    if not isinstance(supplied_metadata, dict):
        raise DoctorError("metadata_json must be an object", code="bad_request")
    try:
        cost_snapshot = json.loads(cost_snapshot_json) if cost_snapshot_json else None
    except json.JSONDecodeError as exc:
        raise DoctorError(f"cost_snapshot_json invalid: {exc}", code="bad_request") from exc
    if cost_snapshot is not None and not isinstance(cost_snapshot, dict):
        raise DoctorError("cost_snapshot_json must be an object", code="bad_request")
    if approval_note:
        supplied_metadata["approval_note"] = approval_note
    path, written, marker_update = merge_write_checkpoint(
        root,
        project_id,
        stage,
        status,
        supplied_artifacts,
        pipeline_type=pipeline_type or None,
        human_approval_required=human_approval_required,
        human_approved=human_approved,
        cost_snapshot_patch=cost_snapshot,
        metadata_patch=supplied_metadata,
        project_marker_builder=lambda artifacts: (
            _build_production_profile_marker_update(project_id, artifacts)
        ),
    )
    artifacts = written["artifacts"]
    synced_profile = (
        marker_update.get("production_profile")
        if isinstance(marker_update, dict)
        else None
    )
    result: dict[str, Any] = {
        "checkpoint_path": str(path),
        "stage": stage,
        "status": status,
        "artifact_keys": sorted(artifacts.keys()),
        "materialized_hint_zh": "已写入 checkpoint，并尽量落盘 artifacts/*.json；请刷新看板核对。",
    }
    if synced_profile:
        result["production_profile"] = synced_profile
    return result


def run_approve_checkpoint(
    project_id: str,
    stage: str,
    approval_text: str,
    artifacts_json: str = "{}",
    pipeline_type: str = "",
    metadata_json: str = "",
    cost_snapshot_json: str = "",
) -> dict[str, Any]:
    """Complete a gated stage only with explicit user approval text from the Agent."""
    if not approval_text or not approval_text.strip():
        raise ConfigError(
            "approve_checkpoint requires approval_text from the user's chat reply; "
            "MCP cannot invent approval."
        )
    require_p1_writes()
    require_projects_root()
    project_dir(project_id)
    try:
        supplied_artifacts = json.loads(artifacts_json) if artifacts_json else {}
    except json.JSONDecodeError as exc:
        raise DoctorError(f"artifacts_json invalid: {exc}", code="bad_request") from exc
    if not isinstance(supplied_artifacts, dict):
        raise DoctorError("artifacts_json must be an object", code="bad_request")

    try:
        supplied_metadata = json.loads(metadata_json) if metadata_json else {}
    except json.JSONDecodeError as exc:
        raise DoctorError(f"metadata_json invalid: {exc}", code="bad_request") from exc
    if not isinstance(supplied_metadata, dict):
        raise DoctorError("metadata_json must be an object", code="bad_request")

    if cost_snapshot_json:
        try:
            cost_snapshot = json.loads(cost_snapshot_json)
        except json.JSONDecodeError as exc:
            raise DoctorError(f"cost_snapshot_json invalid: {exc}", code="bad_request") from exc
        if not isinstance(cost_snapshot, dict):
            raise DoctorError("cost_snapshot_json must be an object", code="bad_request")
    else:
        cost_snapshot = None

    from lib.application.approve_stage import approve_stage
    from lib.application.errors import ApplicationError

    try:
        return approve_stage(
            project_id,
            stage,
            approval_text,
            artifacts=supplied_artifacts,
            pipeline_type=pipeline_type,
            metadata=supplied_metadata,
            cost_snapshot=cost_snapshot,
            project_marker_builder=lambda artifacts: (
                _build_production_profile_marker_update(project_id, artifacts)
            ),
        )
    except ApplicationError as exc:
        raise DoctorError(exc.message, code=exc.code) from exc


def run_append_decision(project_id: str, decision_json: str) -> dict[str, Any]:
    require_p1_writes()
    _ensure_repo_on_path()
    from lib.asset_precheck import has_generated_image_source
    from lib.checkpoint import _merge_decision_log
    from schemas.artifacts import validate_artifact

    root = require_projects_root()
    project = project_dir(project_id)
    try:
        decision = json.loads(decision_json)
    except json.JSONDecodeError as exc:
        raise DoctorError(f"decision_json invalid: {exc}", code="bad_request") from exc
    if isinstance(decision, dict) and "decisions" not in decision:
        decision = {"version": "1.0", "project_id": project_id, "decisions": [decision]}
    if not isinstance(decision, dict) or "decisions" not in decision:
        raise DoctorError(
            "decision_json must be a decision object or {decisions:[...]}",
            code="bad_request",
        )
    decision.setdefault("version", "1.0")
    decision.setdefault("project_id", project_id)
    for row in decision.get("decisions") or []:
        if (
            not isinstance(row, dict)
            or row.get("category") != "asset_decision"
            or str(row.get("selected") or "").strip() != "approved"
            or not str(row.get("asset_path") or "").strip()
            or not has_generated_image_source(row)
        ):
            continue
        raw_asset_path = str(row.get("asset_path") or "").strip()
        candidate = project / raw_asset_path
        try:
            candidate = candidate.resolve()
            candidate.relative_to(project.resolve())
            if not candidate.is_file():
                raise OSError("approved asset is not a file")
            actual_sha256 = hashlib.sha256(candidate.read_bytes()).hexdigest()
        except (OSError, ValueError) as exc:
            raise DoctorError(
                "approved asset_path must be an existing project-local file",
                code="bad_request",
            ) from exc
        supplied_sha256 = str(row.get("asset_sha256") or "").strip().lower()
        if supplied_sha256 and supplied_sha256 != actual_sha256:
            raise DoctorError(
                "asset_sha256 does not match the approved asset content",
                code="bad_request",
            )
        row["asset_sha256"] = actual_sha256
    try:
        validate_artifact("decision_log", decision)
    except Exception as exc:
        raise DoctorError(f"decision_json invalid: {exc}", code="bad_request") from exc
    try:
        appended = _merge_decision_log(root, project_id, decision)
    except Exception as exc:
        raise DoctorError(str(exc), code="bad_request") from exc
    return {"project_id": project_id, "appended": appended}

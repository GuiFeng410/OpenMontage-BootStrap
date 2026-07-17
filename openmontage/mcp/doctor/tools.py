"""P0 doctor tool implementations (read-only by default)."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from openmontage.mcp.common.errors import ConfigError, DoctorError
from openmontage.mcp.common.sandbox import project_dir, projects_root, require_projects_root, resolve_under_projects

REPO_ROOT = Path(__file__).resolve().parents[3]


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
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _registry():
    _ensure_repo_on_path()
    from tools.tool_registry import registry

    registry.discover()
    return registry


def _remotion_ok() -> dict[str, Any]:
    composer = REPO_ROOT / "remotion-composer"
    nm = composer / "node_modules"
    pkg = composer / "package.json"
    if not pkg.exists():
        return {"ok": False, "detail": "remotion-composer/package.json missing"}
    if not nm.exists():
        return {
            "ok": False,
            "detail": "remotion-composer/node_modules missing — run npm install in remotion-composer",
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
    skills_root = REPO_ROOT / "openmontage" / "skills"
    if skills_root.exists():
        for child in sorted(skills_root.iterdir()):
            if (child / "SKILL.md").exists() or (child / "skill.md").exists():
                skill_packs.append(child.name)

    media_module = (REPO_ROOT / "openmontage" / "mcp" / "media" / "server.py").exists()
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
        next_p1.append("remotion-composer npm install")
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

    defs = REPO_ROOT / "pipeline_defs"
    names = []
    try:
        names = list_pipelines()
    except Exception:
        names = sorted(p.stem for p in defs.glob("*.yaml")) if defs.exists() else []

    packs = []
    skills = REPO_ROOT / "openmontage" / "skills"
    if skills.exists():
        packs = [p.name for p in skills.iterdir() if p.is_dir()]

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


def run_get_project_state(project_id: str) -> dict[str, Any]:
    _ensure_repo_on_path()
    from lib.checkpoint import (
        PROJECT_MARKER_FILENAME,
        get_completed_stages,
        get_latest_checkpoint,
        get_next_stage,
    )

    pdir = project_dir(project_id)
    if not pdir.exists():
        raise DoctorError(f"Project not found: {project_id}", code="not_found")
    root = require_projects_root()
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
        "completed_stages": completed,
        "next_stage": nxt,
        "awaiting_human": awaiting,
        "latest_checkpoint_stage": (latest or {}).get("stage"),
        "latest_checkpoint_status": (latest or {}).get("status"),
    }


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
    schema_dir = REPO_ROOT / "schemas" / "artifacts"
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
    try:
        validate_checkpoint(data)
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


def run_init_project(project_id: str, title: str, pipeline_type: str) -> dict[str, Any]:
    require_p1_writes()
    _ensure_repo_on_path()
    from lib.checkpoint import init_project

    root = require_projects_root()
    # Validate id via sandbox helper
    target = project_dir(project_id)
    path = init_project(
        project_id,
        title=title,
        pipeline_type=pipeline_type,
        pipeline_dir=root,
    )
    return {
        "project_id": project_id,
        "project_dir": str(path),
        "title": title,
        "pipeline_type": pipeline_type,
        "sandbox_root": str(root),
        "resolved": str(target),
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
) -> dict[str, Any]:
    require_p1_writes()
    _ensure_repo_on_path()
    from lib.checkpoint import write_checkpoint

    root = require_projects_root()
    project_dir(project_id)  # validate id
    try:
        artifacts = json.loads(artifacts_json) if artifacts_json else {}
    except json.JSONDecodeError as exc:
        raise DoctorError(f"artifacts_json invalid: {exc}", code="bad_request") from exc
    if not isinstance(artifacts, dict):
        raise DoctorError("artifacts_json must be an object", code="bad_request")
    metadata = {}
    if approval_note:
        metadata["approval_note"] = approval_note
    path = write_checkpoint(
        root,
        project_id,
        stage,
        status,
        artifacts,
        pipeline_type=pipeline_type or None,
        human_approval_required=human_approval_required,
        human_approved=human_approved,
        metadata=metadata or None,
    )
    return {"checkpoint_path": str(path), "stage": stage, "status": status}


def run_approve_checkpoint(
    project_id: str,
    stage: str,
    approval_text: str,
    artifacts_json: str = "{}",
    pipeline_type: str = "",
) -> dict[str, Any]:
    """Complete a gated stage only with explicit user approval text from the Agent."""
    if not approval_text or not approval_text.strip():
        raise ConfigError(
            "approve_checkpoint requires approval_text from the user's chat reply; "
            "MCP cannot invent approval."
        )
    return run_write_checkpoint(
        project_id=project_id,
        stage=stage,
        status="completed",
        artifacts_json=artifacts_json,
        pipeline_type=pipeline_type,
        human_approval_required=True,
        human_approved=True,
        approval_note=approval_text.strip(),
    )


def run_append_decision(project_id: str, decision_json: str) -> dict[str, Any]:
    require_p1_writes()
    _ensure_repo_on_path()
    from lib.checkpoint import _merge_decision_log

    root = require_projects_root()
    project_dir(project_id)
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
    _merge_decision_log(root, project_id, decision)
    return {"project_id": project_id, "appended": len(decision.get("decisions") or [])}

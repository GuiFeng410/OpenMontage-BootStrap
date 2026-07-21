"""Bootstrap / produce tool implementations for the facade MCP."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from openmontage.mcp.common.errors import ConfigError, DoctorError
from openmontage.mcp.doctor import tools as doctor_tools
from openmontage.mcp.media import tools as media_tools

REPO_ROOT = Path(__file__).resolve().parents[3]

GITHUB_CLONE_URL = "https://github.com/GuiFeng410/OpenMontage-BootStrap.git"
GITEE_CLONE_URL = "https://gitee.com/rory_-3232/open-montage-boot-strap.git"

DEFAULT_PIPER_MODEL = "zh_CN-huayan-medium"


def _require_execute(*, dry_run: bool, confirm_execute: bool, action: str) -> None:
    if dry_run:
        return
    if not confirm_execute:
        raise ConfigError(
            f"{action} requires dry_run=true (preview) or confirm_execute=true after the user approved the plan."
        )


def _ffmpeg_manual_commands() -> list[str]:
    plat = sys.platform
    if plat == "win32":
        return ["winget install Gyan.FFmpeg", "or download from https://ffmpeg.org/download.html"]
    if plat == "darwin":
        return ["brew install ffmpeg"]
    return ["sudo apt install ffmpeg  # Debian/Ubuntu", "or use your distro package manager"]


def _resolve_clone_url(source: str, url: str) -> tuple[str, str]:
    source = (source or "auto").strip().lower()
    if source == "url":
        if not url.strip():
            raise DoctorError("source=url requires a non-empty url", code="bad_request")
        return url.strip(), "url"
    if source == "github":
        return GITHUB_CLONE_URL, "github"
    if source == "gitee":
        return GITEE_CLONE_URL, "gitee"
    if source == "auto":
        return GITHUB_CLONE_URL, "auto"
    raise DoctorError(
        "source must be auto|github|gitee|url",
        code="bad_request",
    )


def list_bootstrap_tools() -> dict[str, Any]:
    return {
        "bootstrap": [
            "clone_repo",
            "detect_environment",
            "plan_install",
            "install_python_deps",
            "install_node_deps",
            "ensure_ffmpeg",
            "ensure_piper_model",
            "configure_sandbox",
            "verify_ready",
        ],
        "produce_minimal": [
            "produce_init_project",
            "produce_set_production_profile",
            "produce_write_checkpoint",
            "produce_approve_checkpoint",
            "produce_read_state",
            "produce_get_next_stage",
            "produce_tts_preflight",
            "produce_tts_sample",
            "produce_tts_generate",
            "produce_generate_subtitles",
            "produce_compose_preflight",
            "produce_compose_start",
            "produce_job_status",
            "produce_probe_media",
            "produce_read_asset_manifest",
            "produce_append_asset_manifest_entry",
            "produce_scan_copy_music",
            "produce_ensure_captions_music_dirs",
            "produce_write_copy",
            "produce_import_copy",
            "produce_segment_copy_to_subtitles",
            "produce_import_music",
            "produce_register_music",
            "produce_build_compose_inputs",
            "produce_mix_narration_and_music",
            "error_capture_context",
            "error_classify",
            "error_plan_recovery",
            "error_list_incidents",
        ],
        "not_in_v1": ["diagram", "stitch", "providers_tts", "error_apply_recovery"],
        "repo_root": str(REPO_ROOT),
        "mirrors": {"github": GITHUB_CLONE_URL, "gitee": GITEE_CLONE_URL},
    }


def clone_repo(
    target_dir: str,
    source: str = "auto",
    url: str = "",
    dry_run: bool = True,
    confirm_execute: bool = False,
    confirm_overwrite: bool = False,
) -> dict[str, Any]:
    target = Path(target_dir).expanduser().resolve()
    primary_url, label = _resolve_clone_url(source, url)
    fallback = GITEE_CLONE_URL if label == "auto" else None

    plan = {
        "action": "git_clone",
        "target_dir": str(target),
        "primary_url": primary_url,
        "fallback_url": fallback,
        "source_label": label,
    }

    if target.exists() and any(target.iterdir()):
        git_dir = target / ".git"
        if git_dir.exists():
            return {
                "dry_run": dry_run,
                "skipped": True,
                "reason": "target already a git checkout",
                "target_dir": str(target),
                "plan": plan,
            }
        if not confirm_overwrite and not dry_run:
            raise ConfigError(
                "target_dir is non-empty; set confirm_overwrite=true after user approval, or choose another path."
            )
        plan["overwrite"] = True

    if dry_run:
        return {"dry_run": True, "executed": False, "plan": plan}

    _require_execute(dry_run=False, confirm_execute=confirm_execute, action="clone_repo")

    if target.exists() and confirm_overwrite and any(target.iterdir()) and not (target / ".git").exists():
        raise DoctorError(
            "Refusing to delete non-git directory automatically. Remove it manually or pick an empty path.",
            code="unsafe_overwrite",
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    urls = [primary_url] + ([fallback] if fallback else [])
    errors: list[str] = []
    for attempt_url in urls:
        if target.exists() and (target / ".git").exists():
            break
        cmd = ["git", "clone", attempt_url, str(target)]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return {
                "dry_run": False,
                "executed": True,
                "cloned_from": attempt_url,
                "target_dir": str(target),
                "plan": plan,
            }
        errors.append(f"{attempt_url}: {(proc.stderr or proc.stdout or '').strip()}")
        if target.exists() and not any(target.iterdir()):
            try:
                target.rmdir()
            except OSError:
                pass

    raise DoctorError(
        "git clone failed for all sources. Manual commands: "
        + f"git clone {GITHUB_CLONE_URL}  OR  git clone {GITEE_CLONE_URL}. Errors: "
        + " | ".join(errors),
        code="clone_failed",
    )


def detect_environment(deep: bool = False) -> dict[str, Any]:
    data = doctor_tools.run_doctor(deep=deep)
    return {
        "doctor": data,
        "can_produce_video_now": data.get("can_produce_video_now"),
        "next_install_for_p1": data.get("next_install_for_p1"),
        "repo_root": str(REPO_ROOT),
    }


def plan_install(
    projects_dir: str = "",
    piper_model_dir: str = "",
    piper_model: str = "",
) -> dict[str, Any]:
    """Aggregate dry-run plans for Skill01 to present to the user."""
    py = install_python_deps(dry_run=True, confirm_execute=False)
    node = install_node_deps(dry_run=True, confirm_execute=False)
    ffmpeg = ensure_ffmpeg(dry_run=True, confirm_execute=False)
    piper = ensure_piper_model(
        model=piper_model or DEFAULT_PIPER_MODEL,
        model_dir=piper_model_dir,
        dry_run=True,
        confirm_execute=False,
    )
    sandbox = configure_sandbox(projects_dir=projects_dir or "", dry_run=True, confirm_execute=False)
    return {
        "summary": "Preview only — no system changes. After user OK, re-call each tool with dry_run=false and confirm_execute=true.",
        "steps": [py, node, ffmpeg, piper, sandbox],
        "manual_fallback_note": "If a step lacks admin rights, use the returned manual_commands.",
    }


def install_python_deps(
    dry_run: bool = True,
    confirm_execute: bool = False,
) -> dict[str, Any]:
    venv_dir = REPO_ROOT / ".venv"
    req = REPO_ROOT / "requirements.txt"
    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
        create_cmd = [sys.executable, "-m", "venv", str(venv_dir)]
    else:
        venv_python = venv_dir / "bin" / "python"
        create_cmd = [sys.executable, "-m", "venv", str(venv_dir)]
    pip_cmd = [
        str(venv_python if venv_python.exists() or not dry_run else sys.executable),
        "-m",
        "pip",
        "install",
        "-U",
        "pip",
    ]
    req_cmd = [
        str(venv_python if venv_python.exists() or not dry_run else sys.executable),
        "-m",
        "pip",
        "install",
        "-r",
        str(req),
    ]
    plan = {
        "action": "python_venv_and_requirements",
        "venv_dir": str(venv_dir),
        "requirements": str(req),
        "commands": [
            " ".join(create_cmd),
            f"{venv_python} -m pip install -U pip",
            f"{venv_python} -m pip install -r {req}",
        ],
        "requirements_exists": req.exists(),
    }
    if dry_run:
        return {"dry_run": True, "executed": False, "plan": plan}

    _require_execute(dry_run=False, confirm_execute=confirm_execute, action="install_python_deps")
    if not req.exists():
        raise DoctorError(f"requirements.txt missing at {req}", code="missing_requirements")

    if not venv_python.exists():
        proc = subprocess.run(create_cmd, capture_output=True, text=True, check=False, cwd=str(REPO_ROOT))
        if proc.returncode != 0:
            raise DoctorError(
                f"venv create failed: {(proc.stderr or proc.stdout or '').strip()}",
                code="venv_failed",
            )

    for cmd in (
        [str(venv_python), "-m", "pip", "install", "-U", "pip"],
        [str(venv_python), "-m", "pip", "install", "-r", str(req)],
    ):
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=str(REPO_ROOT))
        if proc.returncode != 0:
            raise DoctorError(
                f"pip failed ({' '.join(cmd)}): {(proc.stderr or proc.stdout or '').strip()}",
                code="pip_failed",
            )

    return {
        "dry_run": False,
        "executed": True,
        "venv_python": str(venv_python),
        "hint": "Point OpenClaw MCP command to this venv python.",
        "plan": plan,
    }


def install_node_deps(
    dry_run: bool = True,
    confirm_execute: bool = False,
) -> dict[str, Any]:
    composer = REPO_ROOT / "remotion-composer"
    plan = {
        "action": "npm_install_remotion",
        "cwd": str(composer),
        "commands": [f"cd {composer}", "npm install"],
        "package_json_exists": (composer / "package.json").exists(),
        "node_modules_exists": (composer / "node_modules").exists(),
        "node_on_path": bool(shutil.which("node")),
        "npm_on_path": bool(shutil.which("npm")),
    }
    if dry_run:
        return {"dry_run": True, "executed": False, "plan": plan}

    _require_execute(dry_run=False, confirm_execute=confirm_execute, action="install_node_deps")
    if not plan["package_json_exists"]:
        raise DoctorError("remotion-composer/package.json missing", code="missing_remotion")
    if not shutil.which("npm"):
        raise DoctorError(
            "npm not found. Install Node.js 18+ first. "
            + ("winget install OpenJS.NodeJS.LTS" if sys.platform == "win32" else "brew install node / apt install nodejs npm"),
            code="npm_missing",
        )

    proc = subprocess.run(
        ["npm", "install"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(composer),
    )
    if proc.returncode != 0:
        raise DoctorError(
            f"npm install failed: {(proc.stderr or proc.stdout or '').strip()}",
            code="npm_failed",
        )
    return {"dry_run": False, "executed": True, "plan": plan}


def ensure_ffmpeg(
    dry_run: bool = True,
    confirm_execute: bool = False,
) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    manual = _ffmpeg_manual_commands()
    plan = {
        "action": "ensure_ffmpeg",
        "ffmpeg_present": bool(ffmpeg),
        "ffprobe_present": bool(ffprobe),
        "ffmpeg_path": ffmpeg,
        "ffprobe_path": ffprobe,
        "manual_commands": manual,
        "auto_attempt": "winget install Gyan.FFmpeg" if sys.platform == "win32" else None,
        "policy": "If auto install fails or lacks admin rights, skip and return manual_commands.",
    }
    if ffmpeg and ffprobe:
        return {"dry_run": dry_run, "ready": True, "executed": False, "plan": plan}
    if dry_run:
        return {"dry_run": True, "ready": False, "executed": False, "plan": plan}

    _require_execute(dry_run=False, confirm_execute=confirm_execute, action="ensure_ffmpeg")

    if sys.platform == "win32" and shutil.which("winget"):
        proc = subprocess.run(
            ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-package-agreements", "--accept-source-agreements"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return {
                "dry_run": False,
                "executed": True,
                "ready": bool(shutil.which("ffmpeg")),
                "method": "winget",
                "plan": plan,
                "note": "Restart the shell/OpenClaw if PATH was updated.",
            }
        return {
            "dry_run": False,
            "executed": False,
            "ready": False,
            "skipped_no_admin_or_failed": True,
            "manual_commands": manual,
            "error": (proc.stderr or proc.stdout or "").strip()[:2000],
            "plan": plan,
        }

    return {
        "dry_run": False,
        "executed": False,
        "ready": False,
        "skipped_no_admin_or_failed": True,
        "manual_commands": manual,
        "plan": plan,
    }


def ensure_piper_model(
    model: str = DEFAULT_PIPER_MODEL,
    model_dir: str = "",
    dry_run: bool = True,
    confirm_execute: bool = False,
) -> dict[str, Any]:
    model = model or DEFAULT_PIPER_MODEL
    dest = Path(
        model_dir
        or os.environ.get("PIPER_MODEL_DIR")
        or (Path.home() / ".piper" / "models")
    ).expanduser()
    onnx = dest / f"{model}.onnx"
    plan = {
        "action": "download_piper_voice",
        "model": model,
        "model_dir": str(dest),
        "onnx_path": str(onnx),
        "already_present": onnx.exists(),
        "commands": [
            f"pip install piper-tts",
            f'python -m piper.download_voices {model} --download-dir "{dest}"',
        ],
        "env_to_set": {
            "PIPER_MODEL_DIR": str(dest),
            "OPENMONTAGE_PIPER_MODEL": model,
        },
    }
    if onnx.exists():
        return {"dry_run": dry_run, "ready": True, "executed": False, "plan": plan}
    if dry_run:
        return {"dry_run": True, "ready": False, "executed": False, "plan": plan}

    _require_execute(dry_run=False, confirm_execute=confirm_execute, action="ensure_piper_model")
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "piper.download_voices", model, "--download-dir", str(dest)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not onnx.exists():
        return {
            "dry_run": False,
            "executed": False,
            "ready": False,
            "skipped_or_failed": True,
            "manual_commands": plan["commands"],
            "error": (proc.stderr or proc.stdout or "").strip()[:2000],
            "plan": plan,
        }
    return {
        "dry_run": False,
        "executed": True,
        "ready": True,
        "plan": plan,
        "env_to_set": plan["env_to_set"],
    }


def configure_sandbox(
    projects_dir: str = "",
    dry_run: bool = True,
    confirm_execute: bool = False,
) -> dict[str, Any]:
    if projects_dir.strip():
        root = Path(projects_dir).expanduser().resolve()
    else:
        root = (REPO_ROOT / "projects").resolve()
    plan = {
        "action": "configure_sandbox",
        "projects_dir": str(root),
        "env_to_set": {
            "OPENMONTAGE_PROJECTS_DIR": str(root),
            "PYTHONUTF8": "1",
            "OPENMONTAGE_P1_ALLOW_WRITES": "true",
        },
        "create_directory": not root.exists(),
    }
    if dry_run:
        return {"dry_run": True, "executed": False, "plan": plan}

    _require_execute(dry_run=False, confirm_execute=confirm_execute, action="configure_sandbox")
    root.mkdir(parents=True, exist_ok=True)
    os.environ["OPENMONTAGE_PROJECTS_DIR"] = str(root)
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ["OPENMONTAGE_P1_ALLOW_WRITES"] = "true"
    return {
        "dry_run": False,
        "executed": True,
        "projects_dir": str(root),
        "env_applied_to_process": plan["env_to_set"],
        "note": "Also set these in OpenClaw MCP env so they persist across restarts.",
        "plan": plan,
    }


def verify_ready(deep: bool = False) -> dict[str, Any]:
    data = doctor_tools.run_doctor(deep=deep)
    return {
        "can_produce_video_now": bool(data.get("can_produce_video_now")),
        "next_install_for_p1": data.get("next_install_for_p1"),
        "tier": data.get("tier"),
        "doctor_summary_keys": sorted(data.keys()),
        "ready_for_skill02": bool(data.get("can_produce_video_now")),
    }


# --- produce_* thin wrappers (minimal explainer surface) ---


def produce_init_project(project_id: str, title: str, pipeline_type: str = "animated-explainer") -> dict[str, Any]:
    return doctor_tools.run_init_project(project_id, title, pipeline_type)


def produce_set_production_profile(
    project_id: str,
    production_tier: str,
    visual_source: str = "",
    tts_source: str = "",
) -> dict[str, Any]:
    return doctor_tools.run_set_production_profile(
        project_id,
        production_tier,
        visual_source,
        tts_source,
    )


def produce_write_checkpoint(
    project_id: str,
    stage: str,
    status: str,
    artifacts_json: str = "{}",
    pipeline_type: str = "",
    human_approval_required: bool = False,
    human_approved: bool = False,
    approval_note: str = "",
) -> dict[str, Any]:
    return doctor_tools.run_write_checkpoint(
        project_id,
        stage,
        status,
        artifacts_json,
        pipeline_type,
        human_approval_required,
        human_approved,
        approval_note,
    )


def produce_approve_checkpoint(
    project_id: str,
    stage: str,
    approval_text: str,
    artifacts_json: str = "{}",
    pipeline_type: str = "",
) -> dict[str, Any]:
    return doctor_tools.run_approve_checkpoint(
        project_id,
        stage,
        approval_text,
        artifacts_json,
        pipeline_type,
    )


def produce_read_state(project_id: str) -> dict[str, Any]:
    return doctor_tools.run_get_project_state(project_id)


def produce_get_next_stage(project_id: str) -> dict[str, Any]:
    return doctor_tools.run_get_next_stage(project_id)


def produce_tts_preflight() -> dict[str, Any]:
    return media_tools.tts_preflight()


def produce_tts_sample(
    text: str,
    output_path: str = "",
    model: str = "",
    length_scale: float = 1.0,
) -> dict[str, Any]:
    return media_tools.tts_sample(text, output_path, model, length_scale)


def produce_tts_generate(
    text: str,
    output_path: str,
    model: str = "",
    length_scale: float = 1.0,
    confirm_sample_ok: bool = False,
) -> dict[str, Any]:
    return media_tools.tts_generate(text, output_path, model, length_scale, confirm_sample_ok)


def produce_generate_subtitles(
    segments_json: str,
    output_path: str = "",
    fmt: str = "srt",
) -> dict[str, Any]:
    return media_tools.generate_subtitles(segments_json, output_path, fmt)


def produce_compose_preflight(
    edit_decisions_json: str = "{}",
    asset_manifest_json: str = "{}",
) -> dict[str, Any]:
    return media_tools.compose_preflight(edit_decisions_json, asset_manifest_json)


def produce_compose_start(
    edit_decisions_json: str,
    asset_manifest_json: str,
    output_path: str = "",
    proposal_packet_json: str = "",
) -> dict[str, Any]:
    return media_tools.compose_start(
        edit_decisions_json,
        asset_manifest_json,
        output_path,
        proposal_packet_json,
    )


def produce_job_status(job_id: str) -> dict[str, Any]:
    return media_tools.job_status(job_id)


def produce_probe_media(path: str) -> dict[str, Any]:
    return media_tools.probe_media(path)


def produce_read_asset_manifest(project_id: str) -> dict[str, Any]:
    from openmontage.mcp.common.asset_manifest import load_asset_manifest, manifest_path

    manifest = load_asset_manifest(project_id)
    path = manifest_path(project_id)
    return {
        "project_id": project_id,
        "asset_manifest_path": str(path),
        "exists": path.exists(),
        "asset_count": len(manifest.get("assets") or []),
        "asset_manifest": manifest,
        "asset_manifest_json": json.dumps(manifest, ensure_ascii=False),
    }


def produce_append_asset_manifest_entry(project_id: str, entry_json: str) -> dict[str, Any]:
    """Manual upsert of one asset_manifest entry (e.g. after paid gen or local file)."""
    from openmontage.mcp.common.asset_manifest import upsert_asset_entry
    from openmontage.mcp.doctor.tools import require_p1_writes

    require_p1_writes()
    try:
        entry = json.loads(entry_json) if entry_json else {}
    except json.JSONDecodeError as exc:
        raise DoctorError(f"entry_json invalid: {exc}", code="bad_request") from exc
    return upsert_asset_entry(project_id, entry)


def produce_scan_copy_music(project_id: str) -> dict[str, Any]:
    from openmontage.mcp.common.captions_music import scan_copy_music

    return scan_copy_music(project_id)


def produce_ensure_captions_music_dirs(project_id: str) -> dict[str, Any]:
    from openmontage.mcp.common.captions_music import ensure_captions_music_dirs
    from openmontage.mcp.doctor.tools import require_p1_writes

    require_p1_writes()
    return ensure_captions_music_dirs(project_id)


def produce_write_copy(
    project_id: str,
    content: str,
    filename: str = "script.txt",
    confirm: bool = False,
) -> dict[str, Any]:
    from openmontage.mcp.common.captions_music import write_copy
    from openmontage.mcp.doctor.tools import require_p1_writes

    require_p1_writes()
    return write_copy(project_id, content, filename=filename, confirm=confirm)


def produce_import_copy(
    project_id: str,
    source_path: str,
    filename: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    from openmontage.mcp.common.captions_music import import_copy
    from openmontage.mcp.doctor.tools import require_p1_writes

    require_p1_writes()
    return import_copy(project_id, source_path, filename=filename, confirm=confirm)


def produce_segment_copy_to_subtitles(
    project_id: str,
    filename: str = "",
    chars_per_second: float = 4.0,
    min_cue_seconds: float = 1.2,
    max_cue_chars: int = 42,
    fmt: str = "srt",
    scene_id: str = "scene_01",
    confirm_copy_ok: bool = False,
) -> dict[str, Any]:
    """Split assets/copy → subtitle segments → write assets/subs → register manifest."""
    from openmontage.mcp.common.asset_manifest import path_relative_to_project, upsert_asset_entry
    from openmontage.mcp.common.captions_music import (
        SUBS_DIR,
        read_primary_copy,
        split_copy_into_cues,
    )
    from openmontage.mcp.doctor.tools import require_p1_writes

    require_p1_writes()
    if not confirm_copy_ok:
        raise ConfigError(
            "produce_segment_copy_to_subtitles requires confirm_copy_ok=true "
            "after the user approved the copy/script."
        )
    copy_path, text = read_primary_copy(project_id, filename=filename)
    segments = split_copy_into_cues(
        text,
        chars_per_second=chars_per_second,
        min_cue_seconds=min_cue_seconds,
        max_cue_chars=max_cue_chars,
    )
    if not segments:
        raise DoctorError("copy produced zero subtitle segments", code="bad_request")

    out_name = "captions.srt" if fmt == "srt" else f"captions.{fmt}"
    out_rel = f"{project_id}/{SUBS_DIR}/{out_name}"
    gen = media_tools.generate_subtitles(
        json.dumps(segments, ensure_ascii=False),
        output_path=out_rel,
        fmt=fmt,
    )
    abs_out = gen.get("output_path") or out_rel
    entry = {
        "id": "subs_main",
        "type": "subtitle",
        "path": path_relative_to_project(project_id, abs_out),
        "source_tool": "subtitle_gen",
        "scene_id": (scene_id or "scene_01").strip() or "scene_01",
        "subtype": "from_copy",
        "generation_summary": f"segmented from {copy_path.name}",
        "cost_usd": 0.0,
    }
    registered = upsert_asset_entry(project_id, entry)
    preview = segments[:3]
    return {
        "project_id": project_id,
        "copy_path": str(copy_path),
        "subtitle_path": abs_out,
        "format": fmt,
        "segment_count": len(segments),
        "duration_estimate_seconds": segments[-1]["end"] if segments else 0.0,
        "segments_preview": preview,
        "segments_json": json.dumps(segments, ensure_ascii=False),
        "generate": gen,
        "manifest_entry": entry,
        "asset_manifest_path": registered["asset_manifest_path"],
        "asset_count": registered["asset_count"],
        "note": (
            "Timing is heuristic (chars/sec) until real TTS/ASR timestamps exist. "
            "Custom cue timing/position is out of scope for phase B."
        ),
    }


def produce_import_music(
    project_id: str,
    source_path: str,
    filename: str = "",
    confirm: bool = False,
    asset_id: str = "music_bgm",
    scene_id: str = "scene_01",
    volume: float = 0.25,
) -> dict[str, Any]:
    from openmontage.mcp.common.captions_music import import_music
    from openmontage.mcp.doctor.tools import require_p1_writes

    require_p1_writes()
    return import_music(
        project_id,
        source_path,
        filename=filename,
        confirm=confirm,
        asset_id=asset_id,
        scene_id=scene_id,
        volume=volume,
    )


def produce_register_music(
    project_id: str,
    filename: str = "",
    asset_id: str = "music_bgm",
    scene_id: str = "scene_01",
    volume: float = 0.25,
    confirm: bool = False,
) -> dict[str, Any]:
    from openmontage.mcp.common.captions_music import register_music
    from openmontage.mcp.doctor.tools import require_p1_writes

    require_p1_writes()
    return register_music(
        project_id,
        filename=filename,
        asset_id=asset_id,
        scene_id=scene_id,
        volume=volume,
        confirm=confirm,
    )


def produce_build_compose_inputs(
    project_id: str,
    music_asset_id: str = "music_bgm",
    subtitle_asset_id: str = "subs_main",
    music_volume: float = 0.25,
    include_music: bool = True,
    include_subs: bool = True,
) -> dict[str, Any]:
    from openmontage.mcp.common.captions_music import build_compose_inputs

    return build_compose_inputs(
        project_id,
        music_asset_id=music_asset_id,
        subtitle_asset_id=subtitle_asset_id,
        music_volume=music_volume,
        include_music=include_music,
        include_subs=include_subs,
    )


def produce_mix_narration_and_music(
    project_id: str,
    narration_path: str = "",
    music_filename: str = "",
    music_volume: float = 0.2,
    duck_db: float = 12.0,
    confirm: bool = False,
) -> dict[str, Any]:
    """Optional FFmpeg duck mix: narration + BGM → assets/audio/mixed.wav + manifest."""
    from openmontage.mcp.common.asset_manifest import path_relative_to_project, upsert_asset_entry
    from openmontage.mcp.common.captions_music import AUDIO_DIR, _pick_music_file, ensure_captions_music_dirs
    from openmontage.mcp.common.sandbox import project_dir, resolve_under_projects
    from openmontage.mcp.doctor.tools import require_p1_writes

    require_p1_writes()
    if not confirm:
        raise ConfigError(
            "produce_mix_narration_and_music requires confirm=true after the user approved mixing."
        )
    ensure_captions_music_dirs(project_id)
    pdir = project_dir(project_id)

    if narration_path:
        narr = resolve_under_projects(narration_path)
    else:
        audio_dir = pdir / AUDIO_DIR
        candidates = sorted(
            [
                p
                for p in audio_dir.glob("*")
                if p.is_file() and p.suffix.lower() in {".wav", ".mp3", ".m4a", ".aac"}
                and p.name != "mixed.wav"
            ]
        )
        if not candidates:
            raise DoctorError(
                "No narration under assets/audio/. Run produce TTS first or pass narration_path.",
                code="not_found",
            )
        narr = candidates[0]

    if not narr.exists():
        raise DoctorError(f"narration not found: {narr}", code="not_found")

    music = _pick_music_file(project_id, filename=music_filename)
    out_rel = f"{project_id}/{AUDIO_DIR}/mixed.wav"
    # duck_level is attenuation in dB (negative). music_volume retained for docs only.
    level = -abs(float(duck_db))
    _ = music_volume
    mix = media_tools.mix_audio(
        "duck",
        json.dumps(
            {
                "primary_audio": str(narr),
                "secondary_audio": str(music),
                "output_path": out_rel,
                "duck_level": level,
            },
            ensure_ascii=False,
        ),
    )
    if not mix.get("success"):
        raise DoctorError(
            f"audio mix failed: {mix.get('error')}. Ensure ffmpeg is on PATH. "
            f"Dependency note: uses audio_mixer duck operation.",
            code="mix_failed",
        )
    abs_out = str(resolve_under_projects(out_rel))
    if mix.get("data") and isinstance(mix["data"], dict) and mix["data"].get("output_path"):
        abs_out = str(mix["data"]["output_path"])
    entry = {
        "id": "audio_mixed",
        "type": "audio",
        "path": path_relative_to_project(project_id, abs_out),
        "source_tool": "audio_mixer",
        "scene_id": "scene_01",
        "subtype": "narration_plus_bgm",
        "generation_summary": f"duck mix {narr.name} + {music.name}",
        "cost_usd": 0.0,
    }
    registered = upsert_asset_entry(project_id, entry)
    return {
        "project_id": project_id,
        "narration_path": str(narr),
        "music_path": str(music),
        "mixed_path": abs_out,
        "mix": mix,
        "manifest_entry": entry,
        "asset_manifest_path": registered["asset_manifest_path"],
        "asset_count": registered["asset_count"],
        "note": (
            "Mixed file registered as audio_mixed. "
            "FFmpeg compose paths that accept a single audio bed can use this file; "
            "Remotion paths may still prefer edit_decisions.audio.music + narration assets."
        ),
    }


def error_capture_context(
    project_id: str,
    tool_name: str,
    stage: str,
    stderr: str,
    stdout: str = "",
    paths_json: str = "",
) -> dict[str, Any]:
    """Capture tool stderr into artifacts/error_recovery.json (phase 1)."""
    from openmontage.mcp.common.error_recovery import error_capture_context as _capture

    return _capture(
        project_id,
        tool_name,
        stage,
        stderr,
        stdout=stdout,
        paths_json=paths_json,
    )


def error_classify(project_id: str, incident_id: str) -> dict[str, Any]:
    """Classify a stored incident against known playbooks."""
    from openmontage.mcp.common.error_recovery import error_classify as _classify

    return _classify(project_id, incident_id)


def error_plan_recovery(
    project_id: str,
    incident_id: str,
    playbook_id: str = "",
) -> dict[str, Any]:
    """Return recovery plan only — does not execute (phase 1)."""
    from openmontage.mcp.common.error_recovery import error_plan_recovery as _plan

    return _plan(project_id, incident_id, playbook_id=playbook_id)


def error_list_incidents(project_id: str) -> dict[str, Any]:
    """List error_recovery incidents for a project."""
    from openmontage.mcp.common.error_recovery import error_list_incidents as _list

    return _list(project_id)

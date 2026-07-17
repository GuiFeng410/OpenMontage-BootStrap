"""P1 media tool implementations — sandboxed BaseTool wrappers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from openmontage.mcp.common.errors import ConfigError, DoctorError
from openmontage.mcp.common.jobs import cancel_job, create_job, read_job, start_background, update_job
from openmontage.mcp.common.registry import get_registry, get_tool, tool_result_to_dict
from openmontage.mcp.common.sandbox import require_projects_root, resolve_under_projects

MEDIA_TOOL_NAMES = [
    "piper_tts",
    "tts_selector",
    "diagram_gen",
    "subtitle_gen",
    "video_compose",
    "audio_mixer",
    "video_stitch",
]


def _require_media_writes() -> None:
    """Media MCP may write only inside OPENMONTAGE_PROJECTS_DIR."""
    require_projects_root()


def _sandbox_output(path: str | None, default_rel: str) -> str:
    if not path:
        path = default_rel
    resolved = resolve_under_projects(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)


def _parse_json_obj(raw: str | None, field: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DoctorError(f"Invalid JSON for {field}: {exc}", code="bad_request") from exc
    if not isinstance(data, dict):
        raise DoctorError(f"{field} must be a JSON object", code="bad_request")
    return data


def _parse_json_any(raw: str | None, field: str) -> Any:
    if raw is None or raw == "":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DoctorError(f"Invalid JSON for {field}: {exc}", code="bad_request") from exc


def list_media_tools() -> dict[str, Any]:
    reg = get_registry()
    tools = getattr(reg, "_tools", {}) or {}
    rows = []
    for name in MEDIA_TOOL_NAMES:
        tool = tools.get(name)
        if tool is None:
            rows.append({"name": name, "status": "missing", "available": False})
            continue
        info = tool.get_info()
        rows.append(
            {
                "name": name,
                "status": info.get("status"),
                "available": info.get("status") == "available",
                "capability": info.get("capability"),
                "provider": info.get("provider"),
                "install_instructions": info.get("install_instructions"),
            }
        )
    return {"tools": rows, "projects_dir": str(require_projects_root())}


def tts_preflight() -> dict[str, Any]:
    piper = shutil.which("piper") or shutil.which("piper-tts")
    model_dir = Path(
        os.environ.get("PIPER_MODEL_DIR") or (Path.home() / ".piper" / "models")
    ).expanduser()
    models = sorted(p.name for p in model_dir.glob("*.onnx")) if model_dir.exists() else []
    default_model = os.environ.get("OPENMONTAGE_PIPER_MODEL", "zh_CN-huayan-medium")
    return {
        "binary": piper,
        "binary_ok": bool(piper),
        "model_dir": str(model_dir),
        "models": models,
        "default_model": default_model,
        "default_model_present": any(default_model in m for m in models) or f"{default_model}.onnx" in models,
        "ready": bool(piper) and bool(models),
    }


def tts_sample(
    text: str,
    output_path: str = "",
    model: str = "",
    length_scale: float = 1.0,
) -> dict[str, Any]:
    _require_media_writes()
    if not text.strip():
        raise DoctorError("text is required", code="bad_request")
    out = _sandbox_output(output_path or "assets/audio/sample.wav", "assets/audio/sample.wav")
    model_name = model or os.environ.get("OPENMONTAGE_PIPER_MODEL", "zh_CN-huayan-medium")
    # Resolve model path if only slug given
    model_dir = Path(os.environ.get("PIPER_MODEL_DIR") or (Path.home() / ".piper" / "models"))
    model_path = model_name
    candidate = model_dir / f"{model_name}.onnx"
    if candidate.exists():
        model_path = str(candidate)
    tool = get_tool("piper_tts")
    result = tool.execute(
        {
            "text": text,
            "model": model_path,
            "output_path": out,
            "length_scale": length_scale,
        }
    )
    payload = tool_result_to_dict(result)
    payload["output_path"] = out
    payload["sample_only"] = True
    return payload


def tts_generate(
    text: str,
    output_path: str,
    model: str = "",
    length_scale: float = 1.0,
    confirm_sample_ok: bool = False,
) -> dict[str, Any]:
    _require_media_writes()
    if not confirm_sample_ok:
        raise ConfigError(
            "tts_generate requires confirm_sample_ok=true after the user approved tts_sample."
        )
    out = _sandbox_output(output_path, "assets/audio/narration.wav")
    model_name = model or os.environ.get("OPENMONTAGE_PIPER_MODEL", "zh_CN-huayan-medium")
    model_dir = Path(os.environ.get("PIPER_MODEL_DIR") or (Path.home() / ".piper" / "models"))
    candidate = model_dir / f"{model_name}.onnx"
    model_path = str(candidate) if candidate.exists() else model_name
    tool = get_tool("piper_tts")
    result = tool.execute(
        {
            "text": text,
            "model": model_path,
            "output_path": out,
            "length_scale": length_scale,
        }
    )
    payload = tool_result_to_dict(result)
    payload["output_path"] = out
    return payload


def generate_diagram(
    diagram_type: str = "boxes",
    definition: str = "",
    boxes_json: str = "[]",
    title: str = "",
    output_path: str = "",
    theme: str = "dark",
) -> dict[str, Any]:
    _require_media_writes()
    out = _sandbox_output(output_path or "assets/images/diagram.png", "assets/images/diagram.png")
    boxes = _parse_json_any(boxes_json, "boxes_json") or []
    tool = get_tool("diagram_gen")
    inputs: dict[str, Any] = {
        "diagram_type": diagram_type,
        "output_path": out,
        "theme": theme,
    }
    if definition:
        inputs["definition"] = definition
    if boxes:
        inputs["boxes"] = boxes
    if title:
        inputs["title"] = title
    result = tool.execute(inputs)
    payload = tool_result_to_dict(result)
    payload["output_path"] = out
    return payload


def generate_subtitles(
    segments_json: str,
    output_path: str = "",
    fmt: str = "srt",
) -> dict[str, Any]:
    _require_media_writes()
    segments = _parse_json_any(segments_json, "segments_json")
    if not isinstance(segments, list):
        raise DoctorError("segments_json must be a JSON array", code="bad_request")
    out = _sandbox_output(output_path or "assets/audio/subtitles.srt", "assets/audio/subtitles.srt")
    tool = get_tool("subtitle_gen")
    result = tool.execute({"segments": segments, "format": fmt, "output_path": out})
    payload = tool_result_to_dict(result)
    payload["output_path"] = out
    return payload


def compose_preflight(
    edit_decisions_json: str = "{}",
    asset_manifest_json: str = "{}",
) -> dict[str, Any]:
    tool = get_tool("video_compose")
    inputs = {
        "operation": "render",
        "edit_decisions": _parse_json_obj(edit_decisions_json, "edit_decisions_json"),
        "asset_manifest": _parse_json_obj(asset_manifest_json, "asset_manifest_json"),
    }
    dry = tool.dry_run(inputs)
    info = tool.get_info()
    return {
        "tool_status": info.get("status"),
        "render_engines": info.get("render_engines"),
        "dry_run": dry,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "node": bool(shutil.which("node")),
    }


def compose_start(
    edit_decisions_json: str,
    asset_manifest_json: str,
    output_path: str = "",
    proposal_packet_json: str = "",
) -> dict[str, Any]:
    _require_media_writes()
    out = _sandbox_output(output_path or "renders/final.mp4", "renders/final.mp4")
    edit = _parse_json_obj(edit_decisions_json, "edit_decisions_json")
    manifest = _parse_json_obj(asset_manifest_json, "asset_manifest_json")
    proposal = _parse_json_obj(proposal_packet_json, "proposal_packet_json") if proposal_packet_json else None

    job = create_job(
        "compose_render",
        meta={"output_path": out, "operation": "render"},
    )

    def worker(job_id: str) -> None:
        if read_job(job_id).get("status") == "cancelled":
            return
        update_job(job_id, progress=0.2)
        tool = get_tool("video_compose")
        inputs: dict[str, Any] = {
            "operation": "render",
            "edit_decisions": edit,
            "asset_manifest": manifest,
            "output_path": out,
        }
        if proposal:
            inputs["proposal_packet"] = proposal
        result = tool.execute(inputs)
        payload = tool_result_to_dict(result)
        if not payload.get("success"):
            update_job(job_id, status="failed", error=payload.get("error") or "compose failed", result=payload)
            return
        update_job(job_id, result=payload, progress=0.95)

    start_background(job["job_id"], worker)
    return {"job_id": job["job_id"], "status": "queued", "output_path": out}


def job_status(job_id: str) -> dict[str, Any]:
    return read_job(job_id)


def job_cancel(job_id: str) -> dict[str, Any]:
    return cancel_job(job_id)


def probe_media(path: str) -> dict[str, Any]:
    resolved = resolve_under_projects(path)
    if not resolved.exists():
        raise DoctorError(f"Media not found: {resolved}", code="not_found")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise ConfigError("ffprobe not found on PATH")
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(resolved),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise DoctorError(f"ffprobe failed: {proc.stderr}", code="probe_failed")
    data = json.loads(proc.stdout or "{}")
    return {"path": str(resolved), "probe": data}


def mix_audio(operation: str, inputs_json: str) -> dict[str, Any]:
    _require_media_writes()
    inputs = _parse_json_obj(inputs_json, "inputs_json")
    inputs["operation"] = operation
    # Sandbox any path-like fields we know
    for key in ("output_path", "primary_audio", "secondary_audio", "input_path"):
        if key in inputs and isinstance(inputs[key], str) and inputs[key]:
            if key == "output_path":
                inputs[key] = _sandbox_output(inputs[key], inputs[key])
            else:
                inputs[key] = str(resolve_under_projects(inputs[key]))
    tool = get_tool("audio_mixer")
    result = tool.execute(inputs)
    return tool_result_to_dict(result)


def stitch_video(inputs_json: str) -> dict[str, Any]:
    _require_media_writes()
    inputs = _parse_json_obj(inputs_json, "inputs_json")
    if inputs.get("output_path"):
        inputs["output_path"] = _sandbox_output(inputs["output_path"], inputs["output_path"])
    tool = get_tool("video_stitch")
    result = tool.execute(inputs)
    return tool_result_to_dict(result)

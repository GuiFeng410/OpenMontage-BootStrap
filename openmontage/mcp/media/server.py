"""OpenMontage media MCP server (stdio) — P1 zero-key media tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from openmontage.mcp.common.envelope import fail, ok
from openmontage.mcp.media import tools as T

mcp = FastMCP(
    "openmontage-media",
    instructions=(
        "OpenMontage P1 media tools: Piper TTS, diagrams, subtitles, "
        "compose jobs, probe/mix/stitch. All writes stay under OPENMONTAGE_PROJECTS_DIR."
    ),
)


def _wrap(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return ok(fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001
        return fail(exc)


@mcp.tool()
def list_media_tools() -> dict[str, Any]:
    """List zero-key media BaseTools and availability."""
    return _wrap(T.list_media_tools)


@mcp.tool()
def tts_preflight() -> dict[str, Any]:
    """Check Piper binary and voice models."""
    return _wrap(T.tts_preflight)


@mcp.tool()
def tts_sample(
    text: str,
    output_path: str = "",
    model: str = "",
    length_scale: float = 1.0,
) -> dict[str, Any]:
    """Generate a short TTS sample for human listen-check (sandbox path)."""
    return _wrap(T.tts_sample, text, output_path, model, length_scale)


@mcp.tool()
def tts_generate(
    text: str,
    output_path: str,
    model: str = "",
    length_scale: float = 1.0,
    confirm_sample_ok: bool = False,
) -> dict[str, Any]:
    """Batch TTS after sample approval (confirm_sample_ok=true required)."""
    return _wrap(T.tts_generate, text, output_path, model, length_scale, confirm_sample_ok)


@mcp.tool()
def generate_diagram(
    diagram_type: str = "boxes",
    definition: str = "",
    boxes_json: str = "[]",
    title: str = "",
    output_path: str = "",
    theme: str = "dark",
) -> dict[str, Any]:
    """Generate a diagram image into the projects sandbox."""
    return _wrap(T.generate_diagram, diagram_type, definition, boxes_json, title, output_path, theme)


@mcp.tool()
def generate_subtitles(
    segments_json: str,
    output_path: str = "",
    fmt: str = "srt",
) -> dict[str, Any]:
    """Generate SRT/VTT/JSON subtitles from transcript segments JSON."""
    return _wrap(T.generate_subtitles, segments_json, output_path, fmt)


@mcp.tool()
def compose_preflight(
    edit_decisions_json: str = "{}",
    asset_manifest_json: str = "{}",
) -> dict[str, Any]:
    """Dry-run compose dependencies and runtime engines."""
    return _wrap(T.compose_preflight, edit_decisions_json, asset_manifest_json)


@mcp.tool()
def compose_start(
    edit_decisions_json: str,
    asset_manifest_json: str,
    output_path: str = "",
    proposal_packet_json: str = "",
) -> dict[str, Any]:
    """Start a background Remotion/FFmpeg compose job; poll with job_status."""
    return _wrap(
        T.compose_start,
        edit_decisions_json,
        asset_manifest_json,
        output_path,
        proposal_packet_json,
    )


@mcp.tool()
def job_status(job_id: str) -> dict[str, Any]:
    """Poll a background job started by compose_start."""
    return _wrap(T.job_status, job_id)


@mcp.tool()
def job_cancel(job_id: str) -> dict[str, Any]:
    """Request cancellation of a background job."""
    return _wrap(T.job_cancel, job_id)


@mcp.tool()
def probe_media(path: str) -> dict[str, Any]:
    """ffprobe a media file inside the projects sandbox."""
    return _wrap(T.probe_media, path)


@mcp.tool()
def mix_audio(operation: str, inputs_json: str) -> dict[str, Any]:
    """Run audio_mixer with sandboxed paths (inputs_json object)."""
    return _wrap(T.mix_audio, operation, inputs_json)


@mcp.tool()
def stitch_video(inputs_json: str) -> dict[str, Any]:
    """Run video_stitch with sandboxed output path."""
    return _wrap(T.stitch_video, inputs_json)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

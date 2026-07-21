"""OpenMontage bootstrap facade MCP server (stdio)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from openmontage.mcp.bootstrap import tools as T
from openmontage.mcp.common.envelope import fail, ok

mcp = FastMCP(
    "openmontage-bootstrap",
    instructions=(
        "OpenMontage BootStrap facade: one MCP for env setup + minimal zero-key produce. "
        "High-risk install tools default dry_run=true; after user approves the plan, "
        "call again with dry_run=false and confirm_execute=true. "
        "If admin rights are missing, return manual_commands instead of failing hard. "
        "Clone mirrors: GitHub first, then Gitee. "
        "Produce surface is explainer-minimal only (no diagram/stitch). "
        "Paid TTS is NOT included — optional teaching points to providers-tts."
    ),
)


def _wrap(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return ok(fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001
        return fail(exc)


@mcp.tool()
def list_bootstrap_tools() -> dict[str, Any]:
    """List bootstrap_* and produce_* tools exposed by this facade."""
    return _wrap(T.list_bootstrap_tools)


@mcp.tool()
def clone_repo(
    target_dir: str,
    source: str = "auto",
    url: str = "",
    dry_run: bool = True,
    confirm_execute: bool = False,
    confirm_overwrite: bool = False,
) -> dict[str, Any]:
    """Clone BootStrap repo (auto=GitHub then Gitee). Defaults to dry_run preview."""
    return _wrap(
        T.clone_repo,
        target_dir,
        source,
        url,
        dry_run,
        confirm_execute,
        confirm_overwrite,
    )


@mcp.tool()
def detect_environment(deep: bool = False) -> dict[str, Any]:
    """Run doctor probe and return can_produce / next install hints."""
    return _wrap(T.detect_environment, deep)


@mcp.tool()
def plan_install(
    projects_dir: str = "",
    piper_model_dir: str = "",
    piper_model: str = "",
) -> dict[str, Any]:
    """Aggregate dry-run install plans for user review (no side effects)."""
    return _wrap(T.plan_install, projects_dir, piper_model_dir, piper_model)


@mcp.tool()
def install_python_deps(dry_run: bool = True, confirm_execute: bool = False) -> dict[str, Any]:
    """Create .venv and pip install -r requirements.txt (dry_run by default)."""
    return _wrap(T.install_python_deps, dry_run, confirm_execute)


@mcp.tool()
def install_node_deps(dry_run: bool = True, confirm_execute: bool = False) -> dict[str, Any]:
    """npm install in remotion-composer (dry_run by default)."""
    return _wrap(T.install_node_deps, dry_run, confirm_execute)


@mcp.tool()
def ensure_ffmpeg(dry_run: bool = True, confirm_execute: bool = False) -> dict[str, Any]:
    """Ensure ffmpeg/ffprobe; on failure return manual_commands (no hard fail)."""
    return _wrap(T.ensure_ffmpeg, dry_run, confirm_execute)


@mcp.tool()
def ensure_piper_model(
    model: str = "zh_CN-huayan-medium",
    model_dir: str = "",
    dry_run: bool = True,
    confirm_execute: bool = False,
) -> dict[str, Any]:
    """Download Piper voice model (dry_run by default)."""
    return _wrap(T.ensure_piper_model, model, model_dir, dry_run, confirm_execute)


@mcp.tool()
def configure_sandbox(
    projects_dir: str = "",
    dry_run: bool = True,
    confirm_execute: bool = False,
) -> dict[str, Any]:
    """Create projects sandbox dir and recommend env vars (dry_run by default)."""
    return _wrap(T.configure_sandbox, projects_dir, dry_run, confirm_execute)


@mcp.tool()
def verify_ready(deep: bool = False) -> dict[str, Any]:
    """Return whether Skill02 may start (can_produce_video_now)."""
    return _wrap(T.verify_ready, deep)


@mcp.tool()
def produce_init_project(
    project_id: str,
    title: str,
    pipeline_type: str = "animated-explainer",
) -> dict[str, Any]:
    """Create sandboxed project (requires OPENMONTAGE_P1_ALLOW_WRITES)."""
    return _wrap(T.produce_init_project, project_id, title, pipeline_type)


@mcp.tool()
def produce_set_production_profile(
    project_id: str,
    production_tier: str,
    visual_source: str = "",
    tts_source: str = "",
) -> dict[str, Any]:
    """Persist light/medium/heavy profile on project.json after the user picks a tier."""
    return _wrap(
        T.produce_set_production_profile,
        project_id,
        production_tier,
        visual_source,
        tts_source,
    )


@mcp.tool()
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
    """Write stage checkpoint under projects sandbox."""
    return _wrap(
        T.produce_write_checkpoint,
        project_id,
        stage,
        status,
        artifacts_json,
        pipeline_type,
        human_approval_required,
        human_approved,
        approval_note,
    )


@mcp.tool()
def produce_approve_checkpoint(
    project_id: str,
    stage: str,
    approval_text: str,
    artifacts_json: str = "{}",
    pipeline_type: str = "",
) -> dict[str, Any]:
    """Approve a gated stage using the user's exact approval text."""
    return _wrap(
        T.produce_approve_checkpoint,
        project_id,
        stage,
        approval_text,
        artifacts_json,
        pipeline_type,
    )


@mcp.tool()
def produce_read_state(project_id: str) -> dict[str, Any]:
    """Read project marker + checkpoints."""
    return _wrap(T.produce_read_state, project_id)


@mcp.tool()
def produce_get_next_stage(project_id: str) -> dict[str, Any]:
    """Suggest next pipeline stage."""
    return _wrap(T.produce_get_next_stage, project_id)


@mcp.tool()
def produce_tts_preflight() -> dict[str, Any]:
    """Check Piper readiness."""
    return _wrap(T.produce_tts_preflight)


@mcp.tool()
def produce_tts_sample(
    text: str,
    output_path: str = "",
    model: str = "",
    length_scale: float = 1.0,
) -> dict[str, Any]:
    """Generate Piper sample for human listen-check."""
    return _wrap(T.produce_tts_sample, text, output_path, model, length_scale)


@mcp.tool()
def produce_tts_generate(
    text: str,
    output_path: str,
    model: str = "",
    length_scale: float = 1.0,
    confirm_sample_ok: bool = False,
) -> dict[str, Any]:
    """Batch Piper TTS after sample approval (confirm_sample_ok required)."""
    return _wrap(
        T.produce_tts_generate,
        text,
        output_path,
        model,
        length_scale,
        confirm_sample_ok,
    )


@mcp.tool()
def produce_generate_subtitles(
    segments_json: str,
    output_path: str = "",
    fmt: str = "srt",
) -> dict[str, Any]:
    """Generate SRT/VTT subtitles from segments JSON."""
    return _wrap(T.produce_generate_subtitles, segments_json, output_path, fmt)


@mcp.tool()
def produce_compose_preflight(
    edit_decisions_json: str = "{}",
    asset_manifest_json: str = "{}",
) -> dict[str, Any]:
    """Dry-run compose dependencies."""
    return _wrap(T.produce_compose_preflight, edit_decisions_json, asset_manifest_json)


@mcp.tool()
def produce_compose_start(
    edit_decisions_json: str,
    asset_manifest_json: str,
    output_path: str = "",
    proposal_packet_json: str = "",
) -> dict[str, Any]:
    """Start Remotion/FFmpeg compose job; poll with produce_job_status."""
    return _wrap(
        T.produce_compose_start,
        edit_decisions_json,
        asset_manifest_json,
        output_path,
        proposal_packet_json,
    )


@mcp.tool()
def produce_read_asset_manifest(project_id: str) -> dict[str, Any]:
    """Read project artifacts/asset_manifest.json (for medium stock / heavy assets)."""
    return _wrap(T.produce_read_asset_manifest, project_id)


@mcp.tool()
def produce_append_asset_manifest_entry(project_id: str, entry_json: str) -> dict[str, Any]:
    """Upsert one asset_manifest entry by id (schema fields required)."""
    return _wrap(T.produce_append_asset_manifest_entry, project_id, entry_json)


@mcp.tool()
def produce_scan_copy_music(project_id: str) -> dict[str, Any]:
    """Scan assets/copy, assets/music, assets/subs for captions-music Skill."""
    return _wrap(T.produce_scan_copy_music, project_id)


@mcp.tool()
def produce_ensure_captions_music_dirs(project_id: str) -> dict[str, Any]:
    """Create assets/copy|music|subs|audio and artifacts if missing."""
    return _wrap(T.produce_ensure_captions_music_dirs, project_id)


@mcp.tool()
def produce_write_copy(
    project_id: str,
    content: str,
    filename: str = "script.txt",
    confirm: bool = False,
) -> dict[str, Any]:
    """Write approved script text into assets/copy/ (confirm=true required)."""
    return _wrap(T.produce_write_copy, project_id, content, filename, confirm)


@mcp.tool()
def produce_import_copy(
    project_id: str,
    source_path: str,
    filename: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    """Copy a user file under projects sandbox into assets/copy/ (confirm=true)."""
    return _wrap(T.produce_import_copy, project_id, source_path, filename, confirm)


@mcp.tool()
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
    """Split approved copy into cues, write assets/subs, register asset_manifest."""
    return _wrap(
        T.produce_segment_copy_to_subtitles,
        project_id,
        filename,
        chars_per_second,
        min_cue_seconds,
        max_cue_chars,
        fmt,
        scene_id,
        confirm_copy_ok,
    )


@mcp.tool()
def produce_import_music(
    project_id: str,
    source_path: str,
    filename: str = "",
    confirm: bool = False,
    asset_id: str = "music_bgm",
    scene_id: str = "scene_01",
    volume: float = 0.25,
) -> dict[str, Any]:
    """Copy BGM under projects sandbox into assets/music/ and register manifest."""
    return _wrap(
        T.produce_import_music,
        project_id,
        source_path,
        filename,
        confirm,
        asset_id,
        scene_id,
        volume,
    )


@mcp.tool()
def produce_register_music(
    project_id: str,
    filename: str = "",
    asset_id: str = "music_bgm",
    scene_id: str = "scene_01",
    volume: float = 0.25,
    confirm: bool = False,
) -> dict[str, Any]:
    """Register an existing assets/music file into asset_manifest."""
    return _wrap(
        T.produce_register_music,
        project_id,
        filename,
        asset_id,
        scene_id,
        volume,
        confirm,
    )


@mcp.tool()
def produce_build_compose_inputs(
    project_id: str,
    music_asset_id: str = "music_bgm",
    subtitle_asset_id: str = "subs_main",
    music_volume: float = 0.25,
    include_music: bool = True,
    include_subs: bool = True,
) -> dict[str, Any]:
    """Build edit_decisions_json + asset_manifest_json for produce_compose_*."""
    return _wrap(
        T.produce_build_compose_inputs,
        project_id,
        music_asset_id,
        subtitle_asset_id,
        music_volume,
        include_music,
        include_subs,
    )


@mcp.tool()
def produce_mix_narration_and_music(
    project_id: str,
    narration_path: str = "",
    music_filename: str = "",
    music_volume: float = 0.2,
    duck_db: float = 12.0,
    confirm: bool = False,
) -> dict[str, Any]:
    """Optional FFmpeg duck mix of narration + BGM into assets/audio/mixed.wav."""
    return _wrap(
        T.produce_mix_narration_and_music,
        project_id,
        narration_path,
        music_filename,
        music_volume,
        duck_db,
        confirm,
    )


@mcp.tool()
def produce_job_status(job_id: str) -> dict[str, Any]:
    """Poll background compose job."""
    return _wrap(T.produce_job_status, job_id)


@mcp.tool()
def produce_probe_media(path: str) -> dict[str, Any]:
    """ffprobe a file under the projects sandbox."""
    return _wrap(T.produce_probe_media, path)


@mcp.tool()
def error_capture_context(
    project_id: str,
    tool_name: str,
    stage: str,
    stderr: str,
    stdout: str = "",
    paths_json: str = "",
) -> dict[str, Any]:
    """Capture tool stderr into project artifacts/error_recovery.json; returns incident_id."""
    return _wrap(
        T.error_capture_context,
        project_id,
        tool_name,
        stage,
        stderr,
        stdout,
        paths_json,
    )


@mcp.tool()
def error_classify(project_id: str, incident_id: str) -> dict[str, Any]:
    """Match a stored incident to a known playbook (E01–E04 or E00_unknown)."""
    return _wrap(T.error_classify, project_id, incident_id)


@mcp.tool()
def error_plan_recovery(
    project_id: str,
    incident_id: str,
    playbook_id: str = "",
) -> dict[str, Any]:
    """Build recovery plan for an incident."""
    return _wrap(T.error_plan_recovery, project_id, incident_id, playbook_id)


@mcp.tool()
def error_apply_recovery(
    project_id: str,
    incident_id: str,
    confirm: bool = False,
    action_ids: str = "",
) -> dict[str, Any]:
    """Apply safe playbook actions (max 3 retries). High-risk needs confirm=true."""
    return _wrap(T.error_apply_recovery, project_id, incident_id, confirm, action_ids)


@mcp.tool()
def error_list_incidents(project_id: str) -> dict[str, Any]:
    """List stored error-recovery incidents for a project."""
    return _wrap(T.error_list_incidents, project_id)


@mcp.tool()
def probe_audio_loudness(path: str) -> dict[str, Any]:
    """Run ffmpeg volumedetect on a sandboxed audio file (E01 helper)."""
    return _wrap(T.probe_audio_loudness, path)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

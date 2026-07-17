"""OpenMontage doctor MCP server (stdio) — P0 diagnosis + P1 sandboxed project API."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from openmontage.mcp.common.envelope import fail, ok
from openmontage.mcp.doctor import tools as T

mcp = FastMCP(
    "openmontage-doctor",
    instructions=(
        "OpenMontage doctor: environment diagnosis, capability menu, "
        "sandboxed project state. Default Agent is read-only. "
        "Production Agent may set OPENMONTAGE_P1_ALLOW_WRITES=true for "
        "checkpoint/artifact writes under OPENMONTAGE_PROJECTS_DIR only. "
        "No media generation here — use openmontage-media."
    ),
)


def _wrap(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        data = fn(*args, **kwargs)
        warnings = []
        if isinstance(data, dict) and "_warnings" in data:
            warnings = list(data.pop("_warnings") or [])
        return ok(data, warnings=warnings)
    except Exception as exc:  # noqa: BLE001
        return fail(exc)


@mcp.tool()
def doctor(deep: bool = False) -> dict[str, Any]:
    """Probe local binaries, Remotion/Piper, and tool registry."""
    return _wrap(T.run_doctor, deep=deep)


@mcp.tool()
def provider_menu_summary() -> dict[str, Any]:
    """Compact capability menu from OpenMontage tool_registry (read-only)."""
    return _wrap(T.run_provider_menu_summary)


@mcp.tool()
def list_pipelines() -> dict[str, Any]:
    """List pipeline YAML files and local Skill Pack folders in the repo."""
    return _wrap(T.run_list_pipelines)


@mcp.tool()
def list_projects() -> dict[str, Any]:
    """List projects under OPENMONTAGE_PROJECTS_DIR (sandbox root)."""
    return _wrap(T.run_list_projects)


@mcp.tool()
def get_project_state(project_id: str) -> dict[str, Any]:
    """Read marker + checkpoints for a project inside the projects sandbox."""
    return _wrap(T.run_get_project_state, project_id)


@mcp.tool()
def get_next_stage(project_id: str) -> dict[str, Any]:
    """Return next pipeline stage and whether human approval is default."""
    return _wrap(T.run_get_next_stage, project_id)


@mcp.tool()
def validate_artifact(path: str, artifact_type: str | None = None) -> dict[str, Any]:
    """Validate a JSON artifact path under the projects sandbox against schemas."""
    return _wrap(T.run_validate_artifact, path, artifact_type)


@mcp.tool()
def validate_checkpoint(path: str) -> dict[str, Any]:
    """Validate a checkpoint JSON path under the projects sandbox."""
    return _wrap(T.run_validate_checkpoint, path)


@mcp.tool()
def estimate_cost(tool_name: str, inputs_json: str = "{}") -> dict[str, Any]:
    """Estimate cost/runtime for a registered BaseTool without executing it."""
    return _wrap(T.run_estimate_cost, tool_name, inputs_json)


@mcp.tool()
def read_artifact(path: str) -> dict[str, Any]:
    """Read a JSON/text artifact inside the projects sandbox."""
    return _wrap(T.run_read_artifact, path)


@mcp.tool()
def write_artifact(path: str, content_json: str) -> dict[str, Any]:
    """Write JSON artifact under sandbox (requires OPENMONTAGE_P1_ALLOW_WRITES)."""
    return _wrap(T.run_write_artifact, path, content_json)


@mcp.tool()
def write_checkpoint(
    project_id: str,
    stage: str,
    status: str,
    artifacts_json: str = "{}",
    pipeline_type: str = "",
    human_approval_required: bool = False,
    human_approved: bool = False,
    approval_note: str = "",
) -> dict[str, Any]:
    """Write a stage checkpoint under sandbox (requires P1 write flag)."""
    return _wrap(
        T.run_write_checkpoint,
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
def approve_checkpoint(
    project_id: str,
    stage: str,
    approval_text: str,
    artifacts_json: str = "{}",
    pipeline_type: str = "",
) -> dict[str, Any]:
    """Mark a gated stage completed using the user's approval text (required)."""
    return _wrap(
        T.run_approve_checkpoint,
        project_id,
        stage,
        approval_text,
        artifacts_json,
        pipeline_type,
    )


@mcp.tool()
def append_decision(project_id: str, decision_json: str) -> dict[str, Any]:
    """Append a decision_log entry (sandbox; requires P1 write flag)."""
    return _wrap(T.run_append_decision, project_id, decision_json)


@mcp.tool()
def init_project(project_id: str, title: str, pipeline_type: str) -> dict[str, Any]:
    """Create project layout under sandbox (requires OPENMONTAGE_P1_ALLOW_WRITES)."""
    return _wrap(T.run_init_project, project_id, title, pipeline_type)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

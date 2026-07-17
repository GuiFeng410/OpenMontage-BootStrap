"""OpenMontage doctor MCP server (stdio) — P0 read-only diagnosis."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from openmontage.mcp.common.envelope import fail, ok
from openmontage.mcp.doctor import tools as T

mcp = FastMCP(
    "openmontage-doctor",
    instructions=(
        "OpenMontage P0 doctor: environment diagnosis, capability menu, "
        "and sandboxed project state. No media generation. No default write access."
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
    """Probe local binaries, Remotion/Piper, and tool registry. Read-only."""
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
def init_project(project_id: str, title: str, pipeline_type: str) -> dict[str, Any]:
    """Disabled for default P0 Agent — always returns a policy error."""
    _ = (project_id, title, pipeline_type)
    return _wrap(T.run_init_project_denied)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

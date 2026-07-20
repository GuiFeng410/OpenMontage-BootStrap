"""OpenMontage providers-video MCP server (stdio) — C-常用 paid video gen."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from openmontage.mcp.common.envelope import fail, ok
from openmontage.mcp.providers_video import tools as T

mcp = FastMCP(
    "openmontage-providers-video",
    instructions=(
        "OpenMontage paid/cloud video providers (kling, seedance, sora, veo, "
        "minimax, runway). Always video_dry_run → present estimate → "
        "video_sample(confirm_estimate=true, short clip) → user review OK → "
        "video_generate(confirm=true, confirm_sample_ok=true). "
        "Never silently switch providers. API keys only from environment variables. "
        "Stock footage is out of scope."
    ),
)


def _wrap(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return ok(fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001
        return fail(exc)


@mcp.tool()
def list_video_providers() -> dict[str, Any]:
    """List cloud/paid video providers, key status, and availability."""
    return _wrap(T.list_video_providers)


@mcp.tool()
def video_dry_run(provider_or_tool: str, prompt: str, extras_json: str = "{}") -> dict[str, Any]:
    """Estimate cost/time for a video provider without generating."""
    return _wrap(T.video_dry_run, provider_or_tool, prompt, extras_json)


@mcp.tool()
def video_sample(
    provider_or_tool: str,
    prompt: str,
    output_path: str = "",
    extras_json: str = "{}",
    confirm_estimate: bool = False,
) -> dict[str, Any]:
    """Generate a short paid sample clip after estimate approval."""
    return _wrap(
        T.video_sample,
        provider_or_tool,
        prompt,
        output_path,
        extras_json,
        confirm_estimate,
    )


@mcp.tool()
def video_generate(
    provider_or_tool: str,
    prompt: str,
    output_path: str,
    extras_json: str = "{}",
    confirm: bool = False,
    confirm_sample_ok: bool = False,
) -> dict[str, Any]:
    """Paid video generation after sample approval (confirm + confirm_sample_ok)."""
    return _wrap(
        T.video_generate,
        provider_or_tool,
        prompt,
        output_path,
        extras_json,
        confirm,
        confirm_sample_ok,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

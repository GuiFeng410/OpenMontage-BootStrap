"""OpenMontage providers-image MCP server (stdio) — C-常用 paid image gen."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from openmontage.mcp.common.envelope import fail, ok
from openmontage.mcp.providers_image import tools as T

mcp = FastMCP(
    "openmontage-providers-image",
    instructions=(
        "OpenMontage paid/cloud image providers (flux, openai, dashscope, kling, "
        "google, grok). Always image_dry_run → present estimate → "
        "image_sample(confirm_estimate=true) → user review OK → "
        "image_generate(confirm=true, confirm_sample_ok=true). "
        "Never silently switch providers. API keys only from environment variables. "
        "Stock media is out of scope."
    ),
)


def _wrap(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return ok(fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001
        return fail(exc)


@mcp.tool()
def list_image_providers() -> dict[str, Any]:
    """List cloud/paid image providers, key status, and availability."""
    return _wrap(T.list_image_providers)


@mcp.tool()
def image_dry_run(provider_or_tool: str, prompt: str, extras_json: str = "{}") -> dict[str, Any]:
    """Estimate cost/time for an image provider without generating."""
    return _wrap(T.image_dry_run, provider_or_tool, prompt, extras_json)


@mcp.tool()
def image_sample(
    provider_or_tool: str,
    prompt: str,
    output_path: str = "",
    extras_json: str = "{}",
    confirm_estimate: bool = False,
) -> dict[str, Any]:
    """Generate one paid sample image after estimate approval."""
    return _wrap(
        T.image_sample,
        provider_or_tool,
        prompt,
        output_path,
        extras_json,
        confirm_estimate,
    )


@mcp.tool()
def image_generate(
    provider_or_tool: str,
    prompt: str,
    output_path: str,
    extras_json: str = "{}",
    confirm: bool = False,
    confirm_sample_ok: bool = False,
) -> dict[str, Any]:
    """Paid image generation after sample approval (confirm + confirm_sample_ok)."""
    return _wrap(
        T.image_generate,
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

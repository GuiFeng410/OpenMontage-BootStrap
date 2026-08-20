"""OpenMontage providers-tts MCP server (stdio) — P2 advanced/paid TTS."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from openmontage.mcp.common.envelope import fail, ok
from openmontage.mcp.providers_tts import tools as T

mcp = FastMCP(
    "openmontage-providers-tts",
    instructions=(
        "OpenMontage P2 advanced TTS providers (OpenAI, ElevenLabs, DashScope, "
        "Doubao, Google, Kling). Always tts_dry_run → present estimate → "
        "tts_sample(confirm_estimate=true) → user listen OK → "
        "tts_generate(confirm=true, confirm_sample_ok=true). "
        "Never silently switch providers. Piper/zero-key stays on openmontage-media. "
        "API keys only from environment variables."
    ),
)


def _wrap(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return ok(fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001
        return fail(exc)


@mcp.tool()
def list_tts_providers() -> dict[str, Any]:
    """List cloud/paid TTS providers, key status, and availability."""
    return _wrap(T.list_tts_providers)


@mcp.tool()
def tts_dry_run(provider_or_tool: str, text: str, extras_json: str = "{}") -> dict[str, Any]:
    """Estimate cost/time for a provider without generating audio."""
    return _wrap(T.tts_dry_run, provider_or_tool, text, extras_json)


@mcp.tool()
def tts_sample(
    provider_or_tool: str,
    text: str,
    output_path: str = "",
    extras_json: str = "{}",
    confirm_estimate: bool = False,
) -> dict[str, Any]:
    """Generate a short paid TTS sample after estimate approval."""
    return _wrap(
        T.tts_sample,
        provider_or_tool,
        text,
        output_path,
        extras_json,
        confirm_estimate,
    )


@mcp.tool()
def tts_generate(
    provider_or_tool: str,
    text: str,
    output_path: str,
    extras_json: str = "{}",
    confirm: bool = False,
    confirm_sample_ok: bool = False,
) -> dict[str, Any]:
    """Batch paid TTS after sample approval (confirm + confirm_sample_ok required)."""
    return _wrap(
        T.tts_generate,
        provider_or_tool,
        text,
        output_path,
        extras_json,
        confirm,
        confirm_sample_ok,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

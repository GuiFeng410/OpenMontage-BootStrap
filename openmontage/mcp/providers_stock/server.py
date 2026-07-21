"""OpenMontage providers-stock MCP server (stdio) — free Pexels/Pixabay stock."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from openmontage.mcp.common.envelope import fail, ok
from openmontage.mcp.providers_stock import tools as T

mcp = FastMCP(
    "openmontage-providers-stock",
    instructions=(
        "OpenMontage free stock media (Pexels, Pixabay). "
        "Always list_stock_sources → stock_search → present candidates → "
        "stock_download(confirm=true). Cost is always $0. "
        "API keys from environment only. Optional BootStrap add-on — "
        "not part of the default four-MCP install."
    ),
)


def _wrap(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return ok(fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001
        return fail(exc)


@mcp.tool()
def list_stock_sources() -> dict[str, Any]:
    """List free stock sources (Pexels/Pixabay), key status, and availability."""
    return _wrap(T.list_stock_sources)


@mcp.tool()
def stock_search(
    source: str,
    media_kind: str,
    query: str,
    extras_json: str = "{}",
) -> dict[str, Any]:
    """Search stock candidates without downloading files."""
    return _wrap(T.stock_search, source, media_kind, query, extras_json)


@mcp.tool()
def stock_download(
    source: str,
    media_kind: str,
    query: str,
    output_path: str = "",
    extras_json: str = "{}",
    confirm: bool = False,
) -> dict[str, Any]:
    """Download stock media after user approval (confirm=true required)."""
    return _wrap(
        T.stock_download,
        source,
        media_kind,
        query,
        output_path,
        extras_json,
        confirm,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

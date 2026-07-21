"""Gate tests for providers-stock (no live API calls)."""

from __future__ import annotations

import pytest

from openmontage.mcp.common.errors import ConfigError, DoctorError
from openmontage.mcp.providers_stock.tools import (
    list_stock_sources,
    stock_download,
    stock_search,
)


def test_list_stock_sources_shape() -> None:
    data = list_stock_sources()
    pairs = {(r["source"], r["media_kind"]) for r in data["sources"]}
    assert ("pexels", "image") in pairs
    assert ("pexels", "video") in pairs
    assert ("pixabay", "image") in pairs
    assert ("pixabay", "video") in pairs


def test_allowed_stock_sources_filter(monkeypatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_ALLOWED_STOCK_SOURCES", "pexels")
    data = list_stock_sources()
    assert {r["source"] for r in data["sources"]} == {"pexels"}


def test_download_requires_confirm(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("PEXELS_API_KEY", "dummy")
    with pytest.raises(ConfigError, match="confirm=true"):
        stock_download("pexels", "image", "ocean", confirm=False)


def test_search_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="API key"):
        stock_search("pexels", "image", "ocean")


def test_unknown_source() -> None:
    with pytest.raises(DoctorError, match="Unknown"):
        stock_search("unsplash", "image", "ocean")


def test_bad_media_kind(monkeypatch) -> None:
    monkeypatch.setenv("PEXELS_API_KEY", "dummy")
    with pytest.raises(DoctorError, match="media_kind"):
        stock_search("pexels", "audio", "ocean")


def test_mcp_server_name() -> None:
    from openmontage.mcp.providers_stock.server import mcp

    assert mcp.name == "openmontage-providers-stock"

"""Gate tests for providers-image / providers-video (no live API calls)."""

from __future__ import annotations

import pytest

from openmontage.mcp.common.errors import ConfigError, DoctorError
from openmontage.mcp.providers_image.tools import (
    image_dry_run,
    image_generate,
    image_sample,
    list_image_providers,
)
from openmontage.mcp.providers_video.tools import (
    list_video_providers,
    video_dry_run,
    video_generate,
    video_sample,
)


def test_list_image_providers_shape() -> None:
    data = list_image_providers()
    names = {p["provider"] for p in data["providers"]}
    assert names == {"dashscope", "flux", "google", "grok", "kling", "openai"}


def test_list_video_providers_shape() -> None:
    data = list_video_providers()
    names = {p["provider"] for p in data["providers"]}
    assert names == {"kling", "minimax", "runway", "seedance", "sora", "veo"}
    tools = {p["provider"]: p["tool_name"] for p in data["providers"]}
    assert tools["kling"] == "kling_official_video"
    assert tools["seedance"] == "seedance_video"


def test_image_allowed_providers_filter(monkeypatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_ALLOWED_PROVIDERS", "flux,openai")
    data = list_image_providers()
    assert {p["provider"] for p in data["providers"]} == {"flux", "openai"}


def test_video_allowed_providers_filter(monkeypatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_ALLOWED_PROVIDERS", "kling")
    data = list_video_providers()
    assert {p["provider"] for p in data["providers"]} == {"kling"}


def test_image_sample_requires_confirm(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    with pytest.raises(ConfigError, match="confirm_estimate"):
        image_sample("flux", "a cat", confirm_estimate=False)


def test_image_generate_requires_confirms(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    out = str(tmp_path / "a.png")
    with pytest.raises(ConfigError, match="confirm=true"):
        image_generate("flux", "a cat", out, confirm=False, confirm_sample_ok=True)
    with pytest.raises(ConfigError, match="confirm_sample_ok"):
        image_generate("flux", "a cat", out, confirm=True, confirm_sample_ok=False)


def test_video_sample_requires_confirm(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    with pytest.raises(ConfigError, match="confirm_estimate"):
        video_sample("seedance", "a wave", confirm_estimate=False)


def test_video_generate_requires_confirms(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    out = str(tmp_path / "a.mp4")
    with pytest.raises(ConfigError, match="confirm=true"):
        video_generate("runway", "a wave", out, confirm=False, confirm_sample_ok=True)
    with pytest.raises(ConfigError, match="confirm_sample_ok"):
        video_generate("runway", "a wave", out, confirm=True, confirm_sample_ok=False)


def test_unknown_image_provider() -> None:
    with pytest.raises(DoctorError, match="Unknown"):
        image_dry_run("not-a-provider", "hello")


def test_unknown_video_provider() -> None:
    with pytest.raises(DoctorError, match="Unknown"):
        video_dry_run("kling_video", "hello")


def test_image_dry_run_flux_without_key(monkeypatch) -> None:
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("FAL_AI_API_KEY", raising=False)
    data = image_dry_run("flux", "a red bicycle on a quiet street")
    assert data["provider"] == "flux"
    assert data["tool_name"] == "flux_image"
    assert "estimated_cost_usd" in data


def test_video_dry_run_seedance_without_key(monkeypatch) -> None:
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("FAL_AI_API_KEY", raising=False)
    data = video_dry_run("seedance", "cinematic ocean waves at dusk")
    assert data["provider"] == "seedance"
    assert data["tool_name"] == "seedance_video"
    assert "estimated_cost_usd" in data


def test_mcp_server_names() -> None:
    from openmontage.mcp.providers_image.server import mcp as image_mcp
    from openmontage.mcp.providers_video.server import mcp as video_mcp

    assert image_mcp.name == "openmontage-providers-image"
    assert video_mcp.name == "openmontage-providers-video"

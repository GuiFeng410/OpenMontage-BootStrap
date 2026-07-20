"""P2 providers-tts gate tests (no live API calls)."""

from __future__ import annotations

import pytest

from openmontage.mcp.common.errors import ConfigError, DoctorError
from openmontage.mcp.providers_tts.tools import (
    list_tts_providers,
    tts_dry_run,
    tts_generate,
    tts_sample,
)


def test_list_tts_providers_shape() -> None:
    data = list_tts_providers()
    assert "providers" in data
    names = {p["provider"] for p in data["providers"]}
    assert "openai" in names
    assert "elevenlabs" in names


def test_allowed_providers_filter(monkeypatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_ALLOWED_PROVIDERS", "openai")
    data = list_tts_providers()
    names = {p["provider"] for p in data["providers"]}
    assert names == {"openai"}


def test_sample_requires_confirm_estimate(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    with pytest.raises(ConfigError, match="confirm_estimate"):
        tts_sample("openai", "你好", confirm_estimate=False)


def test_generate_requires_confirms(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    with pytest.raises(ConfigError, match="confirm=true"):
        tts_generate("openai", "你好", str(tmp_path / "a.wav"), confirm=False, confirm_sample_ok=True)
    with pytest.raises(ConfigError, match="confirm_sample_ok"):
        tts_generate("openai", "你好", str(tmp_path / "a.wav"), confirm=True, confirm_sample_ok=False)


def test_unknown_provider() -> None:
    with pytest.raises(DoctorError, match="Unknown"):
        tts_dry_run("not-a-provider", "hello")


def test_dry_run_openai_without_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # dry_run should still return a structure even if unavailable
    data = tts_dry_run("openai", "hello world sample")
    assert data["provider"] == "openai"
    assert data["tool_name"] == "openai_tts"
    assert "estimated_cost_usd" in data

"""Unit tests for OpenAI-compatible vision env resolution."""

from __future__ import annotations

from tools.analysis.openai_compat_vision import resolve_vision_env


def test_resolve_vision_env_prefers_vision_api_key(monkeypatch):
    monkeypatch.setenv("VISION_API_KEY", "vk")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dk")
    monkeypatch.setenv("VISION_BASE_URL", "https://example.com/v1/")
    monkeypatch.setenv("VISION_MODEL", "gpt-4o-mini")
    cfg = resolve_vision_env()
    assert cfg["available"] is True
    assert cfg["api_key"] == "vk"
    assert cfg["key_source"] == "VISION_API_KEY"
    assert cfg["base_url"] == "https://example.com/v1"
    assert cfg["model"] == "gpt-4o-mini"


def test_resolve_vision_env_falls_back_to_dashscope(monkeypatch):
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dk")
    monkeypatch.delenv("VISION_BASE_URL", raising=False)
    monkeypatch.delenv("VISION_MODEL", raising=False)
    cfg = resolve_vision_env()
    assert cfg["available"] is True
    assert cfg["api_key"] == "dk"
    assert cfg["key_source"] == "DASHSCOPE_API_KEY"
    assert "dashscope" in cfg["base_url"]
    assert cfg["model"] == "qwen-vl-max"

"""Tests for Agnes public-URL product image understanding."""

from __future__ import annotations

from unittest.mock import MagicMock

from tools.analysis.agnes_vision import AgnesVision
from tools.base_tool import ToolStatus


def test_agnes_vision_builds_25_flash_payload_for_public_urls(monkeypatch):
    monkeypatch.setenv("AGNES_VISION_MODEL", "agnes-2.5-flash")

    payload = AgnesVision().build_payload(
        {"image_urls": ["https://images.example.com/bracelet.jpg"]}
    )

    assert payload["model"] == "agnes-2.5-flash"
    content = payload["messages"][1]["content"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == "https://images.example.com/bracelet.jpg"


def test_agnes_vision_rejects_non_public_urls():
    try:
        AgnesVision().build_payload({"image_urls": ["file:///private/bracelet.jpg"]})
    except ValueError as exc:
        assert "https" in str(exc)
    else:
        raise AssertionError("Expected a non-public image URL to be rejected")


def test_agnes_vision_executes_and_parses_structured_result(monkeypatch):
    monkeypatch.setenv("AGNES_API_KEY", "test-agnes-key")
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": (
                    '{"images":[{"url":"https://images.example.com/bracelet.jpg",'
                    '"suggested_class":"product_hero","description_zh":"银色手链",'
                    '"confidence":0.9,"risks_zh":[]}]}'
                )
            }
        }]
    }
    requests = MagicMock()
    requests.post.return_value = response
    monkeypatch.setitem(__import__("sys").modules, "requests", requests)

    result = AgnesVision().execute(
        {"image_urls": ["https://images.example.com/bracelet.jpg"]}
    )

    assert result.success, result.error
    assert result.data["images"][0]["suggested_class"] == "product_hero"
    assert requests.post.call_args.kwargs["json"]["model"] == "agnes-2.5-flash"


def test_agnes_vision_requires_agnes_key(monkeypatch):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_AI_API_KEY", raising=False)
    assert AgnesVision().get_status() == ToolStatus.UNAVAILABLE

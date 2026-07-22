"""Agnes image tool payload and status coverage."""

from __future__ import annotations

from unittest.mock import MagicMock

from tools.base_tool import ToolStatus
from tools.graphics.agnes_image import AgnesImage


def test_agnes_image_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_AI_API_KEY", raising=False)
    assert AgnesImage().get_status() == ToolStatus.UNAVAILABLE


def test_agnes_image_available_with_alias_key(monkeypatch):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.setenv("AGNES_AI_API_KEY", "test-agnes-key")
    assert AgnesImage().get_status() == ToolStatus.AVAILABLE


def test_agnes_image_default_payload_uses_21_flash():
    payload = AgnesImage().build_payload({"prompt": "a red apple on a table"})
    assert payload["model"] == "agnes-image-2.1-flash"
    assert payload["size"] == "1K"
    assert payload["ratio"] == "16:9"
    assert payload["extra_body"]["response_format"] == "url"
    assert "response_format" not in payload
    assert "image" not in payload.get("extra_body", {})


def test_agnes_image_can_switch_to_20_flash():
    payload = AgnesImage().build_payload(
        {"prompt": "a blue cube", "model": "agnes-image-2.0-flash"}
    )
    assert payload["model"] == "agnes-image-2.0-flash"


def test_agnes_image_i2i_puts_images_in_extra_body():
    payload = AgnesImage().build_payload(
        {
            "prompt": "make it rainy",
            "operation": "image_to_image",
            "image_url": "https://example.com/in.png",
        }
    )
    assert payload["extra_body"]["image"] == ["https://example.com/in.png"]
    assert payload["extra_body"]["response_format"] == "url"


def test_agnes_image_execute_downloads_url(monkeypatch, tmp_path):
    monkeypatch.setenv("AGNES_API_KEY", "test-agnes-key")
    tool = AgnesImage()
    output = tmp_path / "out.png"

    create_resp = MagicMock()
    create_resp.raise_for_status = MagicMock()
    create_resp.json.return_value = {
        "data": [{"url": "https://cdn.example.com/gen.png", "b64_json": None}]
    }
    download_resp = MagicMock()
    download_resp.raise_for_status = MagicMock()
    download_resp.content = b"png-bytes"

    fake_requests = MagicMock()
    fake_requests.post.return_value = create_resp
    fake_requests.get.return_value = download_resp
    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)

    # execute imports requests inside the method — patch the module after import path
    import tools.graphics.agnes_image as mod

    monkeypatch.setattr(mod, "time", __import__("time"))
    # Patch requests where execute will import it: use builtins via injecting into
    # the function's import by patching requests in sys.modules before execute.
    result = tool.execute({"prompt": "test", "output_path": str(output)})
    assert result.success, result.error
    assert output.read_bytes() == b"png-bytes"
    assert result.data["provider"] == "agnes"
    assert result.data["model"] == "agnes-image-2.1-flash"
    assert result.cost_usd == 0.003

    post_kwargs = fake_requests.post.call_args.kwargs
    body = post_kwargs["json"]
    assert body["extra_body"]["response_format"] == "url"
    assert "response_format" not in body


def test_agnes_image_is_discovered():
    from tools.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry.discover()
    tool = registry.get("agnes_image")
    assert tool is not None
    assert tool.provider == "agnes"
    assert tool.capability == "image_generation"

"""Agnes video tool payload, frame mapping, and async poll coverage."""

from __future__ import annotations

from unittest.mock import MagicMock

from tools.base_tool import ToolStatus
from tools.video.agnes_video import (
    AgnesVideo,
    duration_to_num_frames,
    validate_num_frames,
)


def test_duration_to_num_frames_follows_8n_plus_1():
    frames = duration_to_num_frames(5, 24)
    assert frames == 121
    assert (frames - 1) % 8 == 0
    assert frames <= 441


def test_validate_num_frames_rejects_bad_values():
    assert validate_num_frames(121) == 121
    try:
        validate_num_frames(120)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_agnes_video_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_AI_API_KEY", raising=False)
    assert AgnesVideo().get_status() == ToolStatus.UNAVAILABLE


def test_agnes_video_default_payload():
    payload = AgnesVideo().build_payload({"prompt": "a cat on the beach"})
    assert payload["model"] == "agnes-video-v2.0"
    assert payload["num_frames"] == 121
    assert payload["frame_rate"] == 24
    assert payload["width"] == 1152
    assert payload["height"] == 768
    assert "image" not in payload


def test_agnes_video_duration_maps_to_frames():
    payload = AgnesVideo().build_payload({"prompt": "x", "duration": 3})
    frames = payload["num_frames"]
    assert (frames - 1) % 8 == 0
    assert 65 <= frames <= 81  # ~3s at 24fps, snapped to 8n+1
    payload5 = AgnesVideo().build_payload({"prompt": "x", "duration": 5})
    assert payload5["num_frames"] == 121


def test_agnes_video_i2v_requires_image():
    try:
        AgnesVideo().build_payload({"prompt": "x", "operation": "image_to_video"})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass

    payload = AgnesVideo().build_payload(
        {
            "prompt": "animate",
            "operation": "image_to_video",
            "image_url": "https://example.com/frame.png",
        }
    )
    assert payload["image"] == "https://example.com/frame.png"


def test_agnes_video_estimate_uses_standard_rate():
    cost = AgnesVideo().estimate_cost({"duration": 5})
    assert abs(cost - 0.025) < 1e-9


def test_agnes_video_execute_create_poll_download(monkeypatch, tmp_path):
    monkeypatch.setenv("AGNES_API_KEY", "test-agnes-key")
    tool = AgnesVideo()
    output = tmp_path / "out.mp4"

    create_resp = MagicMock()
    create_resp.raise_for_status = MagicMock()
    create_resp.json.return_value = {
        "id": "task_1",
        "task_id": "task_1",
        "video_id": "video_1",
        "status": "queued",
    }
    poll_resp = MagicMock()
    poll_resp.raise_for_status = MagicMock()
    poll_resp.json.return_value = {
        "status": "completed",
        "video_id": "video_1",
        "task_id": "task_1",
        "seconds": "5.0",
        "size": "1152x768",
        "metadata": {"url": "https://cdn.example.com/out.mp4"},
    }
    download_resp = MagicMock()
    download_resp.raise_for_status = MagicMock()
    download_resp.content = b"mp4-bytes"

    fake_requests = MagicMock()
    fake_requests.post.return_value = create_resp
    fake_requests.get.side_effect = [poll_resp, download_resp]
    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)
    monkeypatch.setattr(
        "tools.video._shared.probe_output",
        lambda path: {"duration_seconds": 5.0, "width": 1152, "height": 768},
    )

    result = tool.execute(
        {
            "prompt": "cinematic waves",
            "output_path": str(output),
            "poll_interval_seconds": 0,
        }
    )
    assert result.success, result.error
    assert output.read_bytes() == b"mp4-bytes"
    assert result.data["provider"] == "agnes"
    assert result.data["video_id"] == "video_1"

    post_url = fake_requests.post.call_args.args[0]
    assert post_url.endswith("/v1/videos")
    get_url = fake_requests.get.call_args_list[0].args[0]
    assert "agnesapi" in get_url


def test_agnes_video_is_discovered():
    from tools.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry.discover()
    tool = registry.get("agnes_video")
    assert tool is not None
    assert tool.provider == "agnes"
    assert tool.capability == "video_generation"

"""TokenHub Pixverse T2V/I2V coverage (no live network)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tools._tokenhub.client import TokenHubClient, TokenHubError
from tools._tokenhub.models import configured_video_models, get_model
from tools._tokenhub.pixverse import (
    PIXVERSE_DEFAULT_MODEL,
    generate_pixverse_video,
    is_pixverse_model,
    submit_image_to_video,
    submit_text_to_video,
)
from tools._tokenhub.video import generate_video, submit_video_job


def test_pixverse_in_configured_catalog():
    assert PIXVERSE_DEFAULT_MODEL in configured_video_models()
    assert get_model(PIXVERSE_DEFAULT_MODEL).status == "configured"
    assert is_pixverse_model("pixverse-video-v6.0")
    assert is_pixverse_model("PIXVERSE-VIDEO-V6.0")
    assert not is_pixverse_model("hy-video-1.5")


def test_submit_video_job_rejects_pixverse_model(monkeypatch):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    with pytest.raises(TokenHubError, match="Pixverse"):
        submit_video_job(
            "x",
            model=PIXVERSE_DEFAULT_MODEL,
            client=TokenHubClient(api_key="test-key"),
        )


def test_submit_text_to_video_payload(monkeypatch):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    client = TokenHubClient(api_key="test-key", base_url="https://tokenhub.test/v1")
    seen: list[tuple[str, dict]] = []

    def fake_post(path: str, payload: dict, **_kwargs):
        seen.append((path, payload))
        return {"task_id": "pv-1", "status": "submitted"}

    client.post = fake_post  # type: ignore[method-assign]
    out = submit_text_to_video(
        "一只橙色小猫",
        duration=5,
        quality="720p",
        aspect_ratio="16:9",
        client=client,
    )
    assert out["task_id"] == "pv-1"
    assert seen[0][0] == "/wand/pixverse/text-to-video"
    assert seen[0][1]["model"] == PIXVERSE_DEFAULT_MODEL
    assert seen[0][1]["duration"] == 5
    assert seen[0][1]["aspect_ratio"] == "16:9"


def test_submit_image_to_video_requires_http_url(monkeypatch):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    client = TokenHubClient(api_key="test-key")
    with pytest.raises(TokenHubError, match="http\\(s\\) URL"):
        submit_image_to_video("turn", image_url="D:/local.jpg", client=client)


def test_submit_image_to_video_payload(monkeypatch):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    client = TokenHubClient(api_key="test-key", base_url="https://tokenhub.test/v1")
    seen: list[tuple[str, dict]] = []

    def fake_post(path: str, payload: dict, **_kwargs):
        seen.append((path, payload))
        return {"id": "pv-2", "status": "queued"}

    client.post = fake_post  # type: ignore[method-assign]
    submit_image_to_video(
        "自然转头",
        image_url="https://cdn.example.com/in.jpg",
        duration=5,
        quality="720p",
        client=client,
    )
    assert seen[0][0] == "/wand/pixverse/image-to-video"
    assert seen[0][1]["img_id"] == "https://cdn.example.com/in.jpg"


def test_generate_pixverse_t2v_poll_download(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    out = tmp_path / "clip.mp4"
    client = TokenHubClient(api_key="test-key", base_url="https://tokenhub.test/v1")
    posts: list[str] = []
    gets: list[str] = []

    def fake_post(path: str, payload: dict, **_kwargs):
        posts.append(path)
        return {"task_id": "pv-t2v", "status": "submitted"}

    def fake_get(path: str, **_kwargs):
        gets.append(path)
        return {
            "task_id": "pv-t2v",
            "status": "completed",
            "data": {"url": "https://cdn.example.com/pix.mp4"},
        }

    client.post = fake_post  # type: ignore[method-assign]
    client.get = fake_get  # type: ignore[method-assign]

    downloaded = MagicMock(return_value=out)
    out.write_bytes(b"0" * 12000)
    monkeypatch.setattr("tools._tokenhub.pixverse.download_video", downloaded)
    monkeypatch.setattr("tools._tokenhub.pixverse.time.sleep", lambda *_: None)

    result = generate_pixverse_video(
        "小猫看镜头",
        mode="t2v",
        output_path=out,
        client=client,
        poll_interval_seconds=0.01,
    )
    assert result["job_id"] == "pv-t2v"
    assert result["video_url"] == "https://cdn.example.com/pix.mp4"
    assert result["output_path"] == str(out)
    assert posts == ["/wand/pixverse/text-to-video"]
    assert gets == ["/wand/pixverse/tasks/pv-t2v"]
    downloaded.assert_called_once()


def test_generate_video_routes_pixverse(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    out = tmp_path / "r.mp4"
    client = TokenHubClient(api_key="test-key", base_url="https://tokenhub.test/v1")

    def fake_post(path: str, payload: dict, **_kwargs):
        assert path == "/wand/pixverse/image-to-video"
        assert payload["img_id"].startswith("https://")
        return {"task_id": "pv-route", "status": "submitted"}

    def fake_get(path: str, **_kwargs):
        return {
            "status": "completed",
            "data": {"video_url": "https://cdn.example.com/routed.mp4"},
        }

    client.post = fake_post  # type: ignore[method-assign]
    client.get = fake_get  # type: ignore[method-assign]
    monkeypatch.setattr("tools._tokenhub.pixverse.time.sleep", lambda *_: None)
    monkeypatch.setattr(
        "tools._tokenhub.pixverse.download_video",
        MagicMock(return_value=out),
    )
    out.write_bytes(b"0" * 12000)

    result = generate_video(
        "转头",
        model=PIXVERSE_DEFAULT_MODEL,
        image_url="https://cdn.example.com/ref.jpg",
        duration=5,
        quality="720p",
        output_path=out,
        client=client,
        poll_interval_seconds=0.01,
    )
    assert result["job_id"] == "pv-route"
    assert result["model"] == PIXVERSE_DEFAULT_MODEL
    assert "routed.mp4" in result["video_url"]


def test_generate_pixverse_rejects_local_path_only(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    img = tmp_path / "a.jpg"
    img.write_bytes(b"jpeg")
    with pytest.raises(TokenHubError, match="local image_path"):
        generate_pixverse_video(
            "x",
            mode="i2v",
            image_path=str(img),
            client=TokenHubClient(api_key="test-key"),
        )

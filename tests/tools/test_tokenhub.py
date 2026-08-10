"""TokenHub client/catalog/I2V payload coverage (no live network)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tools._tokenhub.client import (
    DEFAULT_BASE_URL,
    TokenHubClient,
    TokenHubError,
    get_tokenhub_api_key,
    get_tokenhub_base_url,
)
from tools._tokenhub.models import (
    DEFAULT_VIDEO_MODEL,
    configured_video_models,
    get_model,
    list_models,
    planned_video_models,
)
from tools._tokenhub.video import (
    _image_payload,
    generate_video,
    submit_video_job,
)


def test_get_tokenhub_api_key_reads_primary_and_alias(monkeypatch):
    monkeypatch.delenv("TOKENHUB_API_KEY", raising=False)
    monkeypatch.delenv("TENCENT_TOKENHUB_API_KEY", raising=False)
    assert get_tokenhub_api_key() is None

    monkeypatch.setenv("TOKENHUB_API_KEY", " primary-key ")
    assert get_tokenhub_api_key() == "primary-key"

    monkeypatch.delenv("TOKENHUB_API_KEY", raising=False)
    monkeypatch.setenv("TENCENT_TOKENHUB_API_KEY", "alias-key")
    assert get_tokenhub_api_key() == "alias-key"


def test_get_tokenhub_base_url_default_and_override(monkeypatch):
    monkeypatch.delenv("TOKENHUB_BASE_URL", raising=False)
    assert get_tokenhub_base_url() == DEFAULT_BASE_URL

    monkeypatch.setenv("TOKENHUB_BASE_URL", "https://example.test/v1/")
    assert get_tokenhub_base_url() == "https://example.test/v1"


def test_model_catalog_hy_configured_yt_planned():
    assert DEFAULT_VIDEO_MODEL == "hy-video-1.5"
    assert "hy-video-1.5" in configured_video_models()
    assert "pixverse-video-v6.0" in configured_video_models()
    planned = planned_video_models()
    assert "yt-video-2.0" in planned
    assert get_model("hy-video-1.5").status == "configured"
    assert get_model("pixverse-video-v6.0").status == "configured"
    assert all(m.capability == "video" for m in list_models())


def test_image_payload_local_uses_base64(tmp_path: Path):
    img = tmp_path / "frame.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    payload = _image_payload(image_path=str(img))
    assert payload is not None
    assert "base64" in payload
    assert "url" not in payload
    assert payload["base64"]


def test_image_payload_rejects_data_uri_as_url():
    with pytest.raises(TokenHubError, match="http\\(s\\) URL"):
        _image_payload(image_url="data:image/png;base64,AAAA")


def test_image_payload_http_url():
    payload = _image_payload(image_url="https://cdn.example.com/a.png")
    assert payload == {"url": "https://cdn.example.com/a.png"}


def test_client_headers_require_key(monkeypatch):
    monkeypatch.delenv("TOKENHUB_API_KEY", raising=False)
    monkeypatch.delenv("TENCENT_TOKENHUB_API_KEY", raising=False)
    client = TokenHubClient(api_key=None)
    with pytest.raises(TokenHubError, match="TOKENHUB_API_KEY"):
        client._headers()


def test_submit_planned_model_raises(monkeypatch):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    with pytest.raises(Exception, match="planned"):
        submit_video_job("x", model="yt-video-2.0", client=TokenHubClient(api_key="test-key"))


def test_generate_video_submit_poll_download(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    out = tmp_path / "clip.mp4"

    client = TokenHubClient(api_key="test-key", base_url="https://tokenhub.test/v1")
    calls: list[tuple[str, dict]] = []

    def fake_post(path: str, payload: dict, **_kwargs):
        calls.append((path, payload))
        if path.endswith("/submit"):
            assert payload["model"] == "hy-video-1.5"
            assert "image" in payload
            assert "base64" in payload["image"]
            return {"id": "job-1", "status": "submitted"}
        if path.endswith("/query"):
            return {
                "id": "job-1",
                "status": "completed",
                "data": {"url": "https://cdn.example.com/out.mp4"},
            }
        raise AssertionError(path)

    client.post = fake_post  # type: ignore[method-assign]

    img = tmp_path / "ref.jpg"
    img.write_bytes(b"jpeg-bytes")

    downloaded = MagicMock(return_value=out)
    out.write_bytes(b"0" * 12000)

    monkeypatch.setattr("tools._tokenhub.video.download_video", downloaded)
    monkeypatch.setattr("tools._tokenhub.video.time.sleep", lambda *_: None)

    result = generate_video(
        "gentle product turn",
        image_path=str(img),
        output_path=out,
        client=client,
        poll_interval_seconds=0.01,
    )
    assert result["job_id"] == "job-1"
    assert result["video_url"] == "https://cdn.example.com/out.mp4"
    assert result["output_path"] == str(out)
    assert any(p.endswith("/submit") for p, _ in calls)
    downloaded.assert_called_once()

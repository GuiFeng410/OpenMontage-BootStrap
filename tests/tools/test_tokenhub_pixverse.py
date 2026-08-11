"""TokenHub Pixverse T2V/I2V coverage (no live network)."""

from __future__ import annotations

import traceback
from datetime import datetime, timezone
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
        return {
            "ErrCode": 0,
            "ErrMsg": "success",
            "Resp": {"video_id": "pv-1"},
        }

    client.post = fake_post  # type: ignore[method-assign]
    out = submit_text_to_video(
        "一只橙色小猫",
        duration=5,
        quality="720p",
        aspect_ratio="16:9",
        client=client,
    )
    assert out["Resp"]["video_id"] == "pv-1"
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
        return {
            "ErrCode": 0,
            "ErrMsg": "success",
            "Resp": {"video_id": "pv-t2v"},
        }

    def fake_get(path: str, **_kwargs):
        gets.append(path)
        return {
            "ErrCode": 0,
            "ErrMsg": "success",
            "Resp": {
                "status": "completed",
                "url": "https://cdn.example.com/pix.mp4",
            },
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


def test_normalize_media_url_unquotes_path():
    from tools._tokenhub.pixverse import _normalize_media_url

    raw = "https://media.pixverseai.cn/pixverse%2Fmp4%2Fmedia%2Fweb%2Fori%2Fa.mp4"
    assert _normalize_media_url(raw) == (
        "https://media.pixverseai.cn/pixverse/mp4/media/web/ori/a.mp4"
    )


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


def test_generate_pixverse_rejects_local_path_without_upload_authorization(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    img = tmp_path / "a.jpg"
    img.write_bytes(b"jpeg")
    with pytest.raises(TokenHubError, match="explicit project upload authorization"):
        generate_pixverse_video(
            "x",
            mode="i2v",
            image_path=str(img),
            project_id="demo",
            client=TokenHubClient(api_key="test-key"),
        )


def test_generate_pixverse_never_stages_local_image_in_t2v_mode(monkeypatch):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    ensure = MagicMock()
    monkeypatch.setattr("tools._tokenhub.pixverse.ensure_public_image_url", ensure)

    with pytest.raises(TokenHubError, match="only valid in i2v mode"):
        generate_pixverse_video(
            "x",
            mode="t2v",
            image_path="projects/demo/assets/images/a.png",
            project_id="demo",
            user_authorized_upload=True,
            client=TokenHubClient(api_key="test-key"),
        )

    ensure.assert_not_called()


def test_generate_video_stages_local_pixverse_image_and_cleans_after_download(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    image = tmp_path / "projects" / "demo" / "assets" / "images" / "a.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"png")
    output = tmp_path / "projects" / "demo" / "renders" / "clip.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"0" * 12000)

    from tools.media.public_image import StagedPublicImage

    staged = StagedPublicImage(
        url="https://bucket.example.com/signed.png?signature=secret",
        backend="aliyun_oss",
        object_key="openmontage/tmp/demo/object.png",
        source_sha256="abc",
        expires_at=datetime.now(timezone.utc),
        staged=True,
    )
    ensure = MagicMock(return_value=staged)
    cleanup = MagicMock(return_value=True)
    monkeypatch.setattr("tools._tokenhub.pixverse.ensure_public_image_url", ensure)
    monkeypatch.setattr("tools._tokenhub.pixverse.cleanup_public_image", cleanup)

    client = TokenHubClient(api_key="test-key", base_url="https://tokenhub.test/v1")

    def fake_post(path: str, payload: dict, **_kwargs):
        assert path == "/wand/pixverse/image-to-video"
        assert payload["img_id"] == staged.url
        return {"task_id": "pv-local", "status": "submitted"}

    client.post = fake_post  # type: ignore[method-assign]
    client.get = lambda *_args, **_kwargs: {
        "status": "completed",
        "video_url": "https://cdn.example.com/local.mp4",
    }  # type: ignore[method-assign]
    monkeypatch.setattr(
        "tools._tokenhub.pixverse.download_video",
        MagicMock(return_value=output),
    )
    monkeypatch.setattr("tools._tokenhub.pixverse.time.sleep", lambda *_: None)

    result = generate_video(
        "自然转头",
        model=PIXVERSE_DEFAULT_MODEL,
        image_path=str(image),
        project_id="demo",
        user_authorized_upload=True,
        output_path=output,
        client=client,
        poll_interval_seconds=0.01,
    )

    assert result["output_path"] == str(output)
    ensure.assert_called_once_with(
        str(image),
        project_id="demo",
        user_authorized_upload=True,
    )
    cleanup.assert_called_once_with(staged, project_id="demo")


def test_staged_signed_url_is_redacted_from_pixverse_errors(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    image = tmp_path / "projects" / "demo" / "assets" / "images" / "a.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"png")
    signed_url = "https://bucket.example.com/a.png?signature=must-not-leak"

    from tools.media.public_image import StagedPublicImage

    staged = StagedPublicImage(
        url=signed_url,
        backend="aliyun_oss",
        object_key="openmontage/tmp/demo/object.png",
        source_sha256="abc",
        expires_at=datetime.now(timezone.utc),
        staged=True,
    )
    monkeypatch.setattr(
        "tools._tokenhub.pixverse.ensure_public_image_url",
        MagicMock(return_value=staged),
    )
    monkeypatch.setattr(
        "tools._tokenhub.pixverse.cleanup_public_image",
        MagicMock(return_value=True),
    )
    client = TokenHubClient(api_key="test-key", base_url="https://tokenhub.test/v1")
    client.post = lambda *_args, **_kwargs: {
        "status": "failed",
        "message": signed_url,
    }  # type: ignore[method-assign]

    with pytest.raises(TokenHubError) as caught:
        generate_video(
            "自然转头",
            model=PIXVERSE_DEFAULT_MODEL,
            image_path=str(image),
            project_id="demo",
            user_authorized_upload=True,
            client=client,
        )

    assert signed_url not in str(caught.value)
    assert signed_url not in repr(caught.value.response)
    assert signed_url not in "".join(
        traceback.format_exception(
            type(caught.value),
            caught.value,
            caught.value.__traceback__,
        )
    )


def test_download_timeout_cleans_staged_image_instead_of_retaining(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("TOKENHUB_API_KEY", "test-key")
    image = tmp_path / "projects" / "demo" / "assets" / "images" / "a.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"png")

    from tools.media.public_image import StagedPublicImage

    staged = StagedPublicImage(
        url="https://bucket.example.com/signed.png?signature=secret",
        backend="aliyun_oss",
        object_key="openmontage/tmp/demo/object.png",
        source_sha256="abc",
        expires_at=datetime.now(timezone.utc),
        staged=True,
    )
    cleanup = MagicMock(return_value=True)
    retain = MagicMock()
    monkeypatch.setattr(
        "tools._tokenhub.pixverse.ensure_public_image_url",
        MagicMock(return_value=staged),
    )
    monkeypatch.setattr("tools._tokenhub.pixverse.cleanup_public_image", cleanup)
    monkeypatch.setattr("tools._tokenhub.pixverse.retain_public_image", retain)
    monkeypatch.setattr(
        "tools._tokenhub.pixverse._download_with_cdn_retry",
        MagicMock(side_effect=TokenHubError("Read timed out")),
    )
    client = TokenHubClient(api_key="test-key", base_url="https://tokenhub.test/v1")
    client.post = lambda *_args, **_kwargs: {
        "task_id": "pv-download-timeout",
        "status": "completed",
        "video_url": "https://cdn.example.com/video.mp4",
    }  # type: ignore[method-assign]

    with pytest.raises(TokenHubError, match="Read timed out"):
        generate_video(
            "自然转头",
            model=PIXVERSE_DEFAULT_MODEL,
            image_path=str(image),
            project_id="demo",
            user_authorized_upload=True,
            output_path=tmp_path / "clip.mp4",
            client=client,
        )

    cleanup.assert_called_once_with(staged, project_id="demo")
    retain.assert_not_called()

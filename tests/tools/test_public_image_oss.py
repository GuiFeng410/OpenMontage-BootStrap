from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from tools.media.backends.aliyun_oss import (
    AliyunOSSBackend,
    AliyunOSSConfig,
    AliyunOSSConfigurationError,
)
from tools.media.public_image import (
    PublicImageSafetyError,
    PublicImageUploadConsentError,
    cleanup_public_image,
    ensure_public_image_url,
)


class FakeBackend:
    name = "aliyun_oss"

    def __init__(self) -> None:
        self.uploads: list[tuple[Path, str, int]] = []
        self.deleted: list[str] = []

    def upload_and_sign(
        self,
        local_path: Path,
        *,
        object_key: str,
        expires_sec: int,
    ) -> tuple[str, datetime]:
        self.uploads.append((local_path, object_key, expires_sec))
        return (
            f"https://bucket.example.com/{object_key}?signature=do-not-persist",
            datetime.now(timezone.utc),
        )

    def delete(self, object_key: str) -> None:
        self.deleted.append(object_key)


def _project_image(tmp_path: Path, project_id: str = "demo") -> Path:
    image = tmp_path / project_id / "assets" / "images" / "product.png"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8), color=(20, 40, 60)).save(image)
    return image


def test_public_http_url_is_passthrough_without_upload(tmp_path: Path):
    backend = FakeBackend()

    ref = ensure_public_image_url(
        "https://cdn.example.com/product.png",
        project_id="demo",
        user_authorized_upload=False,
        backend=backend,
        projects_root=tmp_path,
    )

    assert ref.url == "https://cdn.example.com/product.png"
    assert ref.staged is False
    assert backend.uploads == []


def test_local_image_requires_explicit_project_upload_authorization(tmp_path: Path):
    image = _project_image(tmp_path)

    with pytest.raises(PublicImageUploadConsentError, match="explicit project upload authorization"):
        ensure_public_image_url(
            image,
            project_id="demo",
            user_authorized_upload=False,
            backend=FakeBackend(),
            projects_root=tmp_path,
        )


def test_local_image_must_be_inside_project_assets_images(tmp_path: Path):
    outside = tmp_path / "outside.png"
    Image.new("RGB", (8, 8)).save(outside)

    with pytest.raises(PublicImageSafetyError, match="assets/images"):
        ensure_public_image_url(
            outside,
            project_id="demo",
            user_authorized_upload=True,
            backend=FakeBackend(),
            projects_root=tmp_path,
        )


def test_staged_image_ledger_never_persists_signed_url(tmp_path: Path):
    image = _project_image(tmp_path)
    backend = FakeBackend()

    ref = ensure_public_image_url(
        image,
        project_id="demo",
        user_authorized_upload=True,
        backend=backend,
        projects_root=tmp_path,
    )

    assert ref.staged is True
    assert ref.url.startswith("https://")
    assert ref.object_key
    ledger_path = tmp_path / "demo" / "artifacts" / "oss_staging.json"
    ledger_text = ledger_path.read_text(encoding="utf-8")
    ledger = json.loads(ledger_text)
    assert "signature=" not in ledger_text
    assert ledger["entries"][0]["object_key"] == ref.object_key
    assert ledger["entries"][0]["status"] == "staged"

    assert cleanup_public_image(
        ref,
        project_id="demo",
        backend=backend,
        projects_root=tmp_path,
    )
    assert backend.deleted == [ref.object_key]
    updated = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert updated["entries"][0]["status"] == "deleted"


def test_cleanup_failure_is_logged_without_signed_url_or_masking(tmp_path: Path, caplog):
    image = _project_image(tmp_path)
    backend = FakeBackend()
    ref = ensure_public_image_url(
        image,
        project_id="demo",
        user_authorized_upload=True,
        backend=backend,
        projects_root=tmp_path,
    )

    class FailingDeleteBackend(FakeBackend):
        def delete(self, _object_key: str) -> None:
            raise RuntimeError("delete failed")

    assert (
        cleanup_public_image(
            ref,
            project_id="demo",
            backend=FailingDeleteBackend(),
            projects_root=tmp_path,
        )
        is False
    )
    ledger = json.loads(
        (tmp_path / "demo" / "artifacts" / "oss_staging.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["entries"][0]["status"] == "delete_failed"
    assert "signature=do-not-persist" not in caplog.text


def test_cleanup_does_not_mask_success_when_ledger_update_fails(
    tmp_path: Path,
    monkeypatch,
):
    image = _project_image(tmp_path)
    backend = FakeBackend()
    ref = ensure_public_image_url(
        image,
        project_id="demo",
        user_authorized_upload=True,
        backend=backend,
        projects_root=tmp_path,
    )

    def fail_ledger(*_args, **_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(
        "tools.media.public_image._update_staging_status",
        fail_ledger,
    )

    assert cleanup_public_image(
        ref,
        project_id="demo",
        backend=backend,
        projects_root=tmp_path,
    )
    assert backend.deleted == [ref.object_key]


def test_rejects_non_image_content_before_upload(tmp_path: Path):
    fake = tmp_path / "demo" / "assets" / "images" / "not-image.png"
    fake.parent.mkdir(parents=True)
    fake.write_text("not an image", encoding="utf-8")
    backend = FakeBackend()

    with pytest.raises(PublicImageSafetyError, match="valid JPEG, PNG, or WebP"):
        ensure_public_image_url(
            fake,
            project_id="demo",
            user_authorized_upload=True,
            backend=backend,
            projects_root=tmp_path,
        )

    assert backend.uploads == []


def test_aliyun_config_accepts_official_env_and_aliases():
    official = AliyunOSSConfig.from_mapping(
        {
            "OSS_ACCESS_KEY_ID": "official-id",
            "OSS_ACCESS_KEY_SECRET": "official-secret",
            "ALIYUN_OSS_BUCKET": "bucket",
            "ALIYUN_OSS_REGION": "cn-hangzhou",
        }
    )
    alias = AliyunOSSConfig.from_mapping(
        {
            "ALIYUN_OSS_ACCESS_KEY_ID": "alias-id",
            "ALIYUN_OSS_ACCESS_KEY_SECRET": "alias-secret",
            "ALIYUN_OSS_BUCKET": "bucket",
            "ALIYUN_OSS_REGION": "cn-hangzhou",
        }
    )

    assert official.access_key_id == "official-id"
    assert alias.access_key_id == "alias-id"


def test_aliyun_config_normalizes_external_endpoint_for_sdk():
    config = AliyunOSSConfig.from_mapping(
        {
            "OSS_ACCESS_KEY_ID": "id",
            "OSS_ACCESS_KEY_SECRET": "secret",
            "ALIYUN_OSS_BUCKET": "bucket",
            "ALIYUN_OSS_REGION": "cn-hangzhou",
            "ALIYUN_OSS_ENDPOINT": "https://oss-cn-hangzhou.aliyuncs.com",
        }
    )

    assert config.endpoint == "oss-cn-hangzhou.aliyuncs.com"


def test_aliyun_config_rejects_partial_credentials():
    with pytest.raises(AliyunOSSConfigurationError, match="OSS_ACCESS_KEY_SECRET"):
        AliyunOSSConfig.from_mapping(
            {
                "OSS_ACCESS_KEY_ID": "id",
                "ALIYUN_OSS_BUCKET": "bucket",
                "ALIYUN_OSS_REGION": "cn-hangzhou",
            }
        )


def test_aliyun_backend_puts_presigns_and_deletes_without_logging_url(tmp_path: Path):
    requests: list[object] = []

    class FakeClient:
        def put_object(self, request):
            requests.append(request)
            return SimpleNamespace(etag="etag")

        def presign(self, request, **kwargs):
            requests.append((request, kwargs))
            return SimpleNamespace(url="https://bucket.example.com/signed?signature=secret")

        def delete_object(self, request):
            requests.append(request)
            return SimpleNamespace()

    class FakeSDK:
        class PutObjectRequest(SimpleNamespace):
            pass

        class GetObjectRequest(SimpleNamespace):
            pass

        class DeleteObjectRequest(SimpleNamespace):
            pass

    config = AliyunOSSConfig(
        access_key_id="id",
        access_key_secret="secret",
        security_token=None,
        bucket="bucket",
        region="cn-hangzhou",
        endpoint=None,
        prefix="openmontage/tmp/",
        expires_sec=21600,
    )
    backend = AliyunOSSBackend(config, client=FakeClient(), sdk=FakeSDK)
    image = tmp_path / "image.png"
    image.write_bytes(b"image")

    url, _expires_at = backend.upload_and_sign(
        image,
        object_key="openmontage/tmp/demo/a.png",
        expires_sec=21600,
    )
    backend.delete("openmontage/tmp/demo/a.png")

    assert url.startswith("https://")
    assert requests[0].bucket == "bucket"
    assert requests[0].key == "openmontage/tmp/demo/a.png"
    presign_request, presign_kwargs = requests[1]
    assert presign_request.bucket == "bucket"
    assert presign_request.key == "openmontage/tmp/demo/a.png"
    assert int(presign_kwargs["expires"].total_seconds()) == 21600
    assert requests[2].key == "openmontage/tmp/demo/a.png"


def test_aliyun_backend_deletes_uploaded_object_when_presign_fails(tmp_path: Path):
    deleted: list[str] = []

    class FakeClient:
        def put_object(self, _request):
            return SimpleNamespace(etag="etag")

        def presign(self, _request, **_kwargs):
            raise RuntimeError("presign failed")

        def delete_object(self, request):
            deleted.append(request.key)

    class FakeSDK:
        class PutObjectRequest(SimpleNamespace):
            pass

        class GetObjectRequest(SimpleNamespace):
            pass

        class DeleteObjectRequest(SimpleNamespace):
            pass

    config = AliyunOSSConfig(
        access_key_id="id",
        access_key_secret="secret",
        security_token=None,
        bucket="bucket",
        region="cn-hangzhou",
        endpoint=None,
        prefix="openmontage/tmp/",
        expires_sec=21600,
    )
    backend = AliyunOSSBackend(config, client=FakeClient(), sdk=FakeSDK)
    image = tmp_path / "image.png"
    image.write_bytes(b"image")

    with pytest.raises(RuntimeError, match="presign failed"):
        backend.upload_and_sign(
            image,
            object_key="openmontage/tmp/demo/a.png",
            expires_sec=21600,
        )

    assert deleted == ["openmontage/tmp/demo/a.png"]


def test_aliyun_backend_deletes_uploaded_object_for_non_https_signed_url(
    tmp_path: Path,
):
    deleted: list[str] = []

    class FakeClient:
        def put_object(self, _request):
            return SimpleNamespace(etag="etag")

        def presign(self, _request, **_kwargs):
            return SimpleNamespace(url="http://bucket.example.com/insecure")

        def delete_object(self, request):
            deleted.append(request.key)

    class FakeSDK:
        class PutObjectRequest(SimpleNamespace):
            pass

        class GetObjectRequest(SimpleNamespace):
            pass

        class DeleteObjectRequest(SimpleNamespace):
            pass

    config = AliyunOSSConfig(
        access_key_id="id",
        access_key_secret="secret",
        security_token=None,
        bucket="bucket",
        region="cn-hangzhou",
        endpoint=None,
        prefix="openmontage/tmp/",
        expires_sec=21600,
    )
    backend = AliyunOSSBackend(config, client=FakeClient(), sdk=FakeSDK)
    image = tmp_path / "image.png"
    image.write_bytes(b"image")

    with pytest.raises(RuntimeError, match="non-HTTPS"):
        backend.upload_and_sign(
            image,
            object_key="openmontage/tmp/demo/a.png",
            expires_sec=21600,
        )

    assert deleted == ["openmontage/tmp/demo/a.png"]

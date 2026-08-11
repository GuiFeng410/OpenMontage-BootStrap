"""Alibaba Cloud OSS v2 backend for short-lived public image staging."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

DEFAULT_EXPIRES_SEC = 21600
MIN_EXPIRES_SEC = 900
MAX_EXPIRES_SEC = 604800


class AliyunOSSConfigurationError(RuntimeError):
    """Raised when OSS configuration is missing or unsafe."""


def _value(mapping: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        value = str(mapping.get(key) or "").strip()
        if value:
            return value
    return ""


@dataclass(frozen=True)
class AliyunOSSConfig:
    access_key_id: str
    access_key_secret: str
    security_token: str | None
    bucket: str
    region: str
    endpoint: str | None
    prefix: str
    expires_sec: int

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, str]) -> "AliyunOSSConfig":
        access_key_id = _value(
            mapping,
            "OSS_ACCESS_KEY_ID",
            "ALIYUN_OSS_ACCESS_KEY_ID",
        )
        access_key_secret = _value(
            mapping,
            "OSS_ACCESS_KEY_SECRET",
            "ALIYUN_OSS_ACCESS_KEY_SECRET",
        )
        bucket = _value(mapping, "ALIYUN_OSS_BUCKET")
        region = _value(mapping, "ALIYUN_OSS_REGION")
        missing = [
            name
            for name, value in (
                ("OSS_ACCESS_KEY_ID", access_key_id),
                ("OSS_ACCESS_KEY_SECRET", access_key_secret),
                ("ALIYUN_OSS_BUCKET", bucket),
                ("ALIYUN_OSS_REGION", region),
            )
            if not value
        ]
        if missing:
            raise AliyunOSSConfigurationError(
                "Alibaba OSS staging is not fully configured; missing: "
                + ", ".join(missing)
            )

        endpoint = _value(mapping, "ALIYUN_OSS_ENDPOINT") or None
        if endpoint:
            parts = urlsplit(
                endpoint if "://" in endpoint else f"https://{endpoint}"
            )
            hostname = (parts.hostname or "").lower()
            if parts.scheme != "https" or not hostname:
                raise AliyunOSSConfigurationError(
                    "ALIYUN_OSS_ENDPOINT must be a valid HTTPS endpoint"
                )
            if "-internal." in hostname or hostname.endswith("-internal"):
                raise AliyunOSSConfigurationError(
                    "ALIYUN_OSS_ENDPOINT must be externally reachable, not an internal endpoint"
                )
            endpoint = f"{parts.netloc}{parts.path}".rstrip("/")

        raw_prefix = _value(mapping, "ALIYUN_OSS_PREFIX") or "openmontage/tmp/"
        prefix = raw_prefix.strip().strip("/")
        if not prefix:
            prefix = "openmontage/tmp"
        prefix = f"{prefix}/"

        raw_expires = _value(mapping, "OSS_SIGNED_URL_EXPIRES_SEC")
        try:
            expires_sec = int(raw_expires or DEFAULT_EXPIRES_SEC)
        except ValueError as exc:
            raise AliyunOSSConfigurationError(
                "OSS_SIGNED_URL_EXPIRES_SEC must be an integer"
            ) from exc
        if not MIN_EXPIRES_SEC <= expires_sec <= MAX_EXPIRES_SEC:
            raise AliyunOSSConfigurationError(
                f"OSS_SIGNED_URL_EXPIRES_SEC must be between "
                f"{MIN_EXPIRES_SEC} and {MAX_EXPIRES_SEC}"
            )

        return cls(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            security_token=_value(
                mapping,
                "OSS_SESSION_TOKEN",
                "ALIYUN_OSS_SESSION_TOKEN",
            )
            or None,
            bucket=bucket,
            region=region,
            endpoint=endpoint,
            prefix=prefix,
            expires_sec=expires_sec,
        )

    @classmethod
    def from_env(cls) -> "AliyunOSSConfig":
        return cls.from_mapping(os.environ)

    @staticmethod
    def is_configured(mapping: Mapping[str, str] | None = None) -> bool:
        source = mapping if mapping is not None else os.environ
        return all(
            (
                _value(source, "OSS_ACCESS_KEY_ID", "ALIYUN_OSS_ACCESS_KEY_ID"),
                _value(
                    source,
                    "OSS_ACCESS_KEY_SECRET",
                    "ALIYUN_OSS_ACCESS_KEY_SECRET",
                ),
                _value(source, "ALIYUN_OSS_BUCKET"),
                _value(source, "ALIYUN_OSS_REGION"),
            )
        )


class AliyunOSSBackend:
    name = "aliyun_oss"

    def __init__(
        self,
        config: AliyunOSSConfig,
        *,
        client: Any | None = None,
        sdk: Any | None = None,
    ) -> None:
        self.config = config
        if sdk is None:
            try:
                import alibabacloud_oss_v2 as sdk_module
            except ImportError as exc:
                raise AliyunOSSConfigurationError(
                    "Alibaba OSS staging requires package 'alibabacloud-oss-v2'"
                ) from exc
            sdk = sdk_module
        self._sdk = sdk
        self._client = client or self._build_client()

    @classmethod
    def from_env(cls) -> "AliyunOSSBackend":
        return cls(AliyunOSSConfig.from_env())

    def _build_client(self) -> Any:
        credential_kwargs = {
            "access_key_id": self.config.access_key_id,
            "access_key_secret": self.config.access_key_secret,
        }
        if self.config.security_token:
            credential_kwargs["security_token"] = self.config.security_token
        provider = self._sdk.credentials.StaticCredentialsProvider(
            **credential_kwargs,
        )
        cfg = self._sdk.config.load_default()
        cfg.credentials_provider = provider
        cfg.region = self.config.region
        if self.config.endpoint:
            cfg.endpoint = self.config.endpoint
        return self._sdk.Client(cfg)

    def upload_and_sign(
        self,
        local_path: Path,
        *,
        object_key: str,
        expires_sec: int,
    ) -> tuple[str, datetime]:
        with local_path.open("rb") as handle:
            self._client.put_object(
                self._sdk.PutObjectRequest(
                    bucket=self.config.bucket,
                    key=object_key,
                    body=handle,
                )
            )
        try:
            result = self._client.presign(
                self._sdk.GetObjectRequest(
                    bucket=self.config.bucket,
                    key=object_key,
                ),
                expires=timedelta(seconds=expires_sec),
            )
            url = str(getattr(result, "url", "") or "")
            if not url.startswith("https://"):
                raise RuntimeError("Alibaba OSS returned a non-HTTPS signed URL")
        except Exception:
            try:
                self.delete(object_key)
            except Exception:
                pass
            raise
        return url, datetime.now(timezone.utc) + timedelta(seconds=expires_sec)

    def delete(self, object_key: str) -> None:
        self._client.delete_object(
            self._sdk.DeleteObjectRequest(
                bucket=self.config.bucket,
                key=object_key,
            )
        )

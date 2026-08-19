"""Fail-closed staging of project images behind short-lived public URLs."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

from tools.media.backends.aliyun_oss import (
    AliyunOSSBackend,
    AliyunOSSConfig,
    AliyunOSSConfigurationError,
)

LOGGER = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 20 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


class PublicImageError(RuntimeError):
    """Base error for public image staging."""


class PublicImageConfigurationError(PublicImageError):
    """Raised when no usable public image backend is configured."""


class PublicImageUploadConsentError(PublicImageError):
    """Raised when a local image upload was not explicitly authorized."""


class PublicImageSafetyError(PublicImageError):
    """Raised before upload when a local source violates safety boundaries."""


class PublicImageBackend(Protocol):
    name: str

    def upload_and_sign(
        self,
        local_path: Path,
        *,
        object_key: str,
        expires_sec: int,
    ) -> tuple[str, datetime]: ...

    def delete(self, object_key: str) -> None: ...


@dataclass(frozen=True)
class StagedPublicImage:
    url: str
    backend: str | None
    object_key: str | None
    source_sha256: str | None
    expires_at: datetime | None
    staged: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _projects_root(projects_root: Path | None = None) -> Path:
    if projects_root is not None:
        return Path(projects_root).resolve()
    from lib.paths import get_workspace

    return get_workspace().projects_dir.resolve()


def _safe_project_root(project_id: str, projects_root: Path | None = None) -> Path:
    value = str(project_id or "").strip()
    if not value:
        raise PublicImageSafetyError("project_id is required for local image upload")
    root = _projects_root(projects_root)
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PublicImageSafetyError("project_id escapes the projects root") from exc
    return candidate


def _validate_project_image(
    source: str | Path,
    *,
    project_id: str,
    projects_root: Path | None,
) -> tuple[Path, str, str]:
    project_root = _safe_project_root(project_id, projects_root)
    allowed_root = (project_root / "assets" / "images").resolve()
    path = Path(source).expanduser().resolve()
    try:
        path.relative_to(allowed_root)
    except ValueError as exc:
        raise PublicImageSafetyError(
            "Local uploads must come from the current project's assets/images directory"
        ) from exc
    if not path.is_file():
        raise PublicImageSafetyError(f"Local image not found: {path}")
    size = path.stat().st_size
    if size <= 0 or size > MAX_IMAGE_BYTES:
        raise PublicImageSafetyError(
            f"Local image must be between 1 byte and {MAX_IMAGE_BYTES} bytes"
        )
    try:
        with Image.open(path) as image:
            image.verify()
            image_format = str(image.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PublicImageSafetyError(
            "Local upload must be a valid JPEG, PNG, or WebP image"
        ) from exc
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise PublicImageSafetyError(
            "Local upload must be a valid JPEG, PNG, or WebP image"
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, digest, image_format


def _ledger_path(
    project_id: str,
    projects_root: Path | None = None,
) -> Path:
    return _safe_project_root(project_id, projects_root) / "artifacts" / "oss_staging.json"


def _read_ledger(path: Path, project_id: str) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": "1.0", "project_id": project_id, "entries": []}


def _write_ledger(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _record_staged(
    ref: StagedPublicImage,
    *,
    project_id: str,
    projects_root: Path | None,
) -> None:
    path = _ledger_path(project_id, projects_root)
    ledger = _read_ledger(path, project_id)
    entry = {
        "backend": ref.backend,
        "object_key": ref.object_key,
        "source_sha256": ref.source_sha256,
        "expires_at": ref.expires_at.isoformat() if ref.expires_at else None,
        "status": "staged",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    ledger["entries"].append(entry)
    _write_ledger(path, ledger)


def _update_staging_status(
    ref: StagedPublicImage,
    *,
    project_id: str,
    status: str,
    projects_root: Path | None,
    note: str | None = None,
) -> None:
    if not ref.object_key:
        return
    path = _ledger_path(project_id, projects_root)
    ledger = _read_ledger(path, project_id)
    for entry in reversed(ledger["entries"]):
        if entry.get("object_key") == ref.object_key:
            entry["status"] = status
            entry["updated_at"] = _utc_now()
            if note:
                entry["note"] = note
            break
    _write_ledger(path, ledger)


def _default_backend() -> AliyunOSSBackend:
    try:
        return AliyunOSSBackend.from_env()
    except AliyunOSSConfigurationError as exc:
        raise PublicImageConfigurationError(str(exc)) from exc


def _best_effort_status_update(
    ref: StagedPublicImage,
    *,
    project_id: str,
    status: str,
    projects_root: Path | None,
    note: str | None = None,
) -> None:
    try:
        _update_staging_status(
            ref,
            project_id=project_id,
            status=status,
            projects_root=projects_root,
            note=note,
        )
    except Exception as exc:
        LOGGER.warning(
            "Could not update public image staging ledger: backend=%s key=%s error=%s",
            ref.backend,
            ref.object_key,
            type(exc).__name__,
        )


def ensure_public_image_url(
    source: str | Path,
    *,
    project_id: str,
    user_authorized_upload: bool,
    backend: PublicImageBackend | None = None,
    projects_root: Path | None = None,
) -> StagedPublicImage:
    """Return a URL directly or stage one project image after explicit consent."""
    raw = str(source or "").strip()
    parts = urlsplit(raw)
    if parts.scheme in {"http", "https"} and parts.netloc:
        return StagedPublicImage(
            url=raw,
            backend=None,
            object_key=None,
            source_sha256=None,
            expires_at=None,
            staged=False,
        )
    if not user_authorized_upload:
        raise PublicImageUploadConsentError(
            "Local image staging requires explicit project upload authorization"
        )

    path, digest, image_format = _validate_project_image(
        source,
        project_id=project_id,
        projects_root=projects_root,
    )
    selected = backend or _default_backend()
    config = getattr(selected, "config", None)
    prefix = getattr(config, "prefix", "openmontage/tmp/")
    expires_sec = int(getattr(config, "expires_sec", 21600))
    suffix = {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
    }[image_format]
    key_project_id = re.sub(r"[^A-Za-z0-9._-]+", "-", project_id).strip("-")[:80]
    if not key_project_id:
        key_project_id = "project"
    object_key = (
        f"{str(prefix).strip('/')}/{key_project_id}/"
        f"{datetime.now(timezone.utc):%Y%m%d}/{uuid.uuid4().hex}{suffix}"
    )
    try:
        signed_url, expires_at = selected.upload_and_sign(
            path,
            object_key=object_key,
            expires_sec=expires_sec,
        )
    except Exception as exc:
        raise PublicImageError(
            f"Failed to stage project image with backend {selected.name}"
        ) from exc
    ref = StagedPublicImage(
        url=signed_url,
        backend=selected.name,
        object_key=object_key,
        source_sha256=digest,
        expires_at=expires_at,
        staged=True,
    )
    try:
        _record_staged(
            ref,
            project_id=project_id,
            projects_root=projects_root,
        )
    except Exception:
        try:
            selected.delete(object_key)
        except Exception:
            LOGGER.warning(
                "Could not clean staged object after ledger write failure: backend=%s key=%s",
                selected.name,
                object_key,
            )
        raise
    return ref


def cleanup_public_image(
    ref: StagedPublicImage,
    *,
    project_id: str,
    backend: PublicImageBackend | None = None,
    projects_root: Path | None = None,
) -> bool:
    """Best-effort delete for a staged object; never log its signed URL."""
    if not ref.staged or not ref.object_key:
        return True
    try:
        selected = backend or _default_backend()
    except Exception as exc:
        LOGGER.warning(
            "Could not initialize staged image cleanup: backend=%s key=%s error=%s",
            ref.backend,
            ref.object_key,
            type(exc).__name__,
        )
        _best_effort_status_update(
            ref,
            project_id=project_id,
            status="delete_failed",
            projects_root=projects_root,
            note=type(exc).__name__,
        )
        return False
    try:
        selected.delete(ref.object_key)
    except Exception as exc:
        LOGGER.warning(
            "Could not delete staged public image: backend=%s key=%s error=%s",
            ref.backend,
            ref.object_key,
            type(exc).__name__,
        )
        _best_effort_status_update(
            ref,
            project_id=project_id,
            status="delete_failed",
            projects_root=projects_root,
            note=type(exc).__name__,
        )
        return False
    _best_effort_status_update(
        ref,
        project_id=project_id,
        status="deleted",
        projects_root=projects_root,
    )
    return True


def retain_public_image(
    ref: StagedPublicImage,
    *,
    project_id: str,
    reason: str,
    projects_root: Path | None = None,
) -> None:
    """Mark a timed-out staging object for later cleanup without exposing its URL."""
    if not ref.staged:
        return
    _best_effort_status_update(
        ref,
        project_id=project_id,
        status="retained",
        projects_root=projects_root,
        note=str(reason)[:120],
    )

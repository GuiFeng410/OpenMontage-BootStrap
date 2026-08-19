"""Shared constants and path helpers for read-only Backlot projections."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from lib.paths import REPO_ROOT


MEDIA_IMAGE_EXT = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".svg",
}
MEDIA_VIDEO_EXT = {".mp4", ".webm", ".mov"}
MEDIA_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg"}

COMMERCIAL_STAGE_LABELS_ZH = {
    "brief_locked": "方案确认",
    "assets_gate": "素材检查",
    "sample_review": "试片确认",
    "segment_build": "分段制作",
    "draft_review": "初稿审查",
    "final_compose": "合成终稿",
    "delivery_signoff": "交付确认",
}


def rel(project_dir: Path, path: Path) -> str:
    """Return a project-relative POSIX path for media URLs."""
    try:
        return path.resolve().relative_to(Path(project_dir).resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


def resolve_asset_path(project_dir: Path, raw_path: str) -> Optional[Path]:
    """Resolve the path formats found in manifests without requiring one form."""
    if not raw_path:
        return None
    path = Path(raw_path)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.append(project_dir / raw_path)
        candidates.append(REPO_ROOT / raw_path)
        parts = path.parts
        if len(parts) > 2 and parts[0] == "projects":
            candidates.append(project_dir.parent / Path(*parts[1:]))
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def canonical_video_candidate(project_dir: Path, raw: Any) -> Optional[Path]:
    """Resolve a safe in-project video candidate without requiring it to exist."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    normalized = raw.strip().replace("\\", "/")
    candidate = Path(normalized)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    parts = candidate.parts
    if parts and parts[0] == "projects":
        if len(parts) < 3 or parts[1] != project_dir.name:
            return None
        candidate = Path(*parts[2:])
    if candidate.suffix.lower() not in MEDIA_VIDEO_EXT:
        return None
    try:
        resolved = (project_dir / candidate).resolve()
        resolved.relative_to(project_dir.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def canonical_video_path(project_dir: Path, raw: Any) -> Optional[str]:
    """Resolve one canonical artifact video without scanning for substitutes."""
    resolved = canonical_video_candidate(project_dir, raw)
    if resolved is None:
        return None
    try:
        if not resolved.is_file() or resolved.stat().st_size <= 0:
            return None
    except OSError:
        return None
    return rel(project_dir, resolved)

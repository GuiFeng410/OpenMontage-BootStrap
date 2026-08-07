"""Read-only facts scanner for uploaded commercial product images."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

_ROLE_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("hero", "main", "front", "主图", "正面"), "product_hero"),
    (("detail", "macro", "close", "细节", "微距"), "product_detail"),
    (("angle", "side", "back", "角度", "侧面", "背面"), "product_angle"),
    (("hand", "wear", "body", "佩戴", "手持", "上身"), "on_body"),
)


def _suggested_class(filename: str) -> str:
    folded = filename.lower()
    for hints, role in _ROLE_HINTS:
        if any(hint.lower() in folded for hint in hints):
            return role
    return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_user_images(project_dir: str | Path, *, min_dimension: int = 640) -> dict[str, Any]:
    """Return image facts and filename-only role suggestions without writing files."""
    project_path = Path(project_dir).resolve()
    images_dir = project_path / "assets" / "images"
    entries: list[dict[str, Any]] = []
    by_digest: dict[str, dict[str, Any]] = {}

    if images_dir.is_dir():
        for path in sorted(images_dir.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file():
                continue
            try:
                with Image.open(path) as image:
                    width, height = image.size
                    image.verify()
            except (OSError, UnidentifiedImageError):
                continue

            digest = _sha256(path)
            issues: list[str] = []
            if width < min_dimension or height < min_dimension:
                issues.append("resolution_too_small")
            entry: dict[str, Any] = {
                "file": path.name,
                "path": path.relative_to(project_path).as_posix(),
                "width": width,
                "height": height,
                "bytes": path.stat().st_size,
                "sha256": digest,
                "suggested_class": _suggested_class(path.stem),
                "user_class": "",
                "status": "pending_user_confirmation",
                "issues": issues,
            }
            original = by_digest.get(digest)
            if original:
                entry["duplicate_of"] = original["file"]
            else:
                by_digest[digest] = entry
            entries.append(entry)

    low_resolution_count = sum(bool(entry["issues"]) for entry in entries)
    duplicate_group_count = sum(1 for entry in entries if entry.get("duplicate_of"))
    has_unclassified_image = any(not entry["suggested_class"] for entry in entries)
    return {
        "version": "1.0",
        "source_dir": "assets/images",
        "entries": entries,
        "summary": {
            "total_images": len(entries),
            "low_resolution_count": low_resolution_count,
            "duplicate_group_count": duplicate_group_count,
            "needs_user_attention": (
                not entries
                or has_unclassified_image
                or bool(low_resolution_count or duplicate_group_count)
            ),
        },
    }

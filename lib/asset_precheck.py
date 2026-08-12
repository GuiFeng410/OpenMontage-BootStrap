"""Read-only facts scanner for uploaded commercial product images.

P0 hybrid preprocess: program reports hard facts + filename class hints only.
No vision API. User confirmation writes ``asset_ledger`` via the agent gate.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

_ROLE_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("hero", "main", "front", "主图", "正面"), "product_hero"),
    (("detail", "macro", "close", "细节", "微距"), "product_detail"),
    (("angle", "side", "back", "角度", "侧面", "背面"), "product_angle"),
    (("hand", "wear", "body", "佩戴", "手持", "上身"), "on_body"),
    (("pack", "box", "包装"), "packaging"),
    (("scene", "lifestyle", "场景", "氛围"), "lifestyle"),
)

# Duration band → (minimum images, recommended images, preferred classes)
_DURATION_BANDS: tuple[tuple[int, int, int, tuple[str, ...]], ...] = (
    (10, 1, 3, ("product_hero", "product_angle", "product_detail")),
    (30, 2, 6, ("product_hero", "product_angle", "product_detail", "on_body")),
    (60, 3, 10, ("product_hero", "product_angle", "product_detail", "on_body", "lifestyle")),
)

_ENTRY_METADATA_FIELDS = {
    "beat",
    "kind",
    "origin",
    "selected",
    "label_zh",
    "note_zh",
}


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
    counts = Counter(
        entry["suggested_class"] or "unclassified" for entry in entries
    )
    return {
        "version": "1.0",
        "source_dir": "assets/images",
        "entries": entries,
        "summary": {
            "total_images": len(entries),
            "low_resolution_count": low_resolution_count,
            "duplicate_group_count": duplicate_group_count,
            "counts_by_suggested_class": dict(counts),
            "needs_user_attention": (
                not entries
                or has_unclassified_image
                or bool(low_resolution_count or duplicate_group_count)
            ),
        },
    }


def duration_profile(duration_seconds: int | float) -> dict[str, Any]:
    """Return minimum / recommended image counts for a commercial duration."""
    seconds = max(0, int(duration_seconds or 0))
    if seconds <= 10:
        minimum, recommended, classes = 1, 3, _DURATION_BANDS[0][3]
        profile = "10s"
    elif seconds <= 30:
        minimum, recommended, classes = 2, 6, _DURATION_BANDS[1][3]
        profile = "30s"
    else:
        minimum, recommended, classes = 3, 10, _DURATION_BANDS[2][3]
        profile = "60s"
    return {
        "duration_profile": profile,
        "duration_seconds": seconds,
        "minimum_image_count": minimum,
        "recommended_image_count": recommended,
        "preferred_asset_classes": list(classes),
    }


def build_asset_requirements(
    *,
    duration_seconds: int | float,
    confirmed_classes: list[str],
    gap_fill: str = "none",
    user_confirmed_shortage: bool = False,
) -> dict[str, Any]:
    """Build ``asset_requirements`` after user confirms classes (no vision)."""
    profile = duration_profile(duration_seconds)
    counts = Counter(c for c in confirmed_classes if c)
    available = sum(counts.values())
    preferred = list(profile["preferred_asset_classes"])
    missing = [c for c in preferred if counts.get(c, 0) < 1]
    has_hero = counts.get("product_hero", 0) > 0

    if not has_hero:
        status_zh = "等待用户选择"
        warning = "缺少商品主图或核心参考，须补图、图生图或改为概念片后再出表 3。"
    elif available < int(profile["minimum_image_count"]):
        status_zh = "降级继续"
        warning = "图片数量低于最低可运行建议，商品一致性与镜头丰富度可能下降。"
    elif missing or available < int(profile["recommended_image_count"]):
        status_zh = "降级继续"
        warning = "图片数量或类型低于建议，商品一致性与镜头丰富度可能下降。"
    else:
        status_zh = "就绪"
        warning = ""

    return {
        **profile,
        "available_image_count": available,
        "available_asset_classes": sorted(counts.keys()),
        "missing_asset_classes": missing,
        "counts_by_class": dict(counts),
        "status": status_zh,
        "fallback": gap_fill,
        "quality_warning": warning,
        "user_confirmed_shortage": bool(user_confirmed_shortage),
    }


def build_asset_ledger(
    *,
    project_id: str,
    precheck: dict[str, Any],
    user_classes: dict[str, str],
    duration_seconds: int | float = 0,
    gap_fill: str = "none",
    identity_anchor_path: str = "",
    confirmed_at: str = "",
    entry_metadata: dict[str, dict[str, Any]] | None = None,
    planned_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge scan facts with user-confirmed classes into ``asset_ledger``."""
    metadata_by_path = entry_metadata if isinstance(entry_metadata, dict) else {}
    entries_out: list[dict[str, Any]] = []
    confirmed: list[str] = []
    for entry in precheck.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        user_class = str(
            user_classes.get(path)
            or user_classes.get(str(entry.get("file") or ""))
            or entry.get("user_class")
            or entry.get("suggested_class")
            or ""
        ).strip()
        if not user_class:
            continue
        is_anchor = bool(
            identity_anchor_path
            and (path == identity_anchor_path or entry.get("file") == identity_anchor_path)
        )
        row = deepcopy(entry)
        metadata = (
            metadata_by_path.get(path)
            or metadata_by_path.get(str(entry.get("file") or ""))
            or {}
        )
        if isinstance(metadata, dict):
            for key in _ENTRY_METADATA_FIELDS:
                if key in metadata:
                    row[key] = deepcopy(metadata[key])
        row = {
            **row,
            "user_class": user_class,
            "status": "identity_anchor" if is_anchor else "confirmed",
            "is_identity_anchor": is_anchor,
        }
        entries_out.append(row)
        confirmed.append(user_class)

    requirements = build_asset_requirements(
        duration_seconds=duration_seconds,
        confirmed_classes=confirmed,
        gap_fill=gap_fill,
        user_confirmed_shortage=gap_fill != "none",
    )
    ledger = {
        "version": "1.0",
        "project_id": project_id,
        "confirmed_at": confirmed_at,
        "gap_fill": gap_fill,
        "entries": entries_out,
        "summary": {
            "available_image_count": len(entries_out),
            "counts_by_class": dict(Counter(confirmed)),
            "missing_asset_classes": requirements.get("missing_asset_classes") or [],
            "status_zh": requirements.get("status") or "等待用户选择",
            "quality_warning": requirements.get("quality_warning") or "",
        },
        "asset_requirements": requirements,
    }
    if planned_entries is not None:
        ledger["planned_entries"] = [
            deepcopy(entry)
            for entry in planned_entries
            if isinstance(entry, dict)
        ]
    return ledger

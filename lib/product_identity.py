"""Product identity manifests and approval-aware asset access.

The manifest is the identity contract for ecommerce generation. It records the
visual anchor, non-negotiable product constraints, and the image/video assets
that a human has approved for downstream generation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from lib.paths import REPO_ROOT

APPROVED_STATUSES = frozenset({"approved", "satisfied"})


class ManifestValidationError(ValueError):
    """Raised when a product manifest cannot be used safely."""


def _resolve_path(raw_path: str, repo_root: Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (repo_root / path).resolve()


@dataclass
class ProductManifest:
    """Validated product identity data loaded from ``identity_anchor.json``."""

    data: dict[str, Any]
    source_path: Path | None = None
    repo_root: Path = field(default_factory=lambda: REPO_ROOT)

    @property
    def product_id(self) -> str:
        return str(self.data.get("product_id") or "")

    @property
    def product_name(self) -> str:
        return str(self.data.get("product_name") or "")

    @property
    def identity_anchor(self) -> dict[str, Any]:
        value = self.data.get("identity_anchor")
        return value if isinstance(value, dict) else {}

    def resolve_asset_path(self, raw_path: str) -> Path:
        return _resolve_path(raw_path, self.repo_root)

    def _approved_entries(self, key: str, *, existing_only: bool) -> list[dict[str, Any]]:
        entries = self.data.get(key) or []
        if not isinstance(entries, list):
            return []
        approved: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("status") not in APPROVED_STATUSES:
                continue
            raw_path = entry.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            if existing_only and not self.resolve_asset_path(raw_path).is_file():
                continue
            approved.append(dict(entry))
        return approved

    def get_approved_i2i_images(self, *, existing_only: bool = True) -> list[dict[str, Any]]:
        """Return approved I2I references, optionally requiring files on disk."""
        return self._approved_entries("i2i_candidates", existing_only=existing_only)

    def get_approved_i2v_candidates(self, *, existing_only: bool = True) -> list[dict[str, Any]]:
        """Return approved I2V clips, optionally requiring files on disk."""
        return self._approved_entries("i2v_candidates", existing_only=existing_only)

    def validate_anchor(self, *, check_files: bool = True) -> None:
        """Validate required identity fields and approved asset references.

        ``check_files=False`` is useful when creating a manifest before assets
        exist. Production loading should keep the default ``True``.
        """
        errors: list[str] = []
        if not self.product_id:
            errors.append("product_id must be a non-empty string")
        if not self.product_name:
            errors.append("product_name must be a non-empty string")

        anchor = self.identity_anchor
        if not anchor.get("primary_color"):
            errors.append("identity_anchor.primary_color is required")
        for key in ("forbidden_changes", "geometry_constraints"):
            value = anchor.get(key)
            if not isinstance(value, list) or not value:
                errors.append(f"identity_anchor.{key} must be a non-empty list")

        references = self.data.get("reference_images")
        if not isinstance(references, list) or not references:
            errors.append("reference_images must contain at least one entry")

        for key in ("reference_images", "i2i_candidates", "i2v_candidates"):
            entries = self.data.get(key) or []
            if not isinstance(entries, list):
                errors.append(f"{key} must be a list")
                continue
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    errors.append(f"{key}[{index}] must be an object")
                    continue
                raw_path = entry.get("path")
                if not isinstance(raw_path, str) or not raw_path.strip():
                    errors.append(f"{key}[{index}].path must be a non-empty string")
                elif check_files and not self.resolve_asset_path(raw_path).is_file():
                    errors.append(f"{key}[{index}] asset does not exist: {raw_path}")

        if not self.get_approved_i2i_images(existing_only=False):
            errors.append("at least one approved I2I candidate is required")
        if not self.get_approved_i2v_candidates(existing_only=False):
            errors.append("at least one approved I2V candidate is required")

        if errors:
            raise ManifestValidationError("; ".join(errors))

    def to_dict(self) -> dict[str, Any]:
        return self.data


def load_manifest(
    path: str | Path,
    *,
    repo_root: str | Path | None = None,
    check_files: bool = True,
) -> ProductManifest:
    """Load and validate a product identity manifest from JSON."""
    manifest_path = Path(path).resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ManifestValidationError("manifest root must be a JSON object")
    manifest = ProductManifest(
        data=data,
        source_path=manifest_path,
        repo_root=Path(repo_root).resolve() if repo_root else REPO_ROOT,
    )
    manifest.validate_anchor(check_files=check_files)
    return manifest


def save_manifest(manifest: ProductManifest, path: str | Path | None = None) -> Path:
    """Validate and persist a product manifest."""
    target = Path(path or manifest.source_path or "").resolve()
    if not str(target):
        raise ValueError("path is required when manifest.source_path is unset")
    manifest.validate_anchor(check_files=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def validate_anchor(
    manifest: ProductManifest | dict[str, Any],
    *,
    repo_root: str | Path | None = None,
    check_files: bool = True,
) -> None:
    """Validate a loaded manifest or raw manifest dictionary."""
    if isinstance(manifest, ProductManifest):
        manifest.validate_anchor(check_files=check_files)
        return
    ProductManifest(
        data=manifest,
        repo_root=Path(repo_root).resolve() if repo_root else REPO_ROOT,
    ).validate_anchor(check_files=check_files)


def get_approved_i2i_images(
    manifest: ProductManifest,
    *,
    existing_only: bool = True,
) -> list[dict[str, Any]]:
    return manifest.get_approved_i2i_images(existing_only=existing_only)


def get_approved_i2v_candidates(
    manifest: ProductManifest,
    *,
    existing_only: bool = True,
) -> list[dict[str, Any]]:
    return manifest.get_approved_i2v_candidates(existing_only=existing_only)

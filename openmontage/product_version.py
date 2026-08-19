"""Product version derived from the release manifest."""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any


DIST_NAME = "openmontage"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _default_release_manifest() -> Path:
    # Lazy import: openmontage/__init__ loads this module before MCP is ready.
    from lib.resources import get_resources

    return get_resources().release_manifest()


try:
    RELEASE_MANIFEST = _default_release_manifest()
except Exception:
    RELEASE_MANIFEST = (
        REPO_ROOT / "distribution" / "manifests" / "release-manifest.json"
    )


def load_release_manifest(path: Path | None = None) -> dict[str, Any]:
    target = path or RELEASE_MANIFEST
    data = json.loads(target.read_text(encoding="utf-8"))
    version = str(data.get("version") or "").strip()
    if not version:
        raise RuntimeError(f"release manifest has no version: {target}")
    return data


def get_product_version() -> str:
    if RELEASE_MANIFEST.is_file():
        return str(load_release_manifest()["version"])
    try:
        return distribution_version(DIST_NAME)
    except PackageNotFoundError as exc:
        raise RuntimeError(
            "OpenMontage version is unavailable: no release manifest or "
            f"installed {DIST_NAME!r} distribution metadata"
        ) from exc


PRODUCT_VERSION = get_product_version()

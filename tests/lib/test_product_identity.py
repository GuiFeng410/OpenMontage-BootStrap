"""Tests for product identity manifests without cloud calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.product_identity import (
    ManifestValidationError,
    load_manifest,
    save_manifest,
)


def _manifest(root: Path) -> dict:
    image = root / "anchor.png"
    clip = root / "candidate.mp4"
    image.write_bytes(b"image")
    clip.write_bytes(b"video")
    return {
        "product_id": "demo-bangle",
        "product_name": "Demo bangle",
        "identity_anchor": {
            "primary_color": "pale icy-green",
            "forbidden_changes": ["deep emerald drift"],
            "geometry_constraints": ["closed ring"],
        },
        "reference_images": [{"path": "anchor.png", "status": "approved"}],
        "i2i_candidates": [{"path": "anchor.png", "status": "approved"}],
        "i2v_candidates": [{"path": "candidate.mp4", "status": "satisfied"}],
    }


def test_load_manifest_validates_and_filters_approved_assets(tmp_path: Path):
    path = tmp_path / "identity_anchor.json"
    path.write_text(json.dumps(_manifest(tmp_path)), encoding="utf-8")

    manifest = load_manifest(path, repo_root=tmp_path)

    assert manifest.product_id == "demo-bangle"
    assert [item["path"] for item in manifest.get_approved_i2i_images()] == ["anchor.png"]
    assert [item["path"] for item in manifest.get_approved_i2v_candidates()] == ["candidate.mp4"]


def test_unapproved_or_missing_assets_are_not_promoted(tmp_path: Path):
    data = _manifest(tmp_path)
    data["i2i_candidates"].append({"path": "missing.png", "status": "pending"})
    path = tmp_path / "identity_anchor.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    manifest = load_manifest(path, repo_root=tmp_path)

    assert len(manifest.get_approved_i2i_images()) == 1
    assert manifest.get_approved_i2i_images(existing_only=False)[0]["path"] == "anchor.png"


def test_invalid_manifest_fails_before_generation(tmp_path: Path):
    data = _manifest(tmp_path)
    data["identity_anchor"]["primary_color"] = ""
    path = tmp_path / "identity_anchor.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="primary_color"):
        load_manifest(path, repo_root=tmp_path)


def test_save_manifest_round_trips(tmp_path: Path):
    source = tmp_path / "source.json"
    target = tmp_path / "nested" / "saved.json"
    source.write_text(json.dumps(_manifest(tmp_path)), encoding="utf-8")
    manifest = load_manifest(source, repo_root=tmp_path)

    saved = save_manifest(manifest, target)

    assert saved == target.resolve()
    assert json.loads(target.read_text(encoding="utf-8"))["product_id"] == "demo-bangle"

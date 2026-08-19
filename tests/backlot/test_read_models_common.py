"""Focused tests for shared Backlot read-model path helpers."""

from __future__ import annotations

from backlot.read_models.common import (
    canonical_video_path,
    rel,
    resolve_asset_path,
)


def test_rel_returns_project_relative_posix_path(tmp_path) -> None:
    path = tmp_path / "assets" / "images" / "a.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x")

    assert rel(tmp_path, path) == "assets/images/a.png"


def test_resolve_asset_path_returns_none_for_missing_candidate(tmp_path) -> None:
    assert resolve_asset_path(tmp_path, "../outside.png") is None


def test_canonical_video_path_rejects_non_video(tmp_path) -> None:
    assert canonical_video_path(tmp_path, "assets/images/a.png") is None

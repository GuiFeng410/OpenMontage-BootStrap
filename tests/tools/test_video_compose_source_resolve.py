"""Resolve project-relative cuts[].source without requiring a full Remotion path."""

from __future__ import annotations

from pathlib import Path

from tools.video.video_compose import infer_project_root, resolve_cut_source, VideoCompose


def test_resolve_relative_under_project_root(tmp_path):
    video_dir = tmp_path / "assets" / "video"
    video_dir.mkdir(parents=True)
    clip = video_dir / "seg_beat_01.mp4"
    clip.write_bytes(b"fake")
    resolved = resolve_cut_source("assets/video/seg_beat_01.mp4", project_root=tmp_path)
    assert Path(resolved) == clip.resolve()


def test_resolve_asset_id_then_relative_path(tmp_path):
    clip = tmp_path / "assets" / "video" / "a.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"fake")
    lookup = {"clip-a": {"id": "clip-a", "path": "assets/video/a.mp4"}}
    resolved = resolve_cut_source("clip-a", project_root=tmp_path, asset_lookup=lookup)
    assert Path(resolved) == clip.resolve()


def test_resolve_absolute_unchanged(tmp_path):
    clip = tmp_path / "abs.mp4"
    clip.write_bytes(b"x")
    assert resolve_cut_source(str(clip), project_root=tmp_path / "other") == str(clip)


def test_infer_project_root_from_inputs(tmp_path):
    assert infer_project_root({"project_root": str(tmp_path)}, {}) == tmp_path.resolve()


def test_ffmpeg_compose_accepts_relative_cut(tmp_path, monkeypatch):
    """Missing renderer_family is allowed for ffmpeg; relative source is found."""
    import shutil

    import pytest

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    import subprocess

    video_dir = tmp_path / "assets" / "video"
    video_dir.mkdir(parents=True)
    src = video_dir / "seg_beat_01.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=teal:s=320x240:d=1:r=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src),
        ],
        capture_output=True,
        check=True,
    )
    out = tmp_path / "renders" / "final.mp4"
    out.parent.mkdir()
    result = VideoCompose().execute(
        {
            "operation": "render",
            "project_root": str(tmp_path),
            "output_path": str(out),
            "edit_decisions": {
                "version": "1.0",
                "project_id": "demo",
                "render_runtime": "ffmpeg",
                "cuts": [
                    {
                        "id": "c1",
                        "source": "assets/video/seg_beat_01.mp4",
                        "in_seconds": 0,
                        "out_seconds": 1,
                    }
                ],
            },
            "asset_manifest": {"assets": []},
        }
    )
    assert result.success, result.error
    assert out.exists()

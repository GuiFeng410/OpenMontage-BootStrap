"""Tests for Remotion public/ asset staging in video_compose."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.video.video_compose import VideoCompose  # noqa: E402


@pytest.fixture
def tool():
    return VideoCompose()


def test_stage_remotion_public_assets_rewrites_cut_and_audio_paths(tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    composer_dir = tmp_path / "remotion-composer"
    public_dir = composer_dir / "public"
    public_dir.mkdir(parents=True)

    project_root = tmp_path / "projects" / "demo-project"
    img = project_root / "assets" / "images" / "scene01.png"
    audio = project_root / "assets" / "audio" / "narration.wav"
    img.parent.mkdir(parents=True)
    audio.parent.mkdir(parents=True)
    img.write_bytes(b"png")
    audio.write_bytes(b"wav")

    props = {
        "project_id": "demo-project",
        "cuts": [{"id": "c1", "source": "assets/images/scene01.png"}],
        "audio": {"narration": {"src": "assets/audio/narration.wav"}},
    }

    tool._stage_remotion_public_assets(props, composer_dir, project_root)

    assert props["cuts"][0]["source"] == "demo-project/scene01.png"
    assert props["audio"]["narration"]["src"] == "demo-project/narration.wav"
    assert (public_dir / "demo-project" / "scene01.png").exists()
    assert (public_dir / "demo-project" / "narration.wav").exists()

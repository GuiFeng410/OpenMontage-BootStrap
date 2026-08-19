"""Focused characterization tests for the commercial board read model."""

from __future__ import annotations

from pathlib import Path

import pytest

from backlot import state as state_mod
from backlot.read_models.commercial import build_commercial_board
from backlot.state import load_board_state
from tests.backlot.test_state import _make_six_beat_legacy_assignment_project


REQUIRED_COMMERCIAL_KEYS = {
    "beats",
    "decision",
    "brief_summary",
    "stage_evidence",
}
EXPECTED_COMMERCIAL_STAGES = [
    "brief_locked",
    "assets_gate",
    "sample_review",
    "segment_build",
    "draft_review",
    "final_compose",
    "delivery_signoff",
]
SIX_BEAT_COUNT = 6


def test_commercial_builder_is_importable() -> None:
    assert callable(build_commercial_board)


@pytest.fixture
def projects_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(state_mod, "PROJECTS_DIR", root)
    return root


def _project_files(project: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }


def test_six_beat_commercial_projection_keeps_stable_contract(
    projects_root: Path,
) -> None:
    project = _make_six_beat_legacy_assignment_project(projects_root)

    state = load_board_state(project)
    commercial = state["commercial"]

    assert REQUIRED_COMMERCIAL_KEYS <= set(commercial)
    assert len(commercial["beats"]) == SIX_BEAT_COUNT
    assert [stage["name"] for stage in state["stages"]] == EXPECTED_COMMERCIAL_STAGES


def test_loading_commercial_projection_does_not_write_project_files(
    projects_root: Path,
) -> None:
    project = _make_six_beat_legacy_assignment_project(projects_root)
    before = _project_files(project)

    load_board_state(project)

    assert _project_files(project) == before

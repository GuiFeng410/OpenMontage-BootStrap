"""lock_production_profile use case: persist tier without MCP or generate."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.application.create_project import create_project
from lib.application.errors import ApplicationError
from lib.application.lock_production_profile import lock_production_profile
from lib.application.read_project_snapshot import read_project_snapshot
from lib.error_codes import BAD_REQUEST, NOT_FOUND


def test_missing_marker_raises_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    (tmp_path / "projects" / "empty-dir").mkdir(parents=True)
    with pytest.raises(ApplicationError) as caught:
        lock_production_profile("empty-dir", "light")
    assert caught.value.code == NOT_FOUND
    assert "marker missing" in caught.value.message


def test_missing_project_raises_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    with pytest.raises(ApplicationError) as caught:
        lock_production_profile("no-such", "light")
    assert caught.value.code == NOT_FOUND
    assert caught.value.message == "Project not found: no-such"


def test_lock_light_updates_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    create_project(
        title="Lock Light",
        pipeline_type="bootstrap-commercial",
        requested_project_id="lock-light",
    )
    result = lock_production_profile("lock-light", "light")
    assert result["production_profile"]["production_tier"] == "light"
    assert result["production_profile"]["visual_source"] == "template"
    assert result["production_profile"]["tts_source"] == "edge_tts"
    snapshot = read_project_snapshot("lock-light")
    assert snapshot["production_profile"]["production_tier"] == "light"


def test_invalid_tier_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    create_project(
        title="Bad Tier",
        pipeline_type="bootstrap-commercial",
        requested_project_id="bad-tier",
    )
    with pytest.raises(ApplicationError) as caught:
        lock_production_profile("bad-tier", "ultra")
    assert caught.value.code == BAD_REQUEST
    assert "production_tier" in caught.value.message

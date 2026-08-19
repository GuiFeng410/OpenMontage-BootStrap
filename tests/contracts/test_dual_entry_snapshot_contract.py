"""Shared-state contract for chat, Python board, and HTTP board entry points."""

from __future__ import annotations

import json
from pathlib import Path

import backlot.server as server_mod
import lib.checkpoint as checkpoint_lib
import pytest
from backlot import state as state_mod
from backlot.server import create_app
from backlot.state import load_board_state
from fastapi.testclient import TestClient
from openmontage.mcp.bootstrap.tools import produce_read_state
from tests.contracts.test_phase0_contracts import sample_artifact


PROJECT_ID = "dual-entry-smoke"
COMMON_PROFILE_KEYS = ("production_tier", "duration_seconds")


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )


def _seed_project(root: Path) -> Path:
    project = root / PROJECT_ID
    (project / "artifacts").mkdir(parents=True)
    (project / "assets" / "images").mkdir(parents=True)
    (project / "renders").mkdir()
    profile = {
        "production_tier": "light",
        "review_mode_preset": "minimal",
        "duration_seconds": 15,
    }
    _write(
        project / "project.json",
        {
            "project_id": PROJECT_ID,
            "title": "双入口烟测",
            "pipeline_type": "bootstrap-commercial",
            "production_profile": profile,
        },
    )
    _write(
        project / "checkpoint_brief_locked.json",
        {
            "version": "1.0",
            "project_id": PROJECT_ID,
            "pipeline_type": "bootstrap-commercial",
            "stage": "brief_locked",
            "status": "awaiting_human",
            "timestamp": "2026-08-19T00:00:00+00:00",
            "checkpoint_policy": "guided",
            "human_approval_required": True,
            "human_approved": False,
            "artifacts": {
                "brief": {
                    "theme": "双入口测试商品片",
                    "duration_seconds": 15,
                    "images": {},
                }
            },
        },
    )
    return project


def _seed_framework_project(
    root: Path,
    project_id: str,
    *,
    current_status: str,
    research_completed: bool = False,
) -> Path:
    project = root / project_id
    (project / "artifacts").mkdir(parents=True)
    (project / "assets" / "images").mkdir(parents=True)
    (project / "renders").mkdir()
    _write(
        project / "project.json",
        {
            "project_id": project_id,
            "title": project_id,
            "pipeline_type": "framework-smoke",
        },
    )
    if research_completed:
        checkpoint_lib.write_checkpoint(
            root,
            project_id,
            "research",
            "completed",
            artifacts={"research_brief": sample_artifact("research_brief")},
            pipeline_type="framework-smoke",
            human_approved=True,
        )
        checkpoint_lib.write_checkpoint(
            root,
            project_id,
            "script",
            current_status,
            artifacts={"script": sample_artifact("script")},
            pipeline_type="framework-smoke",
        )
    else:
        checkpoint_lib.write_checkpoint(
            root,
            project_id,
            "research",
            current_status,
            artifacts={},
            pipeline_type="framework-smoke",
        )
    return project


def _completed_stages(board: dict) -> list[str]:
    return [
        stage["name"]
        for stage in board["stages"]
        if stage.get("status") == "completed"
    ]


def _current_stage(board: dict) -> str | None:
    awaiting = next(
        (
            stage["name"]
            for stage in board["stages"]
            if stage.get("status") == "awaiting_human"
        ),
        None,
    )
    return awaiting or next(
        (
            stage["name"]
            for stage in board["stages"]
            if stage.get("status") in {"pending", "in_progress", "failed"}
        ),
        None,
    )


def _configure_roots(root: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(root))
    monkeypatch.setattr(state_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(server_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(checkpoint_lib, "PROJECTS_DIR", root)


def _load_entry_states(project_id: str, project: Path) -> tuple[dict, dict, dict]:
    mcp_state = produce_read_state(project_id)
    board_state = load_board_state(project)
    with TestClient(create_app()) as client:
        response = client.get(f"/api/project/{project_id}/state")
    assert response.status_code == 200
    return mcp_state, board_state, response.json()


def _assert_shared_progress(mcp_state: dict, board_state: dict, http_state: dict) -> None:
    assert mcp_state["project_id"] == board_state["project_id"]
    assert (
        mcp_state["marker"]["pipeline_type"]
        == board_state["pipeline"]["pipeline_type"]
    )
    mcp_profile = mcp_state.get("production_profile") or {}
    board_profile = board_state.get("production_profile") or {}
    for key in COMMON_PROFILE_KEYS:
        if key in mcp_profile and key in board_profile:
            assert mcp_profile[key] == board_profile[key]
    assert mcp_state["completed_stages"] == _completed_stages(board_state)
    assert mcp_state["next_stage"] == _current_stage(board_state)
    assert http_state["project_id"] == board_state["project_id"]
    assert http_state["stages"] == board_state["stages"]


def test_chat_python_and_http_states_share_project_progress(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    project = _seed_project(root)
    _configure_roots(root, monkeypatch)

    states = _load_entry_states(PROJECT_ID, project)

    _assert_shared_progress(*states)


def test_completed_stage_and_current_awaiting_match_across_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    project_id = "dual-entry-completed-awaiting"
    project = _seed_framework_project(
        root,
        project_id,
        current_status="awaiting_human",
        research_completed=True,
    )
    _configure_roots(root, monkeypatch)

    mcp_state, board_state, http_state = _load_entry_states(project_id, project)

    _assert_shared_progress(mcp_state, board_state, http_state)
    assert mcp_state["completed_stages"] == ["research"]
    assert mcp_state["next_stage"] == "script"
    assert mcp_state["latest_checkpoint_status"] == "awaiting_human"


@pytest.mark.parametrize("current_status", ["in_progress", "failed"])
def test_incomplete_current_stage_matches_across_entries(
    tmp_path: Path,
    monkeypatch,
    current_status: str,
) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    project_id = f"dual-entry-{current_status}"
    project = _seed_framework_project(
        root,
        project_id,
        current_status=current_status,
    )
    _configure_roots(root, monkeypatch)

    mcp_state, board_state, http_state = _load_entry_states(project_id, project)

    _assert_shared_progress(mcp_state, board_state, http_state)
    assert mcp_state["completed_stages"] == []
    assert mcp_state["next_stage"] == "research"
    assert mcp_state["latest_checkpoint_status"] == current_status

"""Chat and board write paths share application use cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import lib.board_runner as board_runner
import lib.checkpoint as checkpoint_lib
import lib.interaction_intents as intents
import lib.project_export as project_export
from lib.application import (
    approve_stage,
    create_project,
    export_project,
    lock_production_profile,
    read_project_snapshot,
    sync_production_job,
)
from lib.checkpoint import read_checkpoint
from lib.install_state import snapshot_install_state
from lib.library_create import create_library_project
from lib.paths import REPO_ROOT
from openmontage.mcp.bootstrap.tools import list_bootstrap_tools
from tests.lib.test_approve_stage import _brief_locked_artifacts
from tests.lib.test_project_export import _export_intent


REQUIRED_PRODUCE_NAMES = {
    "produce_init_project",
    "produce_read_state",
    "produce_set_production_profile",
    "produce_approve_checkpoint",
    "produce_apply_project_export",
    "produce_runner_tick",
}

KERNEL_MARKER_KEYS = ("pipeline_type", "title")


def _configure_workspace(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(root))
    monkeypatch.setattr(checkpoint_lib, "PROJECTS_DIR", root)
    monkeypatch.setattr(intents, "PROJECTS_DIR", root)
    monkeypatch.setattr(project_export, "PROJECTS_DIR", root)
    monkeypatch.setattr(board_runner, "PROJECTS_DIR", root)
    monkeypatch.setattr("backlot.runner.stop_runner", lambda **_k: True)


def test_create_project_and_library_share_kernel_marker_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "projects"
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(root))
    snapshot_install_state(repo_root=tmp_path, verify_ready=False)

    chat = create_project(
        title="Jade Bangle",
        pipeline_type="bootstrap-commercial",
        requested_project_id="jade-bangle",
    )
    board = create_library_project(title="Jade Bangle", repo_root=tmp_path)

    chat_marker = json.loads(
        (root / chat["project_id"] / "project.json").read_text(encoding="utf-8")
    )
    board_marker = json.loads(
        (root / board["project_id"] / "project.json").read_text(encoding="utf-8")
    )
    for key in KERNEL_MARKER_KEYS:
        assert key in chat_marker
        assert key in board_marker
    assert chat_marker["pipeline_type"] == board_marker["pipeline_type"] == "bootstrap-commercial"
    assert chat_marker["title"] == board_marker["title"] == "Jade Bangle"


def test_approve_stage_and_runner_complete_same_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "projects"
    _configure_workspace(root, monkeypatch)
    artifacts = _brief_locked_artifacts()
    create_project(
        title="Chat Approve",
        pipeline_type="bootstrap-commercial",
        requested_project_id="chat-approve",
    )
    create_project(
        title="Board Approve",
        pipeline_type="bootstrap-commercial",
        requested_project_id="board-approve",
    )

    chat = approve_stage(
        "chat-approve",
        "brief_locked",
        "用户确认方案",
        artifacts=artifacts,
        pipeline_type="bootstrap-commercial",
    )
    board_runner._complete_brief_locked("board-approve", artifacts)

    chat_ckpt = read_checkpoint(root, "chat-approve", "brief_locked")
    board_ckpt = read_checkpoint(root, "board-approve", "brief_locked")
    assert chat["status"] == "completed"
    assert chat_ckpt["status"] == board_ckpt["status"] == "completed"
    assert chat_ckpt["human_approved"] is True
    assert board_ckpt["human_approved"] is True


def test_export_project_and_runner_consume_complete_the_same_way(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "projects"
    _configure_workspace(root, monkeypatch)
    for project_id in ("chat-export", "board-export"):
        create_project(
            title=project_id,
            pipeline_type="bootstrap-commercial",
            requested_project_id=project_id,
        )
        renders = root / project_id / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        (renders / "final.mp4").write_bytes(b"film")

    chat = export_project("chat-export", confirm_phrase="结束导出")
    intents.create_or_conflict("board-export", _export_intent("board-export"))
    pending = [
        json.loads(
            (root / "board-export" / "intents" / "export-001.json").read_text(
                encoding="utf-8"
            )
        )
    ]
    board = board_runner._consume_export("board-export", pending)

    assert chat["ok"] is True
    assert board is not None and board["ok"] is True
    for project_id in ("chat-export", "board-export"):
        marker = json.loads(
            (root / project_id / "project.json").read_text(encoding="utf-8")
        )
        assert marker["lifecycle_status"] == "completed"
        assert (root / project_id / "exports" / "final.mp4").is_file()


def test_bootstrap_produce_tool_names_remain_stable() -> None:
    names = set(list_bootstrap_tools()["produce_minimal"])
    assert REQUIRED_PRODUCE_NAMES <= names


def test_application_use_cases_are_importable() -> None:
    assert callable(create_project)
    assert callable(read_project_snapshot)
    assert callable(lock_production_profile)
    assert callable(approve_stage)
    assert callable(sync_production_job)
    assert callable(export_project)


def test_produce_and_checkpoint_modules_remain_facades() -> None:
    produce_src = (
        REPO_ROOT / "src" / "openmontage" / "lib" / "board_produce.py"
    ).read_text(encoding="utf-8")
    checkpoint_src = (
        REPO_ROOT / "src" / "openmontage" / "lib" / "checkpoint.py"
    ).read_text(encoding="utf-8")
    doctor_src = (
        REPO_ROOT / "src" / "openmontage" / "mcp" / "doctor" / "tools.py"
    ).read_text(encoding="utf-8")
    bootstrap_src = (
        REPO_ROOT / "src" / "openmontage" / "mcp" / "bootstrap" / "tools.py"
    ).read_text(encoding="utf-8")
    library_src = (
        REPO_ROOT / "src" / "openmontage" / "lib" / "library_create.py"
    ).read_text(encoding="utf-8")

    assert "lib.produce" in produce_src
    assert "checkpoint_store" in checkpoint_src
    assert "from lib.application.create_project import create_project" in doctor_src
    assert "from lib.application.approve_stage import approve_stage" in doctor_src
    assert "from lib.application.lock_production_profile import lock_production_profile" in doctor_src
    assert "from lib.application.export_project import export_project" in bootstrap_src
    assert "openmontage.mcp" not in library_src

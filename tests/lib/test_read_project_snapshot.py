"""read_project_snapshot use case: chat-shaped progress without MCP imports."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from lib.application.read_project_snapshot import ApplicationError, read_project_snapshot
from lib.error_codes import NOT_FOUND

_APPLICATION_ROOT = (
    Path(__file__).resolve().parents[2] / "src" / "openmontage" / "lib" / "application"
)
_FORBIDDEN_IMPORT_PREFIXES = ("openmontage.mcp", "backlot.server")
_SNAPSHOT_KEYS = (
    "project_id",
    "project_dir",
    "marker",
    "production_profile",
    "completed_stages",
    "next_stage",
    "awaiting_human",
    "latest_checkpoint_stage",
    "latest_checkpoint_status",
)
_PROJECT_ID = "snapshot-demo"


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _seed_awaiting_project(root: Path) -> Path:
    project = root / _PROJECT_ID
    (project / "artifacts").mkdir(parents=True)
    profile = {
        "production_tier": "light",
        "review_mode_preset": "minimal",
        "duration_seconds": 15,
    }
    _write(
        project / "project.json",
        {
            "project_id": _PROJECT_ID,
            "title": "快照测",
            "pipeline_type": "bootstrap-commercial",
            "production_profile": profile,
        },
    )
    _write(
        project / "checkpoint_brief_locked.json",
        {
            "version": "1.0",
            "project_id": _PROJECT_ID,
            "pipeline_type": "bootstrap-commercial",
            "stage": "brief_locked",
            "status": "awaiting_human",
            "timestamp": "2026-08-19T00:00:00+00:00",
            "checkpoint_policy": "guided",
            "human_approval_required": True,
            "human_approved": False,
            "artifacts": {
                "brief": {
                    "theme": "快照测试商品片",
                    "duration_seconds": 15,
                    "images": {},
                }
            },
        },
    )
    return project


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_application_package_does_not_import_mcp_or_backlot_server() -> None:
    for path in _APPLICATION_ROOT.rglob("*.py"):
        for name in _imported_modules(path):
            assert not name.startswith(_FORBIDDEN_IMPORT_PREFIXES), (
                f"{path.name} imports {name}"
            )


def test_missing_project_raises_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    with pytest.raises(ApplicationError) as caught:
        read_project_snapshot("missing-project")
    assert caught.value.code == NOT_FOUND
    assert caught.value.message == "Project not found: missing-project"


def test_awaiting_snapshot_matches_mcp_facade_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    project = _seed_awaiting_project(root)
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(root))

    snapshot = read_project_snapshot(_PROJECT_ID)
    from openmontage.mcp.doctor.tools import run_get_project_state

    facade = run_get_project_state(_PROJECT_ID)

    assert tuple(snapshot) == _SNAPSHOT_KEYS
    assert snapshot == facade
    assert snapshot["project_id"] == _PROJECT_ID
    assert Path(snapshot["project_dir"]).resolve() == project.resolve()
    assert snapshot["marker"]["pipeline_type"] == "bootstrap-commercial"
    assert snapshot["production_profile"]["production_tier"] == "light"
    assert snapshot["awaiting_human"] == {
        "stage": "brief_locked",
        "human_approval_required": True,
    }
    assert snapshot["latest_checkpoint_stage"] == "brief_locked"
    assert snapshot["latest_checkpoint_status"] == "awaiting_human"

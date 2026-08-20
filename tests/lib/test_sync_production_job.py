"""sync_production_job use case: same action as sync_produce, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.application.sync_production_job import sync_production_job
from lib.produce.orchestrator import sync_produce
from tests.lib.test_board_advance import _seed_minimal_ready_for_delivery, _write_project


def _stub_start(*_args, **_kwargs):
    return {"job_id": "compose-job-1", "output_path": "renders/final.mp4"}


def test_fake_compose_matches_sync_produce(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "projects"
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(root))
    _write_project(root, "via-case")
    _write_project(root, "via-orch")
    _seed_minimal_ready_for_delivery(root, "via-case")
    _seed_minimal_ready_for_delivery(root, "via-orch")

    via_use_case = sync_production_job("via-case", compose_start=_stub_start)
    orch_marker = json.loads(
        (root / "via-orch" / "project.json").read_text(encoding="utf-8")
    )
    via_orchestrator = sync_produce(
        "via-orch",
        orch_marker,
        projects_dir=root,
        compose_start=_stub_start,
    )
    assert via_use_case["action"] == via_orchestrator["action"] == "produce_start"
    assert via_use_case["status"] == via_orchestrator["status"]


def test_missing_marker_matches_empty_sync_produce(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(root))
    via_use_case = sync_production_job(
        "ghost",
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("no compose")
        ),
    )
    via_orchestrator = sync_produce(
        "ghost",
        {},
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("no compose")
        ),
    )
    assert via_use_case == via_orchestrator
    assert via_use_case == {"action": "", "status": ""}

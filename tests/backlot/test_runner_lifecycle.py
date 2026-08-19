"""Runner lock stamp: reuse live process only when code still matches."""

from __future__ import annotations

import os

import pytest

from backlot.runner import (
    RunnerBusyError,
    _STAMP_FILES,
    parse_lock,
    run_loop,
    runner_needs_restart,
    runner_should_exit,
    spawn_detached,
)
from backlot.__main__ import _spawn_runner
from lib.persistence.code_stamp import RUNNER_STAMP_MODULES


def test_parse_lock_accepts_legacy_pid():
    assert parse_lock("18596") == {"pid": 18596, "code_stamp": "", "project_id": ""}


def test_parse_lock_reads_json_stamp():
    raw = '{"pid": 12, "code_stamp": "lib/board_runner.py:1", "project_id": "demo"}'
    assert parse_lock(raw)["pid"] == 12
    assert parse_lock(raw)["code_stamp"] == "lib/board_runner.py:1"
    assert parse_lock(raw)["project_id"] == "demo"


def test_runner_stamp_covers_approval_bundle():
    assert "lib/approval_bundle.py" in _STAMP_FILES
    assert "backlot/read_models/commercial.py" in _STAMP_FILES
    assert _STAMP_FILES == RUNNER_STAMP_MODULES


def test_commercial_read_model_mtime_triggers_runner_restart(monkeypatch, tmp_path):
    for rel in RUNNER_STAMP_MODULES:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# stub\n", encoding="utf-8")
    monkeypatch.setattr("backlot.runner.REPO_ROOT", tmp_path)
    from backlot.runner import runner_code_stamp

    before = runner_code_stamp()
    commercial = tmp_path / "backlot" / "read_models" / "commercial.py"
    commercial.write_text("# stub\nchanged\n", encoding="utf-8")
    after = runner_code_stamp()
    assert "backlot/read_models/commercial.py" in after
    assert before != after
    monkeypatch.setattr("backlot.runner.runner_alive", lambda: True)
    monkeypatch.setattr(
        "backlot.runner.read_lock",
        lambda: {"pid": 1, "code_stamp": before, "project_id": "demo"},
    )
    assert runner_needs_restart() is True


def test_run_loop_defaults_projects_root(monkeypatch):
    monkeypatch.delenv("OPENMONTAGE_PROJECTS_DIR", raising=False)
    monkeypatch.setattr("backlot.runner.acquire_lock", lambda *_a, **_k: False)

    assert run_loop("demo") == 0
    assert os.environ["OPENMONTAGE_PROJECTS_DIR"].replace("\\", "/").endswith(
        "OpenMontage/projects"
    )


def test_run_loop_refuses_empty_project_id(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr("backlot.runner.acquire_lock", lambda *_a, **_k: called.__setitem__("n", 1) or True)
    assert run_loop("") == 0
    assert called["n"] == 0


def test_spawn_runner_reuses_when_stamp_matches(monkeypatch, tmp_path):
    spawned = {"n": 0}
    monkeypatch.setattr("backlot.runner.runner_alive", lambda: True)
    monkeypatch.setattr("backlot.runner.runner_needs_restart", lambda: False)
    monkeypatch.setattr("backlot.runner.active_project_id", lambda: "demo")
    monkeypatch.setattr("backlot.runner.log_path", lambda: tmp_path / "runner.log")
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *_a, **_k: spawned.__setitem__("n", spawned["n"] + 1),
    )
    _spawn_runner("demo")
    assert spawned["n"] == 0


def test_spawn_runner_restarts_when_stamp_mismatch(monkeypatch, tmp_path):
    calls = {"stop": 0, "spawn": 0}
    monkeypatch.setattr("backlot.runner.runner_alive", lambda: True)
    monkeypatch.setattr("backlot.runner.runner_needs_restart", lambda: True)
    monkeypatch.setattr("backlot.runner.active_project_id", lambda: "demo")
    monkeypatch.setattr(
        "backlot.runner.stop_runner",
        lambda **_k: calls.__setitem__("stop", 1),
    )
    monkeypatch.setattr("backlot.runner.log_path", lambda: tmp_path / "runner.log")
    monkeypatch.setattr("subprocess.Popen", lambda *_a, **_k: calls.__setitem__("spawn", 1))
    spawn_detached("demo")
    assert calls["stop"] == 1
    assert calls["spawn"] == 1


def test_spawn_runner_rejects_second_project(monkeypatch):
    monkeypatch.setattr("backlot.runner.runner_alive", lambda: True)
    monkeypatch.setattr("backlot.runner.runner_needs_restart", lambda: False)
    monkeypatch.setattr("backlot.runner.active_project_id", lambda: "other")
    with pytest.raises(RunnerBusyError) as caught:
        spawn_detached("demo")
    assert caught.value.active_project_id == "other"


def test_spawn_runner_ignores_empty_id(monkeypatch):
    spawned = {"n": 0}
    monkeypatch.setattr("subprocess.Popen", lambda *_a, **_k: spawned.__setitem__("n", 1))
    assert spawn_detached("") is None
    assert spawned["n"] == 0


def test_runner_needs_restart_when_legacy_lock_has_no_stamp(monkeypatch, tmp_path):
    lock = tmp_path / "runner.lock"
    lock.write_text("12345", encoding="utf-8")
    monkeypatch.setattr("backlot.runner.lock_path", lambda: lock)
    monkeypatch.setattr("backlot.runner.runner_alive", lambda: True)
    monkeypatch.setattr("backlot.runner.runner_code_stamp", lambda: "lib/board_runner.py:9")
    monkeypatch.setattr(
        "backlot.runner.read_lock",
        lambda: {"pid": 12345, "code_stamp": "", "project_id": ""},
    )
    assert runner_needs_restart() is True


def test_runner_should_exit_on_export_or_retry_exhausted():
    assert runner_should_exit({"projects": [{"phase": "exported"}]}) is True
    assert runner_should_exit({"projects": [{"retry_exhausted": True}]}) is True
    assert runner_should_exit({"projects": [{"phase": "idle"}]}) is False

"""Board runner consumes pending export intents without paid generate."""

from __future__ import annotations

import json
from pathlib import Path

import lib.approval_bundle as approval_bundle
import lib.board_advance as board_advance
import lib.board_runner as runner
import lib.interaction_intents as ii
import lib.project_export as pe
from tests.lib.test_project_export import _export_intent, _write_project


def _patch_projects(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(ii, "PROJECTS_DIR", root)
    monkeypatch.setattr(pe, "PROJECTS_DIR", root)
    monkeypatch.setattr(runner, "PROJECTS_DIR", root)
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(root))


def test_tick_exports_when_final_exists(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = _write_project(root)
    (project / "renders" / "final.mp4").write_bytes(b"film")
    _patch_projects(monkeypatch, root)
    ii.create_or_conflict("demo-pro", _export_intent())

    result = runner.tick("demo-pro", append_decision=lambda *_: {})
    assert result["phase"] == "exported"
    assert "project_export" in result["actions"]
    marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert marker["lifecycle_status"] == "completed"


def test_tick_seeds_stop_after_start_signal(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = _write_project(
        root,
        production_profile={
            "review_mode_preset": "minimal",
            "production_start_requested_at": "2026-08-18T00:00:00+00:00",
            "runner_start_pending": True,
        },
    )
    _patch_projects(monkeypatch, root)
    result = runner.tick("demo-pro", append_decision=lambda *_: {})
    assert "seed_stop" in result["actions"]
    assert "请在本页确认" in result["friendly_zh"]
    assert "回聊天" not in result["friendly_zh"]
    checkpoint = json.loads(
        (project / "checkpoint_brief_locked.json").read_text(encoding="utf-8")
    )
    options = checkpoint["metadata"]["decision_options"]
    assert all("recommended" not in item for item in options)


def test_tick_advances_to_next_stop_after_apply(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = _write_project(
        root,
        production_profile={
            "review_mode_preset": "minimal",
            "production_start_requested_at": "2026-08-18T00:00:00+00:00",
        },
    )
    _patch_projects(monkeypatch, root)
    board_advance.write_stop_card("demo-pro", "brief_locked", projects_dir=root)

    pending_once = [
        {"intent_type": "decision", "intent_id": "dec-1", "revision": "r1"}
    ]
    calls = {"n": 0}

    def fake_list(_project_id: str):
        calls["n"] += 1
        return pending_once if calls["n"] == 1 else []

    monkeypatch.setattr(runner, "_list_pending", fake_list)
    monkeypatch.setattr(
        runner,
        "_consume_decision",
        lambda *_args, **_kwargs: {
            "planned": {"intent": {"stage": "brief_locked"}},
            "applied": {"intent": {"stage": "brief_locked"}},
        },
    )
    result = runner.tick("demo-pro", append_decision=lambda *_: {})
    assert "approval_bundle" in result["actions"]
    assert "next_stop" in result["actions"]
    assert "seed_stop" not in result["actions"]
    assert "进入下一步" in result["friendly_zh"]
    assert "回聊天" not in result["friendly_zh"]
    overlay = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert overlay["board_stop"]["stage"] == "assets_gate"
    assert overlay["board_stop"]["needs_user_decision"] is True
    assert all(
        "recommended" not in item
        for item in overlay["board_stop"]["decision_options"]
    )


def test_tick_keeps_failure_on_page(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    _write_project(root)
    _patch_projects(monkeypatch, root)
    monkeypatch.setattr(
        runner,
        "_list_pending",
        lambda _pid: [
            {"intent_type": "decision", "intent_id": "dec-1", "revision": "r1"}
        ],
    )

    def boom(*_args, **_kwargs):
        raise approval_bundle.ApprovalBundleError(
            "blocked",
            code="blocked",
            safe_message="本机无法自动确认这笔选择。请留在本页，或点刷新重试。",
        )

    monkeypatch.setattr(runner, "_consume_decision", boom)
    result = runner.tick("demo-pro", append_decision=lambda *_: {})
    assert result["phase"] == "paused"
    assert "回聊天" not in result["friendly_zh"]
    assert "确认面板选择" not in (result.get("current_question") or "")


def test_runner_modules_do_not_call_paid_generate() -> None:
    runner_src = Path(runner.__file__).read_text(encoding="utf-8")
    advance_src = Path(board_advance.__file__).read_text(encoding="utf-8")
    from lib import board_gap_plan

    gap_src = Path(board_gap_plan.__file__).read_text(encoding="utf-8")
    for blob in (runner_src, advance_src, gap_src):
        assert "video_generate" not in blob
        assert "image_generate" not in blob
        assert "tts_generate" not in blob
        assert "stock_download" not in blob


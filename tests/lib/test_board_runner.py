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
    import lib.board_produce as board_produce

    monkeypatch.setattr(ii, "PROJECTS_DIR", root)
    monkeypatch.setattr(pe, "PROJECTS_DIR", root)
    monkeypatch.setattr(runner, "PROJECTS_DIR", root)
    monkeypatch.setattr(board_produce, "PROJECTS_DIR", root)
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(root))


def _stub_compose_start(_edit, _manifest, _output=""):
    return {"job_id": "compose-job-1", "output_path": "renders/final.mp4", "status": "queued"}


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
    assert "开始出片" in result["friendly_zh"]
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
    from lib import board_gap_plan, board_produce

    gap_src = Path(board_gap_plan.__file__).read_text(encoding="utf-8")
    produce_src = Path(board_produce.__file__).read_text(encoding="utf-8")
    for blob in (runner_src, advance_src, gap_src):
        assert "video_generate" not in blob
    for blob in (runner_src, advance_src, gap_src, produce_src):
        assert "image_generate" not in blob
        assert "tts_generate" not in blob
        assert "stock_download" not in blob
    assert "video_generate" in produce_src


def test_tick_recovers_stuck_brief_locked(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = _write_project(
        root,
        production_profile={
            "review_mode_preset": "minimal",
        },
    )
    _patch_projects(monkeypatch, root)
    from lib.checkpoint import merge_write_checkpoint

    merge_write_checkpoint(
        root,
        "demo-pro",
        "brief_locked",
        "in_progress",
        {},
        pipeline_type="bootstrap-commercial",
        human_approval_required=True,
        metadata_patch={"needs_user_decision": True},
    )
    art = project / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    for name, body in {
        "gap_plan": {"locked": True},
        "brief": {"theme": "手链", "duration_seconds": 25, "images": {}},
        "asset_precheck": {
            "version": "1.0",
            "entries": [],
            "summary": {
                "total_images": 1,
                "low_resolution_count": 0,
                "duplicate_group_count": 0,
                "needs_user_attention": False,
            },
        },
        "video_plan": {"segments": [{"id": "beat_01", "t": "0-10"}]},
        "segment_cards": {
            "version": "1.0",
            "duration_seconds": 25,
            "overall_prompt_zh": "商品片",
            "segments": [
                {
                    "beat": "beat_01",
                    "time": "00:00-00:10",
                    "copy_plan_zh": "卖点",
                    "shot_plan_zh": "推镜",
                    "asset_plan_zh": "主图",
                }
            ],
        },
    }.items():
        (art / f"{name}.json").write_text(
            json.dumps(body, ensure_ascii=False), encoding="utf-8"
        )
    intent_path = project / "intents" / "dec-applied.json"
    intent_path.parent.mkdir(parents=True, exist_ok=True)
    intent_path.write_text(
        json.dumps(
            {
                "version": "1.0",
                "intent_type": "approval_bundle",
                "intent_id": "dec-applied",
                "project_id": "demo-pro",
                "stage": "brief_locked",
                "revision": "r1",
                "summary": "applied",
                "summary_sha256": "abc",
                "payload": {
                    "theme": "手链",
                    "duration_seconds": 25.0,
                    "production_tier": "heavy",
                    "review_mode": "normal",
                    "provider": "agnes",
                    "model": "agnes-video-v2.0",
                    "runtime": "remotion",
                    "asset_strategy": "reuse-approved",
                    "allow_deterministic_reuse": True,
                    "max_generations": 2,
                    "unit_price_cny": 0.0,
                    "total_budget_cny": 0.0,
                    "resolution": "1080x1920",
                    "quality_target": "draft",
                    "auto_retry_count": 1,
                    "auto_stages": ["brief_locked", "assets_gate"],
                    "pause_conditions": ["generated_image_review"],
                    "expires_at": "2026-08-19T08:47:21.029Z",
                    "revoke_method": "聊天发送撤销快速模式",
                },
                "expires_at": "2026-08-19T08:47:21.029Z",
                "created_at": "2026-08-18T08:47:21.029Z",
                "status": "applied",
                "provider": "agnes",
                "model": "agnes-video-v2.0",
                "runtime": "remotion",
                "cost_cap_cny": 0.0,
                "call_cap": 2,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = runner.tick("demo-pro", append_decision=lambda *_: {})
    assert "recover_stuck_stage" in result["actions"]
    overlay = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert overlay["board_stop"]["stage"] == "assets_gate"


def test_tick_reopens_delivery_completed_without_video(monkeypatch, tmp_path):
    from tests.lib.test_board_advance import (
        _seed_minimal_ready_for_delivery,
        _write_bogus_delivery_completed,
    )

    root = tmp_path / "projects"
    project = _write_project(
        root,
        production_profile={"review_mode_preset": "minimal"},
    )
    _patch_projects(monkeypatch, root)
    monkeypatch.setattr(
        "openmontage.mcp.media.tools.compose_start",
        _stub_compose_start,
    )
    _seed_minimal_ready_for_delivery(root, "demo-pro")
    _write_bogus_delivery_completed(project)
    result = runner.tick("demo-pro", append_decision=lambda *_: {})
    assert "recover_stuck_stage" in result["actions"]
    assert "produce_start" in result["actions"]
    assert result["phase"] == "producing"
    assert "正在按锁定轻度合成" in result["friendly_zh"]
    overlay = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert overlay["board_stop"]["producing_wait"] is True
    delivery = json.loads(
        (project / "checkpoint_delivery_signoff.json").read_text(encoding="utf-8")
    )
    assert delivery["status"] != "completed"


def test_tick_starts_light_compose_after_assets_gate(monkeypatch, tmp_path):
    from tests.lib.test_board_advance import _seed_minimal_ready_for_delivery

    root = tmp_path / "projects"
    project = _write_project(
        root,
        production_profile={
            "review_mode_preset": "minimal",
            "production_tier": "light",
        },
    )
    _patch_projects(monkeypatch, root)
    calls = {"n": 0}

    def stub(*_args, **_kwargs):
        calls["n"] += 1
        return {"job_id": "compose-job-1", "output_path": "renders/final.mp4"}

    monkeypatch.setattr("openmontage.mcp.media.tools.compose_start", stub)
    _seed_minimal_ready_for_delivery(root, "demo-pro")
    result = runner.tick("demo-pro", append_decision=lambda *_: {})
    assert "produce_start" in result["actions"]
    assert result["phase"] == "producing"
    assert calls["n"] == 1
    job = json.loads(
        (project / "artifacts" / "produce_job.json").read_text(encoding="utf-8")
    )
    assert job["status"] == "queued"
    assert job["engine"] == "compose"
    assert "1–3 分钟" in result["friendly_zh"]


def test_tick_heavy_without_key_stays_paused(monkeypatch, tmp_path):
    import lib.board_produce as board_produce
    from tests.lib.test_board_advance import _seed_minimal_ready_for_delivery

    root = tmp_path / "projects"
    project = _write_project(
        root,
        production_profile={
            "review_mode_preset": "minimal",
            "production_tier": "heavy",
            "provider": "agnes",
            "video_channel": "agnes",
        },
    )
    _patch_projects(monkeypatch, root)
    monkeypatch.setattr(board_produce, "_present_key_names", lambda: set())
    monkeypatch.setattr(
        "openmontage.mcp.media.tools.compose_start",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
    )
    _seed_minimal_ready_for_delivery(root, "demo-pro")
    result = runner.tick("demo-pro", append_decision=lambda *_: {})
    assert "produce_paused" in result["actions"]
    assert result["phase"] == "paused"
    assert "不降为轻度" in result["friendly_zh"]
    marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert marker["production_profile"]["production_tier"] == "heavy"


def test_tick_opens_delivery_when_final_exists(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = _write_project(
        root,
        production_profile={
            "review_mode_preset": "minimal",
            "production_tier": "light",
        },
    )
    (project / "renders" / "final.mp4").write_bytes(b"film")
    _patch_projects(monkeypatch, root)
    result = runner.tick("demo-pro", append_decision=lambda *_: {})
    assert result["phase"] == "ready"
    assert "delivery_ready" in result["actions"]
    assert "结束并导出" in result["friendly_zh"]
    overlay = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert overlay["board_stop"]["stage"] == "delivery_signoff"
    assert overlay["board_stop"].get("producing_wait") is not True
    assert overlay["board_stop"]["decision_options"] == []
    assert overlay["board_stop"]["needs_user_decision"] is False


"""FastMCP exposure tests for interaction-intent approval bundles."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

import lib.approval_bundle as approval_bundle
import lib.interaction_intents as interaction_intents
from openmontage.mcp.bootstrap import server as server_mod
from openmontage.mcp.bootstrap import tools as tools_mod
from openmontage.mcp.bootstrap.server import mcp


NEW_TOOL_NAMES = {
    "produce_list_interaction_intents",
    "produce_plan_approval_bundle",
    "produce_apply_approval_bundle",
    "produce_fast_track_evaluate",
}


def _planned_intent() -> dict:
    summary = "确认轻度档审批包"
    return {
        "version": "1.0",
        "intent_type": "approval_bundle",
        "intent_id": "approval-001",
        "project_id": "demo-pro",
        "stage": "brief_locked",
        "revision": "revision-001",
        "summary": summary,
        "summary_sha256": hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        "payload": {
            "theme": "翡翠手镯",
            "duration_seconds": 15,
            "production_tier": "light",
            "review_mode": "guided",
            "provider": "local",
            "model": "deterministic",
            "runtime": "remotion",
            "asset_strategy": "reuse-approved",
            "allow_deterministic_reuse": True,
            "max_generations": 2,
            "unit_price_cny": 0,
            "total_budget_cny": 0,
            "resolution": "1080x1920",
            "quality_target": "draft",
            "auto_retry_count": 1,
            "auto_stages": ["brief_locked", "sample_review"],
            "pause_conditions": ["generated_image_review", "budget_exceeded"],
            "expires_at": "2099-08-15T01:00:00+00:00",
            "revoke_method": "聊天发送撤销快速模式",
        },
        "expires_at": "2099-08-15T01:00:00+00:00",
        "created_at": "2026-08-14T01:00:00+00:00",
        "status": "planned",
    }


def _legal_fast_track_snapshot() -> dict:
    return {
        "policy": {
            "version": "1.0",
            "provider": "local",
            "model": "deterministic",
            "runtime": "remotion",
            "call_cap": 2,
            "cost_cap_cny": 10.0,
            "unit_price_cny": 1.0,
            "resolution": "1080x1920",
            "quality_target": "draft",
            "auto_retry_count": 1,
            "auto_stages": ["sample_review", "delivery_signoff"],
            "expires_at": "2099-08-15T01:00:00+00:00",
            "revoke_method": "聊天发送撤销快速模式",
        },
        "now": "2026-08-14T01:00:00+00:00",
        "current_stage": "sample_review",
        "asset_matrix_closed": True,
        "generated_images_pending_review": False,
        "provider": "local",
        "model": "deterministic",
        "runtime": "remotion",
        "cost_cny_used": 1.0,
        "calls_used": 1,
        "unit_price_cny": 1.0,
        "identity_qa_pass": True,
        "structure_qa_pass": True,
        "technical_qa_pass": True,
        "new_cloud_upload_authorization": False,
        "new_cross_beat_reuse": False,
        "product_downgrade_or_hero_replace": False,
        "revision_list_nonempty": False,
        "user_paused": False,
        "user_revoked": False,
        "user_revision_submitted": False,
        "intent_expired": False,
        "revision_drift": False,
        "artifact_revision": "revision-001",
        "bundle_baseline_revision": "revision-001",
        "final_video_ready": False,
    }


@pytest.fixture
def approval_project(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    project = root / "demo-pro"
    intents = project / "intents"
    intents.mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "project_id": "demo-pro",
                "title": "Approval MCP",
                "pipeline_type": "bootstrap-commercial",
            }
        ),
        encoding="utf-8",
    )
    (intents / "approval-001.json").write_text(
        json.dumps(_planned_intent(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(interaction_intents, "PROJECTS_DIR", root)
    monkeypatch.setattr(approval_bundle, "PROJECTS_DIR", root)
    return project


def test_fastmcp_exposes_new_and_edit_intent_tools() -> None:
    tool_names = {tool.name for tool in asyncio.run(mcp.list_tools())}

    assert NEW_TOOL_NAMES.issubset(tool_names)
    assert {"produce_list_intents", "produce_apply_intent"}.issubset(tool_names)


def test_wrong_phrase_returns_safe_failure_envelope(
    approval_project, monkeypatch
) -> None:
    monkeypatch.setattr(
        tools_mod,
        "produce_append_decision",
        lambda *_args: pytest.fail("wrong phrase must not append a decision"),
    )

    result = server_mod.produce_apply_approval_bundle(
        "demo-pro",
        "approval-001",
        "确认面板",
        "revision-001",
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"] == {
        "code": "confirmation_required",
        "message": "请输入确认面板选择",
    }
    assert json.loads(
        (approval_project / "intents" / "approval-001.json").read_text(
            encoding="utf-8"
        )
    )["status"] == "planned"


def test_list_bootstrap_tools_includes_new_names() -> None:
    listed = set(tools_mod.list_bootstrap_tools()["produce_minimal"])

    assert NEW_TOOL_NAMES.issubset(listed)


def test_fast_track_valid_snapshot_continues_without_project_disk_access(
    tmp_path, monkeypatch
) -> None:
    project_root = (tmp_path / "projects").resolve()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(project_root))

    original_open = Path.open
    original_exists = Path.exists
    original_iterdir = Path.iterdir
    original_mkdir = Path.mkdir

    def is_project_path(path: Path) -> bool:
        resolved = path.resolve()
        return resolved == project_root or project_root in resolved.parents

    def guarded_open(path: Path, *args, **kwargs):
        if is_project_path(path):
            pytest.fail(f"fast-track evaluation opened project path: {path}")
        return original_open(path, *args, **kwargs)

    def guarded_exists(path: Path) -> bool:
        if is_project_path(path):
            pytest.fail(f"fast-track evaluation checked project path: {path}")
        return original_exists(path)

    def guarded_iterdir(path: Path):
        if is_project_path(path):
            pytest.fail(f"fast-track evaluation listed project path: {path}")
        return original_iterdir(path)

    def guarded_mkdir(path: Path, *args, **kwargs):
        if is_project_path(path):
            pytest.fail(f"fast-track evaluation created project path: {path}")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "exists", guarded_exists)
    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)
    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)

    result = server_mod.produce_fast_track_evaluate(
        "demo-pro",
        json.dumps(_legal_fast_track_snapshot(), ensure_ascii=False),
    )

    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"] == {
        "project_id": "demo-pro",
        "action": "continue",
        "reason_code": None,
        "friendly_zh": "当前条件满足，可继续下一阶段。",
        "current_question": None,
    }
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("snapshot_json", ["", "{", "[]"])
def test_fast_track_invalid_snapshot_returns_bad_request_envelope(
    snapshot_json: str,
) -> None:
    result = server_mod.produce_fast_track_evaluate("demo-pro", snapshot_json)

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "bad_request"

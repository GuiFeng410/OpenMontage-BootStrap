"""Board stop cards list options without a recommended badge."""

from __future__ import annotations

import json
from pathlib import Path

from lib.board_advance import (
    advance_after_apply,
    ensure_current_stop_card,
    stop_options,
    strip_recommend,
    write_stop_card,
)
from lib.checkpoint import read_checkpoint


def _write_project(root: Path, project_id: str = "shop-demo") -> dict:
    project = root / project_id
    project.mkdir(parents=True)
    marker = {
        "project_id": project_id,
        "title": "Shop",
        "pipeline_type": "bootstrap-commercial",
        "production_profile": {
            "review_mode_preset": "minimal",
            "production_tier": "light",
        },
    }
    (project / "project.json").write_text(
        json.dumps(marker, ensure_ascii=False),
        encoding="utf-8",
    )
    return marker


def test_stop_options_have_no_recommend() -> None:
    options = stop_options("brief_locked")
    assert [item["id"] for item in options] == ["continue", "revise"]
    assert all("recommended" not in item for item in options)


def test_strip_recommend_drops_badge_fields() -> None:
    cleaned = strip_recommend(
        {
            "recommendation_zh": "推荐重度",
            "options": [{"id": "heavy", "recommended": True, "label_zh": "重度"}],
        }
    )
    assert "recommendation_zh" not in cleaned
    assert "recommended" not in cleaned["options"][0]
    assert cleaned["options"][0]["label_zh"] == "重度"


def test_ensure_current_stop_card_has_no_recommend(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    stage = ensure_current_stop_card("shop-demo", marker, projects_dir=root)
    assert stage == "brief_locked"
    checkpoint = read_checkpoint(root, "shop-demo", "brief_locked")
    meta = checkpoint["metadata"]
    assert meta["needs_user_decision"] is True
    assert "recommendation_zh" not in meta
    assert all("recommended" not in item for item in meta["decision_options"])
    assert checkpoint["status"] == "in_progress"


def test_advance_writes_next_stop_without_completing_prior(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    write_stop_card("shop-demo", "brief_locked", projects_dir=root)
    nxt = advance_after_apply(
        "shop-demo",
        "brief_locked",
        marker,
        projects_dir=root,
    )
    assert nxt == "assets_gate"
    brief = read_checkpoint(root, "shop-demo", "brief_locked")
    assert brief["metadata"].get("needs_user_decision") is False
    assert "decision_options" not in brief["metadata"]
    assert read_checkpoint(root, "shop-demo", "assets_gate") is None
    overlay = json.loads(
        (root / "shop-demo" / "project.json").read_text(encoding="utf-8")
    )["board_stop"]
    assert overlay["stage"] == "assets_gate"
    assert overlay["needs_user_decision"] is True
    assert "recommendation_zh" not in overlay
    assert all("recommended" not in item for item in overlay["decision_options"])

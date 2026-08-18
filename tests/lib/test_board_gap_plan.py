"""Plan-page four-way gap choices. Never calls paid generate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from lib.board_advance import ensure_current_stop_card, stop_card_metadata
from lib.board_gap_plan import (
    GapPlanError,
    build_gap_snapshot,
    default_commercial_image_model,
    list_commercial_image_models,
    lock_gap_plan_from_intent,
)
from lib.checkpoint import read_checkpoint


def _write_project(root: Path, project_id: str = "shop-demo", **profile) -> Path:
    project = root / project_id
    project.mkdir(parents=True)
    marker = {
        "project_id": project_id,
        "title": "玉镯",
        "pipeline_type": "bootstrap-commercial",
        "production_profile": {
            "review_mode_preset": "minimal",
            "production_tier": "light",
            "duration_seconds": 10,
            **profile,
        },
    }
    (project / "project.json").write_text(
        json.dumps(marker, ensure_ascii=False),
        encoding="utf-8",
    )
    return project


def _png(path: Path, color: tuple[int, int, int] = (180, 40, 40)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 800), color).save(path)


def _intent(selections: list[dict]) -> dict:
    return {
        "intent_type": "decision",
        "stage": "brief_locked",
        "payload": {"selections": selections},
    }


def test_image_catalog_excludes_pixverse() -> None:
    ids = [item["id"] for item in list_commercial_image_models()]
    assert "pixverse" not in ids
    assert "dashscope" in ids


def test_default_image_model_prefers_agnes_when_multiple_keys() -> None:
    rows = list_commercial_image_models(
        ["DASHSCOPE_API_KEY", "AGNES_API_KEY", "FAL_KEY"]
    )
    picked = default_commercial_image_model(rows)
    assert picked is not None
    assert picked["id"] == "agnes"
    dash_only = default_commercial_image_model(
        list_commercial_image_models(["DASHSCOPE_API_KEY"])
    )
    assert dash_only is not None
    assert dash_only["id"] == "dashscope"


def test_no_images_means_gaps(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    snap = build_gap_snapshot(
        "shop-demo",
        projects_dir=root,
        repo_root=tmp_path,
        environ={},
    )
    assert snap["enough"] is False
    assert snap["image_key_present"] is False
    assert len(snap["gaps"]) == 3
    i2i = next(item for item in snap["image_models"] if item["id"] == "dashscope")
    assert i2i["available"] is False


def test_enough_images_cover_beats(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = _write_project(root)
    for name, color in (
        ("hero.png", (180, 40, 40)),
        ("side.png", (40, 180, 40)),
        ("detail.png", (40, 40, 180)),
    ):
        _png(project / "assets" / "images" / name, color)
    snap = build_gap_snapshot(
        "shop-demo",
        projects_dir=root,
        repo_root=tmp_path,
        environ={},
    )
    assert snap["enough"] is True
    assert snap["gaps"] == []
    assert len(snap["covered"]) == 3


def test_i2i_available_when_dashscope_key_in_env(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DASHSCOPE_API_KEY=sk-test-not-secret\n", encoding="utf-8")
    root = tmp_path / "projects"
    _write_project(root)
    snap = build_gap_snapshot(
        "shop-demo",
        projects_dir=root,
        repo_root=tmp_path,
        environ={},
    )
    assert snap["image_key_present"] is True
    models = {item["id"]: item for item in snap["image_models"]}
    assert models["dashscope"]["available"] is True
    assert snap["default_image_model"] == "dashscope"


def test_continue_without_gap_choice_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    with pytest.raises(GapPlanError) as caught:
        lock_gap_plan_from_intent(
            "shop-demo",
            _intent(
                [
                    {
                        "decision_key": "brief_locked::current",
                        "option_id": "continue",
                    }
                ]
            ),
            projects_dir=root,
            repo_root=tmp_path,
            environ={},
        )
    assert caught.value.code == "gap_choice_required"


def test_i2i_without_key_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    with pytest.raises(GapPlanError) as caught:
        lock_gap_plan_from_intent(
            "shop-demo",
            _intent(
                [
                    {"decision_key": "brief_locked::current", "option_id": "continue"},
                    {"decision_key": "gap::B01", "option_id": "i2i"},
                    {"decision_key": "gap::B02", "option_id": "skip"},
                    {"decision_key": "gap::B03", "option_id": "skip"},
                ]
            ),
            projects_dir=root,
            repo_root=tmp_path,
            environ={},
        )
    assert caught.value.code == "i2i_unavailable"


def test_i2i_without_shared_model_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    with pytest.raises(GapPlanError) as caught:
        lock_gap_plan_from_intent(
            "shop-demo",
            _intent(
                [
                    {"decision_key": "brief_locked::current", "option_id": "continue"},
                    {"decision_key": "gap::B01", "option_id": "i2i"},
                    {"decision_key": "gap::B02", "option_id": "skip"},
                    {"decision_key": "gap::B03", "option_id": "skip"},
                ]
            ),
            projects_dir=root,
            repo_root=tmp_path,
            environ={"DASHSCOPE_API_KEY": "sk-test-not-secret"},
        )
    assert caught.value.code == "i2i_model_required"


def test_lock_i2i_uses_one_shared_model_for_all_gaps(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = _write_project(root)
    result = lock_gap_plan_from_intent(
        "shop-demo",
        _intent(
            [
                {"decision_key": "brief_locked::current", "option_id": "continue"},
                {"decision_key": "gap::B01", "option_id": "i2i"},
                {"decision_key": "gap::B02", "option_id": "i2i"},
                {"decision_key": "gap::B03", "option_id": "skip"},
                {"decision_key": "image_model::project", "option_id": "agnes"},
            ]
        ),
        projects_dir=root,
        repo_root=tmp_path,
        environ={
            "DASHSCOPE_API_KEY": "sk-dash-not-secret",
            "AGNES_API_KEY": "ag-not-secret",
        },
    )
    assert result["action"] == "continue"
    locked = json.loads((project / "artifacts" / "gap_plan.json").read_text(encoding="utf-8"))
    assert locked["image_model"] == "agnes"
    by_beat = {row["beat_id"]: row for row in locked["gaps"]}
    assert by_beat["B01"]["i2i_model"] == "agnes"
    assert by_beat["B02"]["i2i_model"] == "agnes"
    assert by_beat["B03"]["i2i_model"] is None
    marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert marker["production_profile"]["image_model"] == "agnes"
    assert "video_model" not in marker["production_profile"]
    plan = json.loads((project / "artifacts" / "video_plan.json").read_text(encoding="utf-8"))
    segs = {row["beat"]: row for row in plan["segments"]}
    assert segs["B01"]["provider"] == "agnes"
    assert segs["B02"]["provider"] == "agnes"


def test_lock_skip_writes_plan_without_generate(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = _write_project(root)
    result = lock_gap_plan_from_intent(
        "shop-demo",
        _intent(
            [
                {"decision_key": "brief_locked::current", "option_id": "continue"},
                {"decision_key": "gap::B01", "option_id": "skip"},
                {"decision_key": "gap::B02", "option_id": "upload"},
                {"decision_key": "gap::B03", "option_id": "skip"},
            ]
        ),
        projects_dir=root,
        repo_root=tmp_path,
        environ={},
    )
    assert result["action"] == "continue"
    plan = json.loads((project / "artifacts" / "video_plan.json").read_text(encoding="utf-8"))
    by_beat = {row["beat"]: row for row in plan["segments"]}
    assert by_beat["B01"]["gap_fill"] == "concept_only"
    assert by_beat["B02"]["gap_fill"] == "user_upload"
    assert by_beat["B02"]["assignment_status"] == "missing"
    locked = json.loads((project / "artifacts" / "gap_plan.json").read_text(encoding="utf-8"))
    assert locked["locked"] is True


def test_revise_does_not_write_plan(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = _write_project(root)
    result = lock_gap_plan_from_intent(
        "shop-demo",
        _intent(
            [{"decision_key": "brief_locked::current", "option_id": "revise"}]
        ),
        projects_dir=root,
        repo_root=tmp_path,
        environ={},
    )
    assert result["action"] == "revise"
    assert not (project / "artifacts" / "gap_plan.json").is_file()


def test_stop_card_includes_gap_plan(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = json.loads(
        (_write_project(root) / "project.json").read_text(encoding="utf-8")
    )
    stage = ensure_current_stop_card("shop-demo", marker, projects_dir=root)
    assert stage == "brief_locked"
    overlay = json.loads((root / "shop-demo" / "project.json").read_text(encoding="utf-8"))
    assert overlay["board_stop"]["gap_plan"]["enough"] is False
    meta = stop_card_metadata("brief_locked", "shop-demo", projects_dir=root)
    assert "补传" in meta["decision_prompt_zh"]
    checkpoint = read_checkpoint(root, "shop-demo", "brief_locked")
    assert checkpoint["metadata"]["gap_plan"]["gaps"]


def test_lock_then_complete_brief_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(root))
    result = lock_gap_plan_from_intent(
        "shop-demo",
        _intent(
            [
                {"decision_key": "brief_locked::current", "option_id": "continue"},
                {"decision_key": "gap::B01", "option_id": "skip"},
                {"decision_key": "gap::B02", "option_id": "skip"},
                {"decision_key": "gap::B03", "option_id": "skip"},
            ]
        ),
        projects_dir=root,
        repo_root=tmp_path,
        environ={},
    )
    from lib.checkpoint import merge_write_checkpoint

    merge_write_checkpoint(
        root,
        "shop-demo",
        "brief_locked",
        "completed",
        {
            "brief": result["artifacts"]["brief"],
            "asset_precheck": result["artifacts"]["asset_precheck"],
            "video_plan": result["artifacts"]["video_plan"],
            "segment_cards": result["artifacts"]["segment_cards"],
        },
        pipeline_type="bootstrap-commercial",
        human_approval_required=True,
        human_approved=True,
    )
    checkpoint = read_checkpoint(root, "shop-demo", "brief_locked")
    assert checkpoint["status"] == "completed"


def test_gap_plan_module_does_not_call_paid_generate() -> None:
    from lib import board_gap_plan

    src = Path(board_gap_plan.__file__).read_text(encoding="utf-8")
    assert "image_generate" not in src
    assert "video_generate" not in src
    assert "tts_generate" not in src
    assert "stock_download" not in src

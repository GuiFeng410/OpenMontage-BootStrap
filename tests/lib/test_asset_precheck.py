"""Tests for the read-only commercial image precheck."""

from __future__ import annotations

import hashlib

import pytest
from PIL import Image

from lib import asset_precheck as asset_precheck_mod
from lib.asset_precheck import (
    build_asset_ledger,
    build_asset_requirements,
    duration_profile,
    scan_user_images,
)


def _image(path, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color="white").save(path)


def _review_decision_log(
    *,
    project_id: str,
    path: str,
    beats: list[str],
    project_dir=None,
    decision_id: str = "review-approved",
    decision_patch: dict | None = None,
) -> dict:
    decision = {
        "decision_id": decision_id,
        "stage": "assets_gate",
        "category": "asset_decision",
        "subject": path,
        "asset_path": path,
        "asset_source": "generated",
        "beat_ids": beats,
        "options_considered": [{
            "option_id": "approved",
            "label": "批准生成图",
            "score": 1.0,
            "reason": "候选图符合当前 Beat。",
        }],
        "selected": "approved",
        "reason": "用户批准该候选图。",
        "user_approved": True,
        "user_response_text": "批准该候选图。",
    }
    if project_dir is not None:
        decision["asset_sha256"] = hashlib.sha256(
            (project_dir / path).read_bytes()
        ).hexdigest()
    decision.update(decision_patch or {})
    return {
        "version": "1.0",
        "project_id": project_id,
        "decisions": [decision],
    }


def test_scan_user_images_reports_facts_filename_suggestions_and_risks(tmp_path):
    project_dir = tmp_path / "demo-product"
    images_dir = project_dir / "assets" / "images"
    _image(images_dir / "bracelet_hero.png", (1200, 800))
    _image(images_dir / "bracelet_detail.png", (320, 320))
    (images_dir / "bracelet_hero_copy.png").write_bytes(
        (images_dir / "bracelet_hero.png").read_bytes()
    )
    (images_dir / "notes.txt").write_text("not an image", encoding="utf-8")

    report = scan_user_images(project_dir, min_dimension=640)

    assert report["version"] == "1.0"
    assert report["summary"]["total_images"] == 3
    assert report["summary"]["low_resolution_count"] == 1
    assert report["summary"]["duplicate_group_count"] == 1
    assert report["summary"]["needs_user_attention"] is True
    assert report["summary"]["counts_by_suggested_class"]["product_hero"] == 2
    assert report["summary"]["counts_by_suggested_class"]["product_detail"] == 1
    by_file = {entry["file"]: entry for entry in report["entries"]}
    assert by_file["bracelet_hero.png"]["path"] == "assets/images/bracelet_hero.png"
    assert by_file["bracelet_hero.png"]["suggested_class"] == "product_hero"
    assert by_file["bracelet_detail.png"]["suggested_class"] == "product_detail"
    assert by_file["bracelet_detail.png"]["issues"] == ["resolution_too_small"]
    assert by_file["bracelet_hero_copy.png"]["duplicate_of"] == "bracelet_hero.png"


def test_scan_user_images_safely_recognizes_svg_dimensions_and_namespace(tmp_path):
    project_dir = tmp_path / "svg-product"
    images_dir = project_dir / "assets" / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "sized.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="800px" height="600">'
        '<rect width="800" height="600"/></svg>',
        encoding="utf-8",
    )
    (images_dir / "viewbox.svg").write_text(
        '<svg:svg xmlns:svg="http://www.w3.org/2000/svg" '
        'viewBox="0 0 1200 900"><svg:path d="M0 0"/></svg:svg>',
        encoding="utf-8",
    )
    (images_dir / "dimensionless.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>',
        encoding="utf-8",
    )
    (images_dir / "foreign-namespace.svg").write_text(
        '<evil:svg xmlns:evil="urn:not-svg" width="800" height="600"/>',
        encoding="utf-8",
    )

    report = scan_user_images(project_dir, min_dimension=640)
    by_file = {entry["file"]: entry for entry in report["entries"]}

    assert (by_file["sized.svg"]["width"], by_file["sized.svg"]["height"]) == (
        800,
        600,
    )
    assert (
        by_file["viewbox.svg"]["width"],
        by_file["viewbox.svg"]["height"],
    ) == (1200, 900)
    assert (
        by_file["dimensionless.svg"]["width"],
        by_file["dimensionless.svg"]["height"],
    ) == (1, 1)
    assert "svg_dimensions_missing" in by_file["dimensionless.svg"]["issues"]
    assert "foreign-namespace.svg" not in by_file


def test_scan_user_images_reports_dangerous_svg_without_expanding_entities(tmp_path):
    project_dir = tmp_path / "unsafe-svg-product"
    images_dir = project_dir / "assets" / "images"
    images_dir.mkdir(parents=True)
    secret = project_dir / "secret.txt"
    secret.write_text("must-not-be-expanded", encoding="utf-8")
    (images_dir / "fake.svg").write_text(
        "<html><body>not an svg</body></html>",
        encoding="utf-8",
    )
    (images_dir / "external-entity.svg").write_text(
        '<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///secret.txt">]>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">'
        "<text>&xxe;</text></svg>",
        encoding="utf-8",
    )
    (images_dir / "utf16-entity.svg").write_text(
        '<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///secret.txt">]>'
        '<svg xmlns="http://www.w3.org/2000/svg"><text>&xxe;</text></svg>',
        encoding="utf-16",
    )

    report = scan_user_images(project_dir)

    by_file = {entry["file"]: entry for entry in report["entries"]}
    assert "fake.svg" not in by_file
    assert by_file["external-entity.svg"]["width"] == 1
    assert by_file["external-entity.svg"]["height"] == 1
    assert "unsafe_svg_declaration" in by_file["external-entity.svg"]["issues"]
    assert "unsafe_svg_declaration" in by_file["utf16-entity.svg"]["issues"]
    assert "must-not-be-expanded" not in str(report)


def test_scan_user_images_reports_oversized_svg_without_reading_it(
    tmp_path,
    monkeypatch,
):
    project_dir = tmp_path / "oversized-svg-product"
    images_dir = project_dir / "assets" / "images"
    images_dir.mkdir(parents=True)
    oversized = images_dir / "oversized.svg"
    with oversized.open("wb") as stream:
        stream.seek(asset_precheck_mod._MAX_SVG_BYTES)
        stream.write(b"x")

    original_open = type(oversized).open

    def guarded_open(path, *args, **kwargs):
        if path.resolve() == oversized.resolve():
            raise AssertionError("oversized SVG content must not be opened")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(type(oversized), "open", guarded_open)

    report = scan_user_images(project_dir)

    entry = next(item for item in report["entries"] if item["file"] == "oversized.svg")
    assert entry["bytes"] == asset_precheck_mod._MAX_SVG_BYTES + 1
    assert entry["sha256"] == ""
    assert "svg_too_large" in entry["issues"]


def test_scan_user_images_returns_empty_report_when_upload_folder_is_missing(tmp_path):
    report = scan_user_images(tmp_path / "empty-product")

    assert report["entries"] == []
    assert report["summary"]["total_images"] == 0
    assert report["summary"]["needs_user_attention"] is True


def test_duration_profile_and_requirements_status():
    assert duration_profile(30)["minimum_image_count"] == 2
    ready = build_asset_requirements(
        duration_seconds=30,
        confirmed_classes=[
            "product_hero",
            "product_angle",
            "product_detail",
            "on_body",
            "product_hero",
            "product_angle",
        ],
    )
    assert ready["status"] == "就绪"
    waiting = build_asset_requirements(duration_seconds=30, confirmed_classes=["product_detail"])
    assert waiting["status"] == "等待用户选择"
    degraded = build_asset_requirements(
        duration_seconds=30,
        confirmed_classes=["product_hero"],
    )
    assert degraded["status"] == "降级继续"


def test_build_asset_ledger_merges_user_classes(tmp_path):
    project_dir = tmp_path / "ledger-product"
    images_dir = project_dir / "assets" / "images"
    _image(images_dir / "bracelet_hero.png", (900, 900))
    precheck = scan_user_images(project_dir)
    ledger = build_asset_ledger(
        project_id="ledger-product",
        precheck=precheck,
        user_classes={"assets/images/bracelet_hero.png": "product_hero"},
        duration_seconds=30,
        gap_fill="none",
        identity_anchor_path="assets/images/bracelet_hero.png",
    )
    assert ledger["entries"][0]["user_class"] == "product_hero"
    assert ledger["entries"][0]["is_identity_anchor"] is True
    assert ledger["summary"]["status_zh"] == "降级继续"
    assert ledger["asset_requirements"]["available_image_count"] == 1


def test_build_asset_ledger_writes_production_metadata_into_real_entries(tmp_path):
    project_dir = tmp_path / "ledger-production-metadata"
    images_dir = project_dir / "assets" / "images"
    image_path = "assets/images/bracelet_hero.png"
    _image(project_dir / image_path, (900, 900))

    ledger = build_asset_ledger(
        project_id=project_dir.name,
        precheck=scan_user_images(project_dir),
        user_classes={image_path: "product_hero"},
        entry_metadata={
            image_path: {
                "beat": "beat_01",
                "kind": "image",
                "origin": "user_upload",
                "selected": True,
                "label_zh": "商品身份主图",
            }
        },
    )

    entry = ledger["entries"][0]
    assert {
        key: entry[key]
        for key in ("beats", "kind", "origin", "selected", "label_zh")
    } == {
        "beats": ["beat_01"],
        "kind": "image",
        "origin": "user_upload",
        "selected": True,
        "label_zh": "商品身份主图",
    }


def test_build_asset_ledger_keeps_top_level_planned_entries(tmp_path):
    project_dir = tmp_path / "ledger-planned-entries"
    image_path = "assets/images/bracelet_hero.png"
    _image(project_dir / image_path, (900, 900))
    planned_entries = [
        {
            "beat": f"beat_{index:02d}",
            "kind": "video",
            "status": status,
            "source_paths": [image_path],
            "prompt_zh": f"{status} 提示词",
            "planned_output_path": f"assets/video/beat_{index:02d}.mp4",
            "output_path": (
                f"assets/video/beat_{index:02d}.mp4" if status == "ready" else ""
            ),
        }
        for index, status in enumerate(
            ("planned", "generating", "ready", "failed"),
            start=1,
        )
    ]

    ledger = build_asset_ledger(
        project_id=project_dir.name,
        precheck=scan_user_images(project_dir),
        user_classes={image_path: "product_hero"},
        planned_entries=planned_entries,
    )

    assert ledger["planned_entries"] == [
        {
            **{key: value for key, value in entry.items() if key != "beat"},
            "beats": [entry["beat"]],
        }
        for entry in planned_entries
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("S1", ["S1"]),
        ("S1,S4", ["S1", "S4"]),
        (["S2", "S6"], ["S2", "S6"]),
        (["S1,S4", " S2 ", "", "S1"], ["S1", "S4", "S2"]),
    ],
)
def test_normalize_beat_ids_accepts_strings_lists_and_legacy_commas(raw, expected):
    normalize = getattr(asset_precheck_mod, "normalize_beat_ids")

    assert normalize(raw) == expected


@pytest.mark.parametrize(
    ("status", "review_status"),
    [
        ("planned", ""),
        ("generating", ""),
        ("failed", ""),
        ("rejected", ""),
        ("review_pending", ""),
        ("ready", "review_pending"),
    ],
)
def test_matrix_rejects_open_non_i2i_plan_even_when_actual_covers_beat(
    status,
    review_status,
):
    planned = {
        "beats": ["S1"],
        "kind": "image",
        "origin": "user_upload",
        "status": status,
        "output_path": "assets/images/future.png",
    }
    if review_status:
        planned["review_status"] = review_status
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        ledger_entries=[{"path": "assets/images/actual.png", "beats": ["S1"]}],
        planned_entries=[planned],
    )

    assert result["open_planned_entries"]
    assert result["ready"] is False


def test_matrix_rejects_planned_image_without_any_source_declaration():
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        planned_entries=[{
            "beats": ["S1"],
            "kind": "image",
            "status": "planned",
        }],
    )

    assert result["planned_source_issues"] == [{
        "location": "planned_entries[0]",
        "beat_ids": ["S1"],
        "reason": "source_declaration_missing",
    }]
    assert result["ready"] is False


@pytest.mark.parametrize(
    ("status", "signal_patch"),
    [
        ("generating", {}),
        ("ready", {}),
        ("review_pending", {}),
        ("approved", {}),
        ("rejected", {}),
        ("failed", {}),
        ("planned", {"planned_output_path": "assets/images/future.png"}),
        ("planned", {"planned_output": "assets/images/future.png"}),
        ("planned", {"output_path": "assets/images/future.png"}),
        ("planned", {"output": "assets/images/future.png"}),
        ("planned", {"candidate_paths": ["assets/images/future.png"]}),
        ("planned", {"candidates": ["assets/images/future.png"]}),
        ("planned", {"provider": "provider"}),
        ("planned", {"model": "model"}),
    ],
)
def test_matrix_treats_every_planned_image_generation_signal_as_generated_chain(
    status,
    signal_patch,
):
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        planned_entries=[{
            "beats": ["S1"],
            "kind": "image",
            "status": status,
            **signal_patch,
        }],
    )

    assert result["i2i_issues"]
    assert "source_declaration_missing" in result["i2i_issues"][0]["reasons"]
    assert "review_not_approved" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


@pytest.mark.parametrize(
    "signal_patch",
    [
        {"provider": "provider"},
        {"model": "model"},
        {"candidate_paths": []},
        {"candidate_output_path": "assets/images/candidate.png"},
        {"output_path": "assets/images/output.png"},
        {"planned_output_path": "assets/images/planned.png"},
        {"review_status": "approved"},
        {"decision_id": "fake-decision"},
        {"retry_count": 0},
        {"max_retries": 2},
        {"retry_of": "previous-candidate"},
        {"status": "generating"},
    ],
)
def test_matrix_treats_actual_image_generation_signals_as_generated_chain(
    tmp_path,
    signal_patch,
):
    project_dir = tmp_path / "actual-generation-signal"
    output_path = "assets/images/actual.png"
    _image(project_dir / output_path, (900, 900))
    entry = {
        "path": output_path,
        "beats": ["S1"],
        "kind": "image",
        "status": "confirmed",
        "selected": True,
        **signal_patch,
    }

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_dir.name,
        canonical_beat_ids=["S1"],
        ledger_entries=[entry],
        project_dir=project_dir,
    )

    assert result["i2i_issues"]
    assert "source_declaration_missing" in result["i2i_issues"][0]["reasons"]
    assert result["assigned"].get("S1", []) == []
    assert result["ready"] is False


def test_matrix_keeps_plain_actual_user_upload_without_generation_signals_compatible(
    tmp_path,
):
    project_dir = tmp_path / "plain-user-upload"
    output_path = "assets/images/actual.png"
    _image(project_dir / output_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1"],
            "kind": "image",
            "status": "confirmed",
            "selected": True,
        }],
        project_dir=project_dir,
    )

    assert result["assigned"] == {"S1": [output_path]}
    assert result["i2i_issues"] == []
    assert result["ready"] is True


@pytest.mark.parametrize("reference_field", ["ref", "ref_image"])
def test_matrix_rejects_closed_video_plan_reference_that_differs_from_approved_path(
    tmp_path,
    reference_field,
):
    project_dir = tmp_path / "ref-drift"
    approved_path = "assets/images/new-approved.png"
    old_path = "assets/images/old-approved.png"
    _image(project_dir / approved_path, (900, 900))
    _image(project_dir / old_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        project_dir=project_dir,
        ledger_entries=[{
            "path": approved_path,
            "beats": ["S1"],
            "kind": "image",
            "status": "confirmed",
            "origin": "user_upload",
            "selected": True,
        }],
        video_plan={
            "status": "completed",
            "segments": [{
                "id": "S1",
                "assignment_status": "approved",
                "asset_source": "user_upload",
                reference_field: old_path,
            }],
        },
    )

    assert {
        "location": "video_plan[0]",
        "beat_id": "S1",
        "reason": "reference_matrix_mismatch",
        "declared_references": [old_path],
        "approved_path": approved_path,
    } in result["video_plan_conflicts"]
    assert result["ready"] is False


def test_matrix_exposes_unique_approved_reference_for_closed_plan_backfill(
    tmp_path,
):
    project_dir = tmp_path / "ref-backfill"
    approved_path = "assets/images/approved.png"
    _image(project_dir / approved_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        project_dir=project_dir,
        ledger_entries=[{
            "path": approved_path,
            "beats": ["S1"],
            "kind": "image",
            "status": "confirmed",
            "origin": "user_upload",
            "selected": True,
        }],
        video_plan={
            "status": "completed",
            "segments": [{
                "id": "S1",
                "assignment_status": "approved",
                "asset_source": "user_upload",
            }],
        },
    )

    assert result["video_plan_conflicts"] == []
    assert result["approved_references"] == {"S1": approved_path}
    assert result["ready"] is True


def test_matrix_rejects_completed_plan_old_reference_without_row_status(tmp_path):
    project_dir = tmp_path / "completed-ref-drift"
    approved_path = "assets/images/new-approved.png"
    old_path = "assets/images/old-approved.png"
    _image(project_dir / approved_path, (900, 900))
    _image(project_dir / old_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        project_dir=project_dir,
        ledger_entries=[{
            "path": approved_path,
            "beats": ["S1"],
            "kind": "image",
            "status": "confirmed",
            "origin": "user_upload",
            "selected": True,
        }],
        video_plan={
            "status": "completed",
            "segments": [{
                "id": "S1",
                "asset_source": "user_upload",
                "ref": old_path,
            }],
        },
    )

    assert any(
        issue["reason"] == "reference_matrix_mismatch"
        for issue in result["video_plan_conflicts"]
    )
    assert result["ready"] is False


def test_matrix_allows_unreviewed_i2i_video_plan_to_omit_reference(tmp_path):
    project_dir = tmp_path / "ref-open-i2i"
    candidate_path = "assets/images/candidate.png"
    _image(project_dir / candidate_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        project_dir=project_dir,
        planned_entries=[{
            "beats": ["S1"],
            "kind": "image",
            "status": "review_pending",
            "asset_source": "i2i",
            "output_path": candidate_path,
            "provider": "provider",
            "model": "model",
        }],
        video_plan={
            "segments": [{
                "id": "S1",
                "assignment_status": "i2i_review_pending",
                "asset_source": "i2i",
            }],
        },
    )

    reference_reasons = {
        issue["reason"]
        for issue in result["video_plan_conflicts"]
        if issue["reason"].startswith(("reference_", "approved_reference_"))
    }
    assert reference_reasons == set()


def test_matrix_rejects_cross_project_decision_log_without_decision_features():
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id="current-project",
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": "assets/images/actual.png",
            "beats": ["S1"],
            "kind": "image",
            "status": "confirmed",
            "origin": "user_upload",
            "selected": True,
        }],
        decision_log={
            "version": "1.0",
            "project_id": "other-project",
            "decisions": [],
        },
    )

    assert result["decision_log_issues"] == [{
        "reason": "project_id_mismatch",
        "expected_project_id": "current-project",
        "actual_project_id": "other-project",
    }]
    assert result["ready"] is False


@pytest.mark.parametrize(
    "status",
    ["pending_user_confirmation", "pending", "rejected", "failed", "blocked"],
)
def test_matrix_rejects_open_unused_ledger_entry(status):
    open_path = "assets/images/open.png"
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        ledger_entries=[
            {
                "path": "assets/images/actual.png",
                "beats": ["S1"],
                "status": "confirmed",
            },
            {"path": open_path, "status": status},
        ],
    )

    assert result["open_ledger_entries"]
    assert open_path not in result["unused_assets"]
    assert result["ready"] is False


@pytest.mark.parametrize("closed_status", ["assigned", "ready", "approved"])
def test_matrix_accepts_compatible_closed_video_plan_status(closed_status):
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        segment_cards={"segments": [{"beat": "S1"}]},
        video_plan={
            "segments": [{
                "id": "S1",
                "assignment_status": closed_status,
                "asset_source": "user_upload",
            }],
        },
        ledger_entries=[{
            "path": "assets/images/actual.png",
            "beats": ["S1"],
            "status": "confirmed",
            "origin": "user_upload",
        }],
    )

    assert result["video_plan_conflicts"] == []
    assert result["ready"] is True


@pytest.mark.parametrize(
    "open_status",
    [
        "planned",
        "missing",
        "reuse_pending",
        "review_pending",
        "i2i_review_pending",
        "rejected",
        "failed",
    ],
)
def test_matrix_rejects_open_video_plan_status_despite_actual(open_status):
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        segment_cards={"segments": [{"beat": "S1"}]},
        video_plan={
            "segments": [{
                "id": "S1",
                "assignment_status": open_status,
            }],
        },
        ledger_entries=[{
            "path": "assets/images/actual.png",
            "beats": ["S1"],
            "status": "confirmed",
        }],
    )

    assert result["video_plan_conflicts"]
    assert result["ready"] is False


def test_matrix_rejects_video_plan_source_drift_from_ledger():
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        segment_cards={"segments": [{"beat": "S1"}]},
        video_plan={
            "segments": [{
                "id": "S1",
                "assignment_status": "assigned",
                "gap_fill": "i2i",
                "asset_source": "i2i",
            }],
        },
        ledger_entries=[{
            "path": "assets/images/actual.png",
            "beats": ["S1"],
            "status": "confirmed",
            "origin": "user_upload",
        }],
    )

    assert result["video_plan_conflicts"]
    assert result["ready"] is False


def test_matrix_rejects_multiple_actual_paths_for_one_beat():
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        ledger_entries=[
            {"path": "assets/images/a.png", "beats": ["S1"]},
            {"path": "assets/images/b.png", "beats": ["S1"]},
        ],
    )

    assert result["assignment_conflicts"] == [{
        "beat_id": "S1",
        "paths": ["assets/images/a.png", "assets/images/b.png"],
    }]
    assert result["ready"] is False


def test_matrix_rejects_exact_planned_and_actual_paths_for_same_beat(tmp_path):
    project_id = "planned-actual-conflict"
    planned_path = "assets/images/planned.png"
    _image(tmp_path / "assets/images/actual.png", (900, 900))
    _image(tmp_path / planned_path, (900, 900))
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": "assets/images/actual.png",
            "beats": ["S1"],
            "status": "confirmed",
        }],
        planned_entries=[{
            "beats": ["S1"],
            "kind": "image",
            "origin": "generated",
            "status": "approved",
            "review_status": "approved",
            "decision_id": "review-approved",
            "provider": "provider",
            "model": "model",
            "candidate_paths": [planned_path],
            "output_path": planned_path,
        }],
        decision_log=_review_decision_log(
            project_id=project_id,
            path=planned_path,
            beats=["S1"],
            project_dir=tmp_path,
        ),
        project_dir=tmp_path,
    )

    assert result["assignment_conflicts"] == [{
        "beat_id": "S1",
        "paths": [
            "assets/images/actual.png",
            "assets/images/planned.png",
        ],
    }]
    assert result["ready"] is False


def test_matrix_allows_one_selected_approved_path_from_candidate_set(tmp_path):
    project_id = "one-approved-candidate"
    output_path = "assets/images/b.png"
    _image(tmp_path / output_path, (900, 900))
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        planned_entries=[{
            "beats": ["S1"],
            "kind": "image",
            "origin": "generated",
            "status": "approved",
            "review_status": "approved",
            "decision_id": "review-approved",
            "provider": "provider",
            "model": "model",
            "candidate_paths": [
                "assets/images/a.png",
                output_path,
            ],
            "candidate_output_path": output_path,
            "output_path": output_path,
        }],
        decision_log=_review_decision_log(
            project_id=project_id,
            path=output_path,
            beats=["S1"],
            project_dir=tmp_path,
        ),
        project_dir=tmp_path,
    )

    assert result["assigned"] == {"S1": ["assets/images/b.png"]}
    assert result["assignment_conflicts"] == []
    assert result["ready"] is True


def test_matrix_rejects_generic_reuse_approval_without_exact_scope():
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id="project-a",
        canonical_beat_ids=["S1", "S2"],
        ledger_entries=[{
            "path": "assets/images/shared.png",
            "beats": ["S1", "S2"],
        }],
        decision_log={
            "version": "1.0",
            "project_id": "project-a",
            "decisions": [{
                "decision_id": "generic-approval",
                "stage": "assets_gate",
                "category": "asset_decision",
                "subject": "assets/images/shared.png",
                "options_considered": [{
                    "option_id": "approved",
                    "label": "批准",
                    "score": 1.0,
                    "reason": "已批准其它事项。",
                }],
                "selected": "approved",
                "reason": "批准。",
                "user_approved": True,
                "user_response_text": "同意。",
            }],
        },
    )

    assert result["reuse_pending"]
    assert result["ready"] is False


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [
        ("project_id", "other-project"),
        ("stage", "brief_locked"),
        ("asset_path", "assets/images/other.png"),
        ("beat_ids", ["S1"]),
    ],
)
def test_matrix_rejects_reuse_approval_with_wrong_scope(field, wrong_value):
    project_id = "project-a"
    decision = {
        "decision_id": "scoped-reuse",
        "stage": "assets_gate",
        "category": "asset_decision",
        "subject": "assets/images/shared.png",
        "asset_path": "assets/images/shared.png",
        "beat_ids": ["S1", "S2"],
        "options_considered": [{
            "option_id": "reuse",
            "label": "精确复用",
            "score": 1.0,
            "reason": "复用指定路径到指定 Beat。",
            "action": "reuse",
        }],
        "selected": "reuse",
        "reason": "用户批准精确复用。",
        "user_approved": True,
        "user_response_text": "同意精确复用。",
    }
    decision_log = {
        "version": "1.0",
        "project_id": project_id,
        "decisions": [decision],
    }
    if field == "project_id":
        decision_log[field] = wrong_value
    else:
        decision[field] = wrong_value

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1", "S2"],
        ledger_entries=[{
            "path": "assets/images/shared.png",
            "beats": ["S1", "S2"],
        }],
        decision_log=decision_log,
    )

    assert result["reuse_pending"]
    assert result["ready"] is False


def test_matrix_rejects_conflicting_i2i_source_declarations(tmp_path):
    output_path = "assets/images/i2i.png"
    _image(tmp_path / output_path, (900, 900))
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        ledger_entries=[{"path": "assets/images/actual.png", "beats": ["S1"]}],
        planned_entries=[{
            "beats": ["S1"],
            "kind": "image",
            "origin": "i2i",
            "asset_source": "user_upload",
            "status": "ready",
            "review_status": "approved",
            "provider": "provider",
            "model": "model",
            "output_path": output_path,
        }],
        project_dir=tmp_path,
    )

    assert result["source_conflicts"]
    assert "source_declaration_conflict" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ({"provider": ""}, "provider_missing"),
        ({"model": ""}, "model_missing"),
        ({"review_status": "pending"}, "review_not_approved"),
        ({"path": "assets/images/missing.png"}, "output_missing_or_unsafe"),
        ({"asset_source": "user_upload"}, "source_declaration_conflict"),
    ],
)
def test_matrix_rejects_incomplete_actual_i2i(
    tmp_path,
    mutation,
    expected_reason,
):
    output_path = "assets/images/actual-i2i.png"
    _image(tmp_path / output_path, (900, 900))
    entry = {
        "path": output_path,
        "beats": ["S1"],
        "status": "confirmed",
        "origin": "i2i",
        "provider": "provider",
        "model": "model",
        "review_status": "approved",
    }
    entry.update(mutation)

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        ledger_entries=[entry],
        project_dir=tmp_path,
    )

    assert expected_reason in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


def test_matrix_accepts_complete_actual_i2i(tmp_path):
    project_id = "complete-actual-i2i"
    output_path = "assets/images/actual-i2i.png"
    _image(tmp_path / output_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1"],
            "status": "confirmed",
            "origin": "i2i",
            "provider": "provider",
            "model": "model",
            "review_status": "approved",
            "decision_id": "review-approved",
            "candidate_paths": [output_path],
        }],
        decision_log=_review_decision_log(
            project_id=project_id,
            path=output_path,
            beats=["S1"],
            project_dir=tmp_path,
        ),
        project_dir=tmp_path,
    )

    assert result["i2i_issues"] == []
    assert result["assigned"] == {"S1": [output_path]}
    assert result["ready"] is True


def test_matrix_rejects_generated_image_when_latest_review_revokes_approval(tmp_path):
    project_id = "revoked-generated-review"
    output_path = "assets/images/revoked.png"
    _image(tmp_path / output_path, (900, 900))
    decision_log = _review_decision_log(
        project_id=project_id,
        path=output_path,
        beats=["S1"],
        project_dir=tmp_path,
        decision_id="review-approved-old",
    )
    decision_log["decisions"].append({
        "decision_id": "review-rejected-new",
        "stage": "assets_gate",
        "category": "asset_decision",
        "subject": output_path,
        "asset_path": output_path,
        "beat_ids": ["S1"],
        "options_considered": [{
            "option_id": "rejected",
            "label": "撤回生成图",
            "score": 1.0,
            "reason": "用户撤回先前批准。",
        }],
        "selected": "rejected",
        "reason": "用户要求不再采用该图。",
        "user_approved": True,
        "user_response_text": "撤回这张图。",
    })

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1"],
            "status": "approved",
            "origin": "generated",
            "provider": "provider",
            "model": "model",
            "review_status": "approved",
            "decision_id": "review-approved-old",
            "candidate_paths": [output_path],
        }],
        decision_log=decision_log,
        project_dir=tmp_path,
    )

    assert "review_decision_invalid" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


def test_matrix_accepts_legacy_ready_user_upload_as_actual_image(tmp_path):
    output_path = "assets/images/uploaded.png"
    _image(tmp_path / output_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1"],
            "kind": "image",
            "origin": "user_upload",
            "status": "ready",
            "selected": True,
        }],
        project_dir=tmp_path,
    )

    assert result["i2i_issues"] == []
    assert result["assigned"] == {"S1": [output_path]}
    assert result["ready"] is True


def test_matrix_rejects_user_upload_label_when_generation_chain_fields_exist(tmp_path):
    output_path = "assets/images/disguised-generated.png"
    _image(tmp_path / output_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1"],
            "kind": "image",
            "origin": "user_upload",
            "status": "ready",
            "selected": True,
            "provider": "provider",
        }],
        project_dir=tmp_path,
    )

    assert "generated_chain_source_mismatch" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


def test_matrix_rejects_prefixed_image_path_with_disguised_generation_chain(tmp_path):
    output_path = "assets/images/prefixed-generated.png"
    _image(tmp_path / output_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": f"./{output_path}",
            "beats": ["S1"],
            "origin": "user_upload",
            "status": "ready",
            "selected": True,
            "provider": "provider",
        }],
        project_dir=tmp_path,
    )

    assert "generated_chain_source_mismatch" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


def test_matrix_rejects_generated_image_when_approved_content_changes(tmp_path):
    project_id = "changed-generated-content"
    output_path = "assets/images/changed.png"
    image_path = tmp_path / output_path
    _image(image_path, (900, 900))
    approved_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    decision_log = _review_decision_log(
        project_id=project_id,
        path=output_path,
        beats=["S1"],
        project_dir=tmp_path,
    )
    decision_log["decisions"][0]["asset_sha256"] = approved_sha256
    _image(image_path, (901, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1"],
            "status": "approved",
            "origin": "generated",
            "provider": "provider",
            "model": "model",
            "review_status": "approved",
            "decision_id": "review-approved",
            "candidate_paths": [output_path],
        }],
        decision_log=decision_log,
        project_dir=tmp_path,
    )

    assert "approved_content_changed" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


def test_matrix_rejects_generated_approval_with_subject_drifted_withdrawal(tmp_path):
    project_id = "subject-drifted-withdrawal"
    output_path = "assets/images/withdrawn.png"
    image_path = tmp_path / output_path
    _image(image_path, (900, 900))
    decision_log = _review_decision_log(
        project_id=project_id,
        path=output_path,
        beats=["S1"],
        project_dir=tmp_path,
    )
    decision_log["decisions"][0]["asset_sha256"] = hashlib.sha256(
        image_path.read_bytes()
    ).hexdigest()
    decision_log["decisions"].append({
        "decision_id": "review-withdrawn",
        "stage": "assets_gate",
        "category": "asset_decision",
        "subject": "用户改写了主题",
        "asset_path": output_path,
        "beat_ids": ["S1"],
        "options_considered": [{
            "option_id": "rejected",
            "label": "撤回",
            "score": 1.0,
            "reason": "不再采用。",
        }],
        "selected": "rejected",
        "reason": "用户撤回批准。",
        "user_approved": True,
        "user_response_text": "撤回。",
    })

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1"],
            "status": "approved",
            "origin": "generated",
            "provider": "provider",
            "model": "model",
            "review_status": "approved",
            "decision_id": "review-approved",
            "candidate_paths": [output_path],
        }],
        decision_log=decision_log,
        project_dir=tmp_path,
    )

    assert "review_decision_invalid" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


def test_matrix_normalizes_path_and_beat_order_for_drifted_withdrawal(tmp_path):
    project_id = "normalized-withdrawal-scope"
    output_path = "assets/images/withdrawn-multi.png"
    image_path = tmp_path / output_path
    _image(image_path, (900, 900))
    decision_log = _review_decision_log(
        project_id=project_id,
        path=output_path,
        beats=["S1", "S2"],
        project_dir=tmp_path,
    )
    decision_log["decisions"].append({
        "decision_id": "review-withdrawn-normalized",
        "stage": "assets_gate",
        "category": "asset_decision",
        "subject": "主题发生漂移",
        "asset_path": f"./{output_path}",
        "beat_ids": ["S2", "S1"],
        "options_considered": [{
            "option_id": "rejected",
            "label": "撤回",
            "score": 1.0,
            "reason": "不再采用。",
        }],
        "selected": "rejected",
        "reason": "用户撤回批准。",
        "user_approved": True,
        "user_response_text": "撤回。",
    })

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1", "S2"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1", "S2"],
            "status": "approved",
            "origin": "generated",
            "provider": "provider",
            "model": "model",
            "review_status": "approved",
            "decision_id": "review-approved",
            "candidate_paths": [output_path],
        }],
        decision_log=decision_log,
        project_dir=tmp_path,
    )

    assert "review_decision_invalid" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


def test_matrix_different_beat_scope_does_not_revoke_generated_approval(tmp_path):
    project_id = "independent-generated-scopes"
    output_path = "assets/images/scoped.png"
    image_path = tmp_path / output_path
    _image(image_path, (900, 900))
    decision_log = _review_decision_log(
        project_id=project_id,
        path=output_path,
        beats=["S1"],
        project_dir=tmp_path,
    )
    decision_log["decisions"].append({
        "decision_id": "review-rejected-other-beat",
        "stage": "assets_gate",
        "category": "asset_decision",
        "subject": output_path,
        "asset_path": output_path,
        "beat_ids": ["S2"],
        "options_considered": [{
            "option_id": "rejected",
            "label": "拒绝 S2",
            "score": 1.0,
            "reason": "仅拒绝 S2。",
        }],
        "selected": "rejected",
        "reason": "仅拒绝 S2。",
        "user_approved": True,
        "user_response_text": "只拒绝 S2。",
    })

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1"],
            "status": "approved",
            "origin": "generated",
            "provider": "provider",
            "model": "model",
            "review_status": "approved",
            "decision_id": "review-approved",
            "candidate_paths": [output_path],
        }],
        decision_log=decision_log,
        project_dir=tmp_path,
    )

    assert result["i2i_issues"] == []
    assert result["ready"] is True


def test_path_comparison_preserves_case_on_case_sensitive_filesystems(monkeypatch):
    monkeypatch.setattr(asset_precheck_mod, "_PATH_CASE_INSENSITIVE", False)

    upper = asset_precheck_mod._path_comparison_key(
        "assets/images/Hero.png",
        None,
    )
    lower = asset_precheck_mod._path_comparison_key(
        "assets/images/hero.png",
        None,
    )

    assert upper != lower


def test_path_comparison_folds_case_on_case_insensitive_filesystems(monkeypatch):
    monkeypatch.setattr(asset_precheck_mod, "_PATH_CASE_INSENSITIVE", True)

    upper = asset_precheck_mod._path_comparison_key(
        "assets/images/Hero.png",
        None,
    )
    lower = asset_precheck_mod._path_comparison_key(
        "assets/images/hero.png",
        None,
    )

    assert upper == lower


@pytest.mark.parametrize(
    "source_alias",
    [
        "generated",
        "t2i",
        "text_to_image",
        "i2i",
        "image_to_image",
        "ai_generated",
    ],
)
def test_matrix_requires_decision_for_every_generated_actual_alias(
    tmp_path,
    source_alias,
):
    output_path = f"assets/images/{source_alias}.png"
    _image(tmp_path / output_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1"],
            "status": "confirmed",
            "origin": source_alias,
            "provider": "provider",
            "model": "model",
            "review_status": "approved",
        }],
        project_dir=tmp_path,
    )

    assert "decision_id_missing" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


@pytest.mark.parametrize(
    "source_alias",
    [
        "generated",
        "t2i",
        "text_to_image",
        "i2i",
        "image_to_image",
        "ai_generated",
    ],
)
def test_matrix_rejects_ready_as_approval_for_every_generated_plan_alias(
    tmp_path,
    source_alias,
):
    output_path = f"assets/images/{source_alias}.png"
    _image(tmp_path / output_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        planned_entries=[{
            "beats": ["S1"],
            "kind": "image",
            "origin": source_alias,
            "status": "ready",
            "review_status": "approved",
            "decision_id": "review-approved",
            "provider": "provider",
            "model": "model",
            "candidate_paths": [output_path],
            "output_path": output_path,
        }],
        project_dir=tmp_path,
    )

    assert "status_not_approved" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


def test_matrix_treats_generated_aliases_as_one_source(tmp_path):
    project_id = "generated-aliases"
    output_path = "assets/images/generated-approved.png"
    _image(tmp_path / output_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        planned_entries=[{
            "beats": ["S1"],
            "kind": "image",
            "origin": "t2i",
            "asset_source": "image_to_image",
            "status": "approved",
            "review_status": "approved",
            "decision_id": "review-approved",
            "provider": "provider",
            "model": "model",
            "candidate_paths": [output_path],
            "output_path": output_path,
        }],
        decision_log=_review_decision_log(
            project_id=project_id,
            path=output_path,
            beats=["S1"],
            project_dir=tmp_path,
        ),
        project_dir=tmp_path,
    )

    assert result["source_conflicts"] == []
    assert result["assigned"] == {"S1": [output_path]}
    assert result["ready"] is True


@pytest.mark.parametrize("location", ["actual", "planned"])
def test_matrix_rejects_approved_generated_without_candidate_paths(
    tmp_path,
    location,
):
    project_id = f"missing-candidates-{location}"
    output_path = "assets/images/approved.png"
    _image(tmp_path / output_path, (900, 900))
    common = {
        "beats": ["S1"],
        "origin": "generated",
        "provider": "provider",
        "model": "model",
        "review_status": "approved",
        "decision_id": "review-approved",
    }
    ledger_entries = [{
        **common,
        "path": output_path,
        "status": "confirmed",
    }] if location == "actual" else []
    planned_entries = [{
        **common,
        "kind": "image",
        "status": "approved",
        "output_path": output_path,
    }] if location == "planned" else []

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        ledger_entries=ledger_entries,
        planned_entries=planned_entries,
        decision_log=_review_decision_log(
            project_id=project_id,
            path=output_path,
            beats=["S1"],
            project_dir=tmp_path,
        ),
        project_dir=tmp_path,
    )

    assert "candidate_paths_missing" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False


@pytest.mark.parametrize(
    ("scenario", "decision_patch", "log_project_id", "entry_decision_id"),
    [
        ("fake-id", {}, "review-scope", "missing-decision"),
        ("old-project", {}, "other-project", "review-approved"),
        ("old-beats", {"beat_ids": ["S9"]}, "review-scope", "review-approved"),
        (
            "asset-path-mismatch",
            {"asset_path": "assets/images/other.png"},
            "review-scope",
            "review-approved",
        ),
        (
            "subject-mismatch",
            {"subject": "assets/images/other.png"},
            "review-scope",
            "review-approved",
        ),
    ],
)
def test_matrix_rejects_invalid_generated_review_decision(
    tmp_path,
    scenario,
    decision_patch,
    log_project_id,
    entry_decision_id,
):
    project_id = "review-scope"
    output_path = "assets/images/approved.png"
    _image(tmp_path / output_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1"],
            "status": "confirmed",
            "origin": "generated",
            "provider": "provider",
            "model": "model",
            "review_status": "approved",
            "decision_id": entry_decision_id,
            "candidate_paths": [output_path],
        }],
        decision_log=_review_decision_log(
            project_id=log_project_id,
            path=output_path,
            beats=["S1"],
            project_dir=tmp_path,
            decision_patch=decision_patch,
        ),
        project_dir=tmp_path,
    )

    assert "review_decision_invalid" in result["i2i_issues"][0]["reasons"]
    assert result["ready"] is False, scenario


@pytest.mark.parametrize("location", ["actual", "planned"])
def test_matrix_accepts_generated_with_real_candidate_and_scoped_review(
    tmp_path,
    location,
):
    project_id = f"approved-{location}"
    output_path = "assets/images/approved.png"
    _image(tmp_path / output_path, (900, 900))
    common = {
        "beats": ["S1"],
        "origin": "generated",
        "provider": "provider",
        "model": "model",
        "review_status": "approved",
        "decision_id": "review-approved",
        "candidate_paths": [output_path],
    }

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            **common,
            "path": output_path,
            "status": "confirmed",
        }] if location == "actual" else [],
        planned_entries=[{
            **common,
            "kind": "image",
            "status": "approved",
            "output_path": output_path,
        }] if location == "planned" else [],
        decision_log=_review_decision_log(
            project_id=project_id,
            path=output_path,
            beats=["S1"],
            project_dir=tmp_path,
        ),
        project_dir=tmp_path,
    )

    assert result["i2i_issues"] == []
    assert result["assigned"] == {"S1": [output_path]}
    assert result["ready"] is True


def test_matrix_rejects_candidate_outside_project_and_output_not_candidate(
    tmp_path,
):
    project_id = "unsafe-candidates"
    output_path = "assets/images/approved.png"
    _image(tmp_path / output_path, (900, 900))

    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id=project_id,
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": output_path,
            "beats": ["S1"],
            "status": "confirmed",
            "origin": "generated",
            "provider": "provider",
            "model": "model",
            "review_status": "approved",
            "decision_id": "review-approved",
            "candidate_paths": [
                "assets/images/other.png",
                "../outside.png",
            ],
        }],
        decision_log=_review_decision_log(
            project_id=project_id,
            path=output_path,
            beats=["S1"],
            project_dir=tmp_path,
        ),
        project_dir=tmp_path,
    )

    reasons = result["i2i_issues"][0]["reasons"]
    assert "approved_output_not_candidate" in reasons
    assert "candidate_path_unsafe" in reasons
    assert result["ready"] is False


def test_matrix_does_not_resolve_plan_decision_before_generated_approval(
    tmp_path,
):
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        project_id="planned-not-reviewed",
        canonical_beat_ids=["S1"],
        planned_entries=[{
            "beats": ["S1"],
            "kind": "image",
            "origin": "i2i",
            "status": "planned",
            "review_status": "pending",
            "decision_id": "plan-decision-not-in-review-log",
            "provider": "provider",
            "model": "model",
            "candidate_paths": [],
            "planned_output_path": "assets/images/planned.png",
        }],
        decision_log={
            "version": "1.0",
            "project_id": "planned-not-reviewed",
            "decisions": [],
        },
        project_dir=tmp_path,
    )

    reasons = result["i2i_issues"][0]["reasons"]
    assert "review_decision_invalid" not in reasons
    assert "candidate_paths_missing" not in reasons
    assert result["ready"] is False


def test_matrix_rejects_conflicting_legacy_and_current_beat_fields():
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        canonical_beat_ids=["S1"],
        ledger_entries=[{
            "path": "assets/images/a.png",
            "beat": "S9",
            "beats": ["S1"],
        }],
    )

    assert result["beat_reference_conflicts"]
    assert result["ready"] is False


@pytest.mark.parametrize(
    ("segment_ids", "plan_ids"),
    [
        (["S1", "S1"], ["S1"]),
        (["S1"], ["S1", "S1"]),
        (["S1", "S2"], ["S1", "S3"]),
    ],
)
def test_matrix_rejects_duplicate_or_mismatched_canonical_ids(
    segment_ids,
    plan_ids,
):
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        segment_cards={
            "segments": [{"beat": beat_id} for beat_id in segment_ids],
        },
        video_plan={
            "segments": [{"id": beat_id} for beat_id in plan_ids],
        },
        ledger_entries=[
            {"path": f"assets/images/{beat_id}.png", "beats": [beat_id]}
            for beat_id in {"S1", "S2", "S3"}
        ],
    )

    assert result["canonical_source_conflicts"]
    assert result["ready"] is False


@pytest.mark.parametrize(
    "video_plan",
    [
        {
            "segments": [{"id": "S1"}],
            "beats": [{"id": "S2"}],
        },
        {
            "segments": [{"id": "S1", "beat": "S2"}],
        },
    ],
)
def test_matrix_rejects_conflicting_video_plan_keys(video_plan):
    result = asset_precheck_mod.validate_beat_assignment_matrix(
        segment_cards={"segments": [{"beat": "S1"}]},
        video_plan=video_plan,
        ledger_entries=[{
            "path": "assets/images/actual.png",
            "beats": ["S1"],
            "status": "confirmed",
        }],
    )

    assert result["canonical_source_conflicts"]
    assert result["ready"] is False


def test_validate_beat_assignment_matrix_classifies_all_assignment_states():
    validate_matrix = getattr(
        asset_precheck_mod,
        "validate_beat_assignment_matrix",
    )
    result = validate_matrix(
        project_id="reuse-approved",
        canonical_beat_ids=["S1", "S2", "S3", "S4", "S5", "S6"],
        ledger_entries=[
            {"path": "assets/images/01.png", "beat": "S1,S4"},
            {"path": "assets/images/02.png", "beat": ["S2", "S6"]},
            {"path": "assets/images/04.png", "beat": "S3"},
            {"path": "assets/images/05.png"},
            {"path": "assets/images/orphan.png", "beat": "S9"},
        ],
    )

    assert result["assigned"] == {
        "S1": ["assets/images/01.png"],
        "S2": ["assets/images/02.png"],
        "S3": ["assets/images/04.png"],
        "S4": ["assets/images/01.png"],
        "S6": ["assets/images/02.png"],
    }
    assert result["missing"] == ["S5"]
    assert result["unused"] == ["assets/images/05.png"]
    assert result["orphan"] == [{
        "path": "assets/images/orphan.png",
        "beat_ids": ["S9"],
    }]
    assert result["reuse_pending"] == [
        {
            "path": "assets/images/01.png",
            "beat_ids": ["S1", "S4"],
        },
        {
            "path": "assets/images/02.png",
            "beat_ids": ["S2", "S6"],
        },
    ]
    assert result["ready"] is False


def test_validate_beat_assignment_matrix_is_ready_after_reuse_decision():
    validate_matrix = getattr(
        asset_precheck_mod,
        "validate_beat_assignment_matrix",
    )
    ledger_entries = [
        {"path": "assets/images/01.png", "beat": "S1,S4"},
        {"path": "assets/images/02.png", "beat": "S2"},
        {"path": "assets/images/03.png", "beat": "S3"},
        {"path": "assets/images/04.png", "beat": "S5"},
        {"path": "assets/images/06.png", "beat": "S6"},
        {"path": "assets/images/05.png"},
    ]
    decision_log = {
        "version": "1.0",
        "project_id": "reuse-approved",
        "decisions": [{
            "decision_id": "d-asset-reuse-01",
            "stage": "assets_gate",
            "category": "asset_decision",
            "subject": "assets/images/01.png",
            "asset_path": "assets/images/01.png",
            "beat_ids": ["S1", "S4"],
            "options_considered": [
                {
                    "option_id": "approved",
                    "label": "批准跨 Beat 复用",
                    "score": 1.0,
                    "reason": "同一真实商品图可覆盖 S1 与 S4。",
                    "action": "reuse",
                },
                {
                    "option_id": "rejected",
                    "label": "不复用并补图",
                    "score": 0.4,
                    "reason": "可避免重复，但当前闭环无需新增图片。",
                    "rejected_because": "用户已批准复用现有真实商品图。",
                    "action": "do_not_reuse",
                },
            ],
            "selected": "approved",
            "reason": "用户确认 01.png 可同时用于 S1 与 S4。",
            "user_visible": True,
            "user_approved": True,
            "user_response_text": "同意 01.png 在 S1 与 S4 复用。",
        }],
    }
    result = validate_matrix(
        project_id="reuse-approved",
        canonical_beat_ids=["S1", "S2", "S3", "S4", "S5", "S6"],
        ledger_entries=ledger_entries,
        decision_log=decision_log,
    )

    assert result["reuse_pending"] == []
    assert result["unused"] == ["assets/images/05.png"]
    assert result["ready"] is True

    decision = decision_log["decisions"][0]
    decision["selected"] = "rejected"
    decision["reason"] = "用户选择不复用并补图。"
    decision["user_response_text"] = "不同意复用，请补图。"
    rejected = validate_matrix(
        project_id="reuse-approved",
        canonical_beat_ids=["S1", "S2", "S3", "S4", "S5", "S6"],
        ledger_entries=ledger_entries,
        decision_log=decision_log,
    )
    assert rejected["reuse_pending"]
    assert rejected["ready"] is False


def test_validate_beat_assignment_matrix_blocks_incomplete_i2i(tmp_path):
    validate_matrix = getattr(
        asset_precheck_mod,
        "validate_beat_assignment_matrix",
    )
    output_path = "assets/images/i2i-S6.png"
    result = validate_matrix(
        canonical_beat_ids=["S1", "S2", "S3", "S4", "S5", "S6"],
        ledger_entries=[
            {"path": f"assets/images/{beat}.png", "beat": beat}
            for beat in ("S1", "S2", "S3", "S4", "S5", "S6")
        ],
        planned_entries=[{
            "beat": "S6",
            "kind": "image",
            "origin": "i2i",
            "status": "ready",
            "review_status": "pending",
            "output_path": output_path,
        }],
        project_dir=tmp_path,
    )

    assert result["i2i_review_pending"] == [{
        "beat": "S6",
        "path": output_path,
    }]
    assert result["i2i_issues"] == [{
        "beat": "S6",
        "path": output_path,
        "reasons": [
            "status_not_approved",
            "review_not_approved",
            "provider_missing",
            "model_missing",
        ],
    }]
    assert result["ready"] is False

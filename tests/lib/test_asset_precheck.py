"""Tests for the read-only commercial image precheck."""

from __future__ import annotations

from PIL import Image

from lib.asset_precheck import (
    build_asset_ledger,
    build_asset_requirements,
    duration_profile,
    scan_user_images,
)


def _image(path, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color="white").save(path)


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
        for key in ("beat", "kind", "origin", "selected", "label_zh")
    } == {
        "beat": "beat_01",
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

    assert ledger["planned_entries"] == planned_entries

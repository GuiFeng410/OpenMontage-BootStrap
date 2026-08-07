"""Tests for the read-only commercial image precheck."""

from __future__ import annotations

from PIL import Image

from lib.asset_precheck import scan_user_images


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
    assert report["summary"] == {
        "total_images": 3,
        "low_resolution_count": 1,
        "duplicate_group_count": 1,
        "needs_user_attention": True,
    }
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

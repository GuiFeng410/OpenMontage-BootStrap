"""Tests for optional commercial asset vision assist."""

from __future__ import annotations

from PIL import Image

from lib.asset_precheck import scan_user_images
from lib.asset_vision import describe_project_user_images, merge_vision_into_precheck


def _image(path, size=(800, 800)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color="white").save(path)


def test_describe_degrades_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    project = tmp_path / "p1"
    _image(project / "assets" / "images" / "item.png")

    result = describe_project_user_images(project)

    assert result["vision_available"] is False
    assert result["vision_degraded"] is True
    assert result["precheck"]["summary"]["total_images"] == 1
    assert "降级" in result["message_zh"]


def test_merge_vision_fills_empty_suggested_class():
    precheck = {
        "version": "1.0",
        "entries": [
            {
                "file": "a.png",
                "path": "assets/images/a.png",
                "suggested_class": "",
                "issues": [],
            }
        ],
        "summary": {
            "total_images": 1,
            "low_resolution_count": 0,
            "duplicate_group_count": 0,
            "needs_user_attention": True,
            "counts_by_suggested_class": {"unclassified": 1},
        },
    }
    merged = merge_vision_into_precheck(
        precheck,
        [
            {
                "file": "a.png",
                "suggested_class": "product_hero",
                "description_zh": "银色手镯正面",
                "confidence": 0.9,
                "risks_zh": [],
            }
        ],
        model="qwen-vl-max",
    )
    entry = merged["entries"][0]
    assert entry["suggested_class"] == "product_hero"
    assert entry["vision_description_zh"] == "银色手镯正面"
    assert merged["summary"]["vision_enriched"] is True


def test_scan_still_works_alongside_vision_helpers(tmp_path):
    project = tmp_path / "p2"
    _image(project / "assets" / "images" / "hero_main.png")
    report = scan_user_images(project)
    assert report["entries"][0]["suggested_class"] == "product_hero"

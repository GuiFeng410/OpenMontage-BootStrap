"""Tests for identity-aware prompt construction without cloud calls."""

from __future__ import annotations

from lib.product_identity import load_manifest
from lib.shot_prompt_builder import (
    build_batch_prompts,
    build_product_negative_prompt,
    build_product_prompt,
    build_shot_prompt,
)


def test_product_prompt_injects_identity_and_angle():
    manifest = {
        "product_id": "demo-bangle",
        "product_name": "Demo bangle",
        "identity_anchor": {
            "primary_color": "pale icy-green",
            "forbidden_changes": ["no deep emerald drift"],
            "geometry_constraints": ["closed ring", "uniform thickness"],
        },
    }
    scene = {
        "description": "jade bangle on a pale stone plinth",
        "angle": "three-quarter low angle",
        "shot_language": {"shot_size": "close_up", "camera_movement": "dolly_in"},
    }

    prompt = build_product_prompt(scene, manifest, angle=scene["angle"])

    assert "pale icy-green" in prompt
    assert "closed ring" in prompt
    assert "three-quarter low angle" in prompt
    assert "no deep emerald drift" in prompt


def test_batch_prompts_remain_legacy_compatible():
    scene = {"id": "scene01", "description": "a jade bangle", "type": "product"}
    assert build_batch_prompts([scene])[0]["prompt"] == build_shot_prompt(scene)


def test_loaded_manifest_can_drive_negative_prompt():
    manifest = load_manifest(
        "projects/tianshancui-bangle-v6/products/tianshancui-bangle/identity_anchor.json"
    )

    negative = build_product_negative_prompt(manifest)

    assert negative.startswith("Do not:")
    assert "deep emerald green" in negative

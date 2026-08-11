"""Browser regressions from the Backlot UI bug bash."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

import pytest

from scripts import backlot_screenshot_stage


pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402


@pytest.fixture(scope="module")
def staged_backlot_server():
    backlot_screenshot_stage.build_stage()
    port = 4897
    env = dict(os.environ)
    env["OPENMONTAGE_PROJECTS_DIR"] = str(backlot_screenshot_stage.STAGE_DIR)
    server = subprocess.Popen(
        [sys.executable, "-m", "backlot", "serve", "--port", str(port)],
        cwd=backlot_screenshot_stage.REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1):
                break
        except Exception:
            time.sleep(0.2)
    else:
        server.terminate()
        raise RuntimeError("Backlot server did not become healthy")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


def test_project_pages_fit_mobile_and_tablet_widths(staged_backlot_server):
    project_paths = [
        "/p/signal-in-the-static?static=1",
        "/p/the-slow-orchard?static=1",
        "/p/the-last-lighthouse?static=1",
        "/p/paper-boats?static=1",
    ]
    viewports = [
        {"width": 390, "height": 844},
        {"width": 768, "height": 1024},
    ]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            for viewport in viewports:
                page.set_viewport_size(viewport)
                for path in project_paths:
                    page.goto(staged_backlot_server + path, wait_until="networkidle")
                    page.wait_for_timeout(300)
                    sizes = page.evaluate(
                        """() => ({
                            scrollWidth: document.documentElement.scrollWidth,
                            clientWidth: document.documentElement.clientWidth
                        })"""
                    )
                    assert sizes["scrollWidth"] <= sizes["clientWidth"], (
                        path,
                        viewport,
                        sizes,
                    )
        finally:
            browser.close()


def test_static_navigation_invalid_route_and_active_takes(staged_backlot_server):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1560, "height": 1000})
        try:
            page.goto(staged_backlot_server + "/?static=1", wait_until="networkidle")
            href = page.locator("a.lib-card").first.get_attribute("href")
            assert href and "static=1" in href

            response = page.goto(
                staged_backlot_server + "/p/..%2FAGENT_GUIDE.md?static=1",
                wait_until="networkidle",
            )
            assert response and response.status == 200
            assert "PROJECT NOT FOUND" in page.locator("body").inner_text()

            page.goto(staged_backlot_server + "/p/the-last-lighthouse?static=1", wait_until="networkidle")
            page.wait_for_timeout(300)
            assert page.locator(".takes .tk.active").count() >= 1
        finally:
            browser.close()


def test_missing_commercial_media_does_not_render_video_player(staged_backlot_server):
    project = backlot_screenshot_stage.STAGE_DIR / "missing-commercial-media"
    (project / "artifacts").mkdir(parents=True, exist_ok=True)
    (project / "project.json").write_text(
        json.dumps({
            "project_id": "missing-commercial-media",
            "title": "缺失媒体",
            "pipeline_type": "bootstrap-commercial",
        }),
        encoding="utf-8",
    )
    (project / "artifacts" / "segment_cards.json").write_text(
        json.dumps({
            "version": "1.0",
            "duration_seconds": 5,
            "overall_prompt_zh": "商品亮相",
            "segments": [{
                "beat": "beat_01",
                "time": "0-5",
                "copy_plan_zh": "商品亮相",
                "shot_plan_zh": "慢推",
                "asset_plan_zh": "使用试片",
            }],
        }),
        encoding="utf-8",
    )
    (project / "artifacts" / "review_overview.json").write_text(
        json.dumps({
            "overview": [{
                "beat": "beat_01",
                "time": "0-5",
                "asset": "missing-beat.mp4",
            }],
        }),
        encoding="utf-8",
    )
    (project / "artifacts" / "sample_reel.json").write_text(
        json.dumps({"path": "assets/video/missing-sample.mp4", "status": "review"}),
        encoding="utf-8",
    )
    (project / "checkpoint_sample_review.json").write_text(
        json.dumps({
            "stage": "sample_review",
            "status": "in_progress",
            "timestamp": "2026-08-11T00:00:00Z",
            "artifacts": {},
        }),
        encoding="utf-8",
    )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                staged_backlot_server + "/p/missing-commercial-media?static=1",
                wait_until="networkidle",
            )
            assert page.locator("video").count() == 0
            assert "媒体文件不存在" in page.locator("body").inner_text()
        finally:
            browser.close()

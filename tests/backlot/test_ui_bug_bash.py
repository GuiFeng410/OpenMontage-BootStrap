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
        browser = pw.chromium.launch(channel="chrome", headless=True)
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
        browser = pw.chromium.launch(channel="chrome", headless=True)
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
        browser = pw.chromium.launch(channel="chrome", headless=True)
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


def test_commercial_asset_lists_are_collapsed_and_thumbnails_stay_compact(
    staged_backlot_server,
):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                staged_backlot_server + "/p/commercial-task3?static=1",
                wait_until="networkidle",
            )
            page.locator(".stage").filter(has_text="素材检查").click()

            asset_details = page.locator("details.commercial-assets-details")
            assert asset_details.count() == 1
            assert asset_details.evaluate("(node) => node.open") is False
            asset_panel = page.locator(".commercial-assets-panel")
            assert "共 4 张" in asset_panel.inner_text()
            assert "身份基准" in asset_panel.inner_text()
            assert "角度图" in asset_panel.inner_text()

            precheck_details = page.locator(".commercial-precheck-panel details")
            assert precheck_details.count() == 1
            assert precheck_details.evaluate("(node) => node.open") is False

            asset_details.locator("summary").click()
            height = page.locator(".commercial-assets-details .asset-card img").first.evaluate(
                "(img) => img.getBoundingClientRect().height"
            )
            assert 0 < height <= 180

            page.set_viewport_size({"width": 390, "height": 844})
            mobile_height = page.locator(
                ".commercial-assets-details .asset-card img"
            ).first.evaluate("(img) => img.getBoundingClientRect().height")
            assert 0 < mobile_height <= 150
        finally:
            browser.close()


def test_commercial_stage_evidence_retry_copy_and_generation_details(
    staged_backlot_server,
):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        try:
            page.goto(
                staged_backlot_server + "/p/commercial-task3?static=1",
                wait_until="networkidle",
            )
            sample_stage = page.locator(".stage").filter(has_text="试片确认")
            assert "重试中·此前已通过" in sample_stage.inner_text()

            evidence = page.locator(".commercial-stage-evidence")
            assert "项目相对路径" in evidence.inner_text()
            assert "renders/task3_sample.mp4" in evidence.inner_text()
            player = page.locator(".render-hero video")
            assert player.count() == 1
            assert "renders/task3_sample.mp4" in (player.get_attribute("src") or "")
            page.wait_for_function(
                """() => {
                    const video = document.querySelector(".render-hero video");
                    return video && video.readyState >= 1;
                }"""
            )
            assert player.evaluate(
                """async (video) => {
                    await video.play();
                    return !video.paused;
                }"""
            ) is True

            plan = page.locator("details.beat-plan-fold")
            assert plan.count() >= 1
            assert plan.first.evaluate("(node) => node.open") is False
            plan.first.locator("summary").click()
            plan_text = plan.first.inner_text()
            assert "一眼认出产品" in plan_text
            assert "中景缓慢环绕" in plan_text
            assert "商标稳定" in plan_text
            assert "fal" in plan_text
            assert "kling-v2.1" in plan_text
            assert "Agnes" not in page.locator(".commercial-beat-card").inner_text()

            page.locator(".stage").filter(has_text="素材检查").click()
            assert "这条旧提示在阶段完成后不得显示" not in page.locator(
                ".commercial-drawer"
            ).inner_text()

            page.locator(".stage").filter(has_text="初稿审查").click()
            draft_evidence = page.locator(".commercial-stage-evidence")
            assert "项目相对路径" in draft_evidence.inner_text()
            assert "renders/task3_full_draft.mp4" in draft_evidence.inner_text()
            assert "renders/task3_full_draft.mp4" in (
                page.locator(".render-hero video").get_attribute("src") or ""
            )
        finally:
            browser.close()


def test_legacy_sample_and_draft_candidates_warn_without_impersonating_evidence(
    staged_backlot_server,
):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                staged_backlot_server + "/p/commercial-task3-legacy?static=1",
                wait_until="networkidle",
            )
            body = page.locator("body").inner_text()
            assert "未挂接阶段证据" in body
            assert "renders/legacy_sample_preview.mp4" in body
            assert "renders/legacy_sample_preview.mp4" in (
                page.locator(".render-hero video").get_attribute("src") or ""
            )

            page.locator(".stage").filter(has_text="初稿审查").click()
            draft_body = page.locator("body").inner_text()
            assert "未挂接阶段证据" in draft_body
            assert "renders/legacy_full_draft_preview.mp4" in draft_body
            assert "renders/legacy_full_draft_preview.mp4" in (
                page.locator(".render-hero video").get_attribute("src") or ""
            )
        finally:
            browser.close()


def test_eventsource_failure_falls_back_to_polling_without_page_reload(
    staged_backlot_server,
):
    project = backlot_screenshot_stage.STAGE_DIR / "commercial-task3-polling"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.route(
                "**/api/project/commercial-task3-polling/events",
                lambda route: route.abort(),
            )
            page.goto(
                staged_backlot_server + "/p/commercial-task3-polling",
                wait_until="domcontentloaded",
            )
            page.wait_for_selector(".commercial-board")
            assert page.locator(".render-hero video").count() == 0
            page.evaluate("window.__task3NoReload = 73")

            (project / "artifacts" / "sample_reel.json").write_text(
                json.dumps({
                    "version": "1.0",
                    "path": "renders/poll-ready.mp4",
                    "duration_seconds": 2,
                    "status": "review",
                }),
                encoding="utf-8",
            )
            (project / "checkpoint_sample_review.json").write_text(
                json.dumps({
                    "version": "1.0",
                    "project_id": project.name,
                    "pipeline_type": "bootstrap-commercial",
                    "stage": "sample_review",
                    "status": "awaiting_human",
                    "timestamp": "2026-08-11T09:00:00Z",
                    "artifacts": {},
                }),
                encoding="utf-8",
            )

            page.wait_for_selector(".render-hero video", timeout=10000)
            assert page.evaluate("window.__task3NoReload") == 73
            assert "renders/poll-ready.mp4" in (
                page.locator(".render-hero video").get_attribute("src") or ""
            )
            assert "等你聊天确认" in page.locator(".stage").filter(
                has_text="试片确认"
            ).inner_text()
            assert "自动轮询" in page.locator(".sse-banner").inner_text()

            page.evaluate(
                """() => {
                    const current = document.querySelector(".render-hero video");
                    current.currentTime = 0.5;
                    current.pause();
                    window.__commercialPlayerReplacementCount = 0;
                    window.__commercialPlayerSamples = [];
                    window.__commercialPlayerLastNode = current;
                    const observer = new MutationObserver(() => {
                        const video = document.querySelector(".render-hero video");
                        if (!video || video === window.__commercialPlayerLastNode) return;
                        window.__commercialPlayerLastNode = video;
                        window.__commercialPlayerReplacementCount += 1;
                        setTimeout(() => {
                            window.__commercialPlayerSamples.push({
                                currentTime: video.currentTime,
                                paused: video.paused,
                            });
                        }, 250);
                    });
                    observer.observe(document.getElementById("app"), {
                        childList: true,
                        subtree: true,
                    });
                    window.__commercialPlayerObserver = observer;
                }"""
            )
            page.wait_for_function(
                "() => window.__commercialPlayerReplacementCount >= 2",
                timeout=12000,
            )
            page.wait_for_timeout(500)
            playback = page.evaluate(
                """() => ({
                    currentTime: document.querySelector(".render-hero video").currentTime,
                    paused: document.querySelector(".render-hero video").paused,
                    samples: window.__commercialPlayerSamples,
                })"""
            )
            assert playback["currentTime"] >= 0.45
            assert playback["paused"] is True
            assert len(playback["samples"]) >= 2
            assert all(item["currentTime"] >= 0.45 for item in playback["samples"])
            assert all(item["paused"] is True for item in playback["samples"])

            (project / "checkpoint_sample_review.json").write_text(
                json.dumps({
                    "version": "1.0",
                    "project_id": project.name,
                    "pipeline_type": "bootstrap-commercial",
                    "stage": "sample_review",
                    "status": "completed",
                    "timestamp": "2026-08-11T09:05:00Z",
                    "human_approved": True,
                    "artifacts": {},
                    "metadata": {
                        "decision_prompt_zh": "完成后不得继续显示的旧提示",
                    },
                }),
                encoding="utf-8",
            )
            sample_stage = page.locator(".stage").filter(has_text="试片确认")
            page.wait_for_function(
                """() => [...document.querySelectorAll(".stage")]
                    .some((node) => node.textContent.includes("试片确认")
                        && node.textContent.includes("已通过"))""",
                timeout=10000,
            )
            assert "重试中" not in sample_stage.inner_text()
            assert "完成后不得继续显示的旧提示" not in page.locator("body").inner_text()
        finally:
            browser.close()

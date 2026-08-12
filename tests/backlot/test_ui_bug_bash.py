"""Browser regressions from the Backlot UI bug bash."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from scripts import backlot_screenshot_stage


playwright_sync = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync.sync_playwright
expect = playwright_sync.expect


def _available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def staged_backlot_server(tmp_path_factory):
    original_stage_dir = backlot_screenshot_stage.STAGE_DIR
    original_projects_dir = os.environ.get("OPENMONTAGE_PROJECTS_DIR")
    stage_dir = tmp_path_factory.mktemp("backlot-screenshot-stage")
    server = None
    try:
        backlot_screenshot_stage.STAGE_DIR = stage_dir
        os.environ["OPENMONTAGE_PROJECTS_DIR"] = str(stage_dir)
        backlot_screenshot_stage.build_stage()
        port = _available_local_port()
        env = dict(os.environ)
        env["OPENMONTAGE_PROJECTS_DIR"] = str(stage_dir)
        server = subprocess.Popen(
            [sys.executable, "-m", "backlot", "serve", "--port", str(port)],
            cwd=backlot_screenshot_stage.REPO_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            return_code = server.poll()
            if return_code is not None:
                raise RuntimeError(
                    f"Backlot server exited before becoming healthy (code {return_code})"
                )
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/health",
                    timeout=1,
                ):
                    break
            except Exception:
                time.sleep(0.2)
        else:
            server.terminate()
            raise RuntimeError("Backlot server did not become healthy")

        yield f"http://127.0.0.1:{port}"
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        backlot_screenshot_stage.STAGE_DIR = original_stage_dir
        if original_projects_dir is None:
            os.environ.pop("OPENMONTAGE_PROJECTS_DIR", None)
        else:
            os.environ["OPENMONTAGE_PROJECTS_DIR"] = original_projects_dir


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _copy_fixture_video(destination: Path) -> None:
    source = (
        backlot_screenshot_stage.STAGE_DIR
        / "commercial-task3"
        / "renders"
        / "task3_sample.mp4"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


COMMERCIAL_STAGE_ORDER = (
    "brief_locked",
    "assets_gate",
    "sample_review",
    "segment_build",
    "draft_review",
    "final_compose",
    "delivery_signoff",
)


def _write_commercial_checkpoint(
    project: Path,
    stage: str,
    status: str,
    artifacts: dict,
    sequence: int,
) -> None:
    _write_json(project / f"checkpoint_{stage}.json", {
        "version": "1.0",
        "project_id": project.name,
        "pipeline_type": "bootstrap-commercial",
        "stage": stage,
        "status": status,
        "timestamp": f"2026-08-12T00:{sequence:02d}:00Z",
        "human_approved": status == "completed",
        "artifacts": artifacts,
    })


def _stage_segment_evidence_project(
    *,
    include_sample_beat_ids: bool = True,
    include_planned_entries: bool = False,
) -> str:
    project_id = "commercial-segment-contract"
    project = backlot_screenshot_stage.STAGE_DIR / project_id
    if project.exists():
        shutil.rmtree(project)
    (project / "artifacts").mkdir(parents=True)
    _write_json(project / "project.json", {
        "project_id": project_id,
        "title": "分段证据契约",
        "pipeline_type": "bootstrap-commercial",
    })
    for rel in (
        "assets/video/beat_01.mp4",
        "assets/video/beat_02.mp4",
        "assets/video/sample_only.mp4",
    ):
        _copy_fixture_video(project / rel)
    _write_json(project / "artifacts" / "video_plan.json", {
        "segments": [
            {"id": "beat_01", "t": "0-4", "purpose": "开场"},
            {"id": "beat_02", "t": "4-8", "purpose": "收束"},
        ],
    })
    _write_json(project / "artifacts" / "review_overview.json", {
        "overview": [
            {
                "beat": "beat_01",
                "time": "0-4",
                "output_path": "assets/video/beat_01.mp4",
            },
            {
                "beat": "beat_02",
                "time": "4-8",
                "output_path": "assets/video/beat_02.mp4",
            },
        ],
    })
    sample_reel = {
        "path": "assets/video/sample_only.mp4",
        "status": "approved",
    }
    if include_sample_beat_ids:
        sample_reel["beat_ids"] = ["beat_01"]
    _write_json(project / "artifacts" / "sample_reel.json", sample_reel)
    if include_planned_entries:
        (project / "assets" / "images" / "planned.png").parent.mkdir(
            parents=True, exist_ok=True
        )
        (project / "assets" / "images" / "planned.png").write_bytes(b"image")
        _copy_fixture_video(project / "assets" / "video" / "planned.mp4")
        _write_json(project / "artifacts" / "asset_ledger.json", {
            "entries": [],
            "planned_entries": [
                {
                    "beat": "beat_01",
                    "kind": "image",
                    "status": "ready",
                    "output_path": "assets/images/planned.png",
                },
                {
                    "beat": "beat_01",
                    "kind": "video",
                    "status": "ready",
                    "output_path": "assets/video/planned.mp4",
                },
            ],
        })
    _write_json(project / "checkpoint_sample_review.json", {
        "stage": "sample_review",
        "status": "completed",
        "human_approved": True,
        "timestamp": "2026-08-12T00:00:00Z",
        "artifacts": {},
    })
    _write_json(project / "checkpoint_segment_build.json", {
        "stage": "segment_build",
        "status": "in_progress",
        "timestamp": "2026-08-12T00:01:00Z",
        "artifacts": {},
    })
    return project_id


def _stage_edit_gate_project(
    scenario: str,
    *,
    stage: str = "draft_review",
    full_draft: bool = True,
    cuts: bool = True,
    latest_render: bool = True,
    source_exists: bool = True,
    dirty_cuts: bool = False,
) -> str:
    project_id = f"commercial-edit-gate-{scenario}"
    project = backlot_screenshot_stage.STAGE_DIR / project_id
    if project.exists():
        shutil.rmtree(project)
    (project / "artifacts").mkdir(parents=True)
    _write_json(project / "project.json", {
        "version": "1.0",
        "project_id": project_id,
        "title": f"剪辑门禁 {scenario}",
        "pipeline_type": "bootstrap-commercial",
    })
    source_paths = (
        ["assets/video/cut_01.mp4", "assets/video/cut_02_missing.mp4"]
        if not source_exists
        else ["assets/video/cut_01.mp4"]
    )
    edit_cuts = [
        {
            "id": f"cut_{index:02d}",
            "source": source_path,
            "in_seconds": 0,
            "out_seconds": 2,
        }
        for index, source_path in enumerate(source_paths, start=1)
    ] if cuts else []
    _write_json(project / "artifacts" / "brief.json", {
        "version": "1.0",
        "theme": "剪辑门禁测试商品片",
        "duration_seconds": 4,
        "images": {},
    })
    _write_json(project / "artifacts" / "video_plan.json", {
        "version": "1.0",
        "segments": [{"id": "beat_01", "t": "0-4", "purpose": "商品展示"}],
    })
    _write_json(project / "artifacts" / "asset_ledger.json", {
        "version": "1.0",
        "entries": [],
    })
    sample_path = "assets/video/sample.mp4"
    _copy_fixture_video(project / sample_path)
    _write_json(project / "artifacts" / "sample_reel.json", {
        "version": "1.0",
        "path": sample_path,
        "beat_ids": ["beat_01"],
        "status": "approved",
    })
    _write_json(project / "artifacts" / "review_overview.json", {
        "version": "1.0",
        "overview": [
            {
                "beat": f"beat_{index:02d}",
                "time": f"{(index - 1) * 2}-{index * 2}",
                "output_path": source_path,
            }
            for index, source_path in enumerate(source_paths, start=1)
        ],
    })
    edit_decisions = {
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "cuts": edit_cuts,
    }
    if dirty_cuts:
        edit_decisions.update({
            "requires_compose": True,
            "cuts_revision": "h-dirty",
        })
    _write_json(project / "artifacts" / "edit_decisions.json", edit_decisions)
    if cuts:
        _copy_fixture_video(project / source_paths[0])
    if full_draft:
        draft_path = "renders/latest.mp4"
        _write_json(project / "artifacts" / "full_draft_pro.json", {
            "path": draft_path,
            "issue_segments": [],
            "modification_list": [],
        })
        if latest_render:
            _copy_fixture_video(project / draft_path)
    artifacts_by_stage = {
        "brief_locked": {
            "brief": "artifacts/brief.json",
            "video_plan": "artifacts/video_plan.json",
        },
        "assets_gate": {"asset_ledger": "artifacts/asset_ledger.json"},
        "sample_review": {"sample_reel": "artifacts/sample_reel.json"},
        "segment_build": {"review_overview": "artifacts/review_overview.json"},
        "draft_review": (
            {"full_draft_pro": "artifacts/full_draft_pro.json"}
            if full_draft
            else {}
        ),
    }
    active_index = COMMERCIAL_STAGE_ORDER.index(stage)
    for sequence, completed_stage in enumerate(
        COMMERCIAL_STAGE_ORDER[:active_index],
        start=1,
    ):
        _write_commercial_checkpoint(
            project,
            completed_stage,
            "completed",
            artifacts_by_stage.get(completed_stage, {}),
            sequence,
        )
    _write_commercial_checkpoint(
        project,
        stage,
        "in_progress",
        artifacts_by_stage.get(stage, {}),
        active_index + 1,
    )
    return project_id


def test_staged_server_uses_isolated_temporary_projects_directory(
    staged_backlot_server,
):
    shared_stage = (
        backlot_screenshot_stage.REPO_ROOT
        / ".backlot"
        / "screenshot-stage"
    )

    assert staged_backlot_server.startswith("http://127.0.0.1:")
    assert backlot_screenshot_stage.STAGE_DIR != shared_stage
    assert backlot_screenshot_stage.STAGE_DIR.is_dir()


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


def test_commercial_missing_ledger_and_planned_output_render_failed_status(
    staged_backlot_server,
):
    project_id = "commercial-missing-asset-contract"
    project = backlot_screenshot_stage.STAGE_DIR / project_id
    if project.exists():
        shutil.rmtree(project)
    (project / "artifacts").mkdir(parents=True)
    _write_json(project / "project.json", {
        "project_id": project_id,
        "title": "缺失素材契约",
        "pipeline_type": "bootstrap-commercial",
    })
    _write_json(project / "artifacts" / "segment_cards.json", {
        "segments": [{"beat": "beat_01", "time": "0-4"}],
    })
    _write_json(project / "artifacts" / "asset_ledger.json", {
        "entries": [{
            "beat": "beat_01",
            "kind": "video",
            "path": "assets/video/missing-ledger.mp4",
            "selected": True,
            "label_zh": "缺失入片视频",
        }],
        "planned_entries": [{
            "beat": "beat_01",
            "kind": "image",
            "status": "ready",
            "label_zh": "计划商品图",
            "planned_output_path": "assets/images/planned-hero.png",
            "output_path": "assets/images/planned-hero.png",
        }],
    })
    _write_json(project / "checkpoint_sample_review.json", {
        "stage": "sample_review",
        "status": "in_progress",
        "timestamp": "2026-08-12T00:00:00Z",
        "artifacts": {},
    })

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.locator(".stage").filter(has_text="素材检查").click()
            card = page.locator('.commercial-beat-card[data-beat="beat_01"]')
            planned = card.locator(".planned-entry-card")
            expect(planned).to_have_count(1)
            planned_text = planned.inner_text()
            assert "生成失败" in planned_text
            assert "已就绪" not in planned_text
            assert "assets/images/planned-hero.png" in planned_text
            expect(planned.locator("img")).to_have_count(0)

            page.locator(".stage").filter(has_text="试片确认").click()
            expect(page.locator(".planned-entry-card")).to_have_count(0)
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
            expect(plan).not_to_have_count(0)
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
            expect(page.locator(".render-hero video")).to_have_count(0)

            page.locator(".stage").filter(has_text="初稿审查").click()
            draft_body = page.locator("body").inner_text()
            assert "未挂接阶段证据" in draft_body
            assert "renders/legacy_full_draft_preview.mp4" in draft_body
            expect(page.locator(".render-hero video")).to_have_count(0)
        finally:
            browser.close()


def test_segment_stage_does_not_reuse_sample_reel(staged_backlot_server):
    project_id = _stage_segment_evidence_project()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.locator(".stage").filter(has_text="分段制作").click()

            body = page.locator("body").inner_text()
            assert "sample_only.mp4" not in body
            assert page.locator(
                '.render-meta .v:has-text("试片"), '
                '.section-title:has-text("sample_only.mp4")'
            ).count() == 0
        finally:
            browser.close()


def test_segment_stage_each_beat_only_shows_its_review_output(
    staged_backlot_server,
):
    project_id = _stage_segment_evidence_project()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.locator(".stage").filter(has_text="分段制作").click()

            for beat_id in ("beat_01", "beat_02"):
                card = page.locator(
                    f'.commercial-beat-card[data-beat="{beat_id}"]'
                )
                assert card.count() == 1
                videos = card.locator("video")
                assert videos.count() == 1
                assert f"assets/video/{beat_id}.mp4" in (
                    videos.get_attribute("src") or ""
                )
                other = "beat_02" if beat_id == "beat_01" else "beat_01"
                assert f"assets/video/{other}.mp4" not in card.inner_text()
        finally:
            browser.close()


def test_segment_path_conflict_with_draft_hides_only_conflicting_video(
    staged_backlot_server,
):
    project_id = _stage_segment_evidence_project()
    project = backlot_screenshot_stage.STAGE_DIR / project_id
    shared_path = "assets/video/beat_01.mp4"
    _write_json(project / "artifacts" / "full_draft_pro.json", {
        "path": shared_path,
        "issue_segments": [],
        "modification_list": [],
    })

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="domcontentloaded",
            )
            page.wait_for_selector(".commercial-board")
            page.locator(".stage").filter(has_text="分段制作").click()

            conflict_card = page.locator(
                '.commercial-beat-card[data-beat="beat_01"]'
            )
            expect(conflict_card.locator("video")).to_have_count(0)
            expect(conflict_card).to_contain_text("canonical 路径冲突")

            legal_card = page.locator(
                '.commercial-beat-card[data-beat="beat_02"]'
            )
            expect(legal_card.locator("video")).to_have_count(1)
            assert "assets/video/beat_02.mp4" in (
                legal_card.locator("video").get_attribute("src") or ""
            )
        finally:
            browser.close()


def test_sample_reel_beat_ids_limit_sample_view(staged_backlot_server):
    project_id = _stage_segment_evidence_project()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.locator(".stage").filter(has_text="试片确认").click()

            cards = page.locator(".commercial-beat-card")
            assert cards.count() == 1
            assert cards.first.get_attribute("data-beat") == "beat_01"
            assert "sample_only.mp4" in (
                page.locator(".render-hero video").get_attribute("src") or ""
            )
        finally:
            browser.close()


def test_legacy_sample_without_beat_ids_keeps_hero_without_claiming_beat_coverage(
    staged_backlot_server,
):
    project_id = _stage_segment_evidence_project(include_sample_beat_ids=False)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.locator(".stage").filter(has_text="试片确认").click()

            assert "sample_only.mp4" in (
                page.locator(".render-hero video").get_attribute("src") or ""
            )
            assert page.locator(".commercial-beat-card").count() == 0
        finally:
            browser.close()


def test_planned_entries_only_render_in_assets_view(staged_backlot_server):
    project_id = _stage_segment_evidence_project(include_planned_entries=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.locator(".stage").filter(has_text="素材检查").click()
            planned = page.locator(".planned-entry-card")
            assert planned.count() == 1
            planned_text = planned.inner_text()
            assert "计划图片" in planned_text
            assert "计划视频" not in planned_text
            assert "assets/video/planned.mp4" not in planned_text

            for stage_label in ("试片确认", "分段制作", "初稿审查"):
                page.locator(".stage").filter(has_text=stage_label).click()
                assert page.locator(".planned-entry-card").count() == 0
        finally:
            browser.close()


def test_reused_draft_path_cannot_appear_as_sample_stage_media(
    staged_backlot_server,
):
    project_id = _stage_segment_evidence_project()
    project = backlot_screenshot_stage.STAGE_DIR / project_id
    shared_path = "assets/video/sample_only.mp4"
    _write_json(project / "artifacts" / "full_draft_pro.json", {
        "path": shared_path,
        "issue_segments": [],
        "modification_list": [],
    })

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.locator(".stage").filter(has_text="试片确认").click()
            expect(page.locator(".render-hero video")).to_have_count(0)
            expect(page.locator(".commercial-stage-evidence")).to_contain_text(
                "canonical 路径冲突"
            )

            page.locator(".stage").filter(has_text="初稿审查").click()
            expect(page.locator(".render-hero video")).to_have_count(1)
            assert shared_path in (
                page.locator(".render-hero video").get_attribute("src") or ""
            )
        finally:
            browser.close()


EDIT_GATE_BLOCKED_CASES = [
    (
        "before-draft",
        {"stage": "segment_build"},
        "初稿审查阶段起才可提交",
    ),
    (
        "missing-full-draft",
        {"full_draft": False},
        "缺少 full_draft_pro",
    ),
    (
        "empty-cuts",
        {"cuts": False},
        "没有可编辑片段",
    ),
    (
        "missing-latest-render",
        {"latest_render": False},
        "缺少最新成片",
    ),
    (
        "missing-cut-source",
        {"source_exists": False},
        "片段源文件不存在",
    ),
    (
        "compose-required",
        {"dirty_cuts": True},
        "需要重合成",
    ),
]


@pytest.mark.parametrize(
    ("scenario", "options", "_expected_hint"),
    EDIT_GATE_BLOCKED_CASES,
)
def test_edit_gate_disables_submission_until_draft_is_complete(
    staged_backlot_server,
    scenario,
    options,
    _expected_hint,
):
    project_id = _stage_edit_gate_project(scenario, **options)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.get_by_role("button", name="✂ 剪辑").click()

            submit = page.get_by_role("button", name="提交剪辑要求")
            assert submit.count() == 0 or submit.is_disabled() is True
            assert page.locator(".edit-clip").count() == 0
            assert page.locator("#edit-note-input").count() == 0
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("scenario", "options", "expected_hint"),
    EDIT_GATE_BLOCKED_CASES,
)
def test_edit_gate_explains_each_submission_blocker(
    staged_backlot_server,
    scenario,
    options,
    expected_hint,
):
    project_id = _stage_edit_gate_project(scenario, **options)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.get_by_role("button", name="✂ 剪辑").click()

            expect(page.locator(".edit-tab")).to_contain_text(expected_hint)
        finally:
            browser.close()


def test_edit_gate_enables_submission_from_draft_review_when_all_inputs_exist(
    staged_backlot_server,
):
    project_id = _stage_edit_gate_project("ready")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.get_by_role("button", name="✂ 剪辑").click()

            expect(page.locator(".edit-clip")).to_have_count(1)
            expect(page.locator(".edit-clip-del")).to_have_count(0)
            submit = page.get_by_role("button", name="提交剪辑要求")
            expect(submit).to_have_count(1)
            expect(submit).to_be_enabled()
        finally:
            browser.close()


def test_edit_ui_allows_delete_with_multiple_cuts_but_never_to_zero(
    staged_backlot_server,
):
    project_id = _stage_edit_gate_project("two-cuts")
    project = backlot_screenshot_stage.STAGE_DIR / project_id
    decisions_path = project / "artifacts" / "edit_decisions.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    second_source = "assets/video/cut_02.mp4"
    _copy_fixture_video(project / second_source)
    decisions["cuts"].append({
        "id": "cut_02",
        "source": second_source,
        "in_seconds": 0,
        "out_seconds": 2,
    })
    _write_json(decisions_path, decisions)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.get_by_role("button", name="✂ 剪辑").click()

            expect(page.locator(".edit-clip")).to_have_count(2)
            expect(page.locator(".edit-clip-del")).to_have_count(2)
            page.locator(".edit-clip-del").first.click()
            expect(page.locator(".edit-clip")).to_have_count(1)
            expect(page.locator(".edit-clip-del")).to_have_count(0)
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("response_detail", "expected"),
    [
        (
            {
                "kind": "editing_gate",
                "reason_codes": ["compose_required"],
                "friendly_zh": "cuts 已应用，需要重合成后再提交。",
            },
            "cuts 已应用，需要重合成后再提交。",
        ),
        (
            "intent_id already exists with different content",
            "这组改动之前已经提交过了",
        ),
    ],
)
def test_edit_submit_distinguishes_gate_409_from_duplicate_conflict(
    staged_backlot_server,
    response_detail,
    expected,
):
    project_id = _stage_edit_gate_project("submit-409")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.route(
                "**/intents",
                lambda route: route.fulfill(
                    status=409,
                    content_type="application/json",
                    body=json.dumps({"detail": response_detail}),
                ),
            )
            page.goto(
                f"{staged_backlot_server}/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            page.get_by_role("button", name="✂ 剪辑").click()
            expect(page.locator("#edit-note-input")).to_be_visible()
            page.locator("#edit-note-input").fill("测试错误分支")
            page.get_by_role("button", name="提交剪辑要求").click()

            expect(page.locator(".edit-feedback")).to_contain_text(expected)
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

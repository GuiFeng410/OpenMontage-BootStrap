"""React commercial board is the default station at `/p/<id>`. `/next/p/` is an alias."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backlot import server as server_mod
from scripts import backlot_screenshot_stage

FIXTURE = Path(__file__).parent / "fixtures" / "next-board-commercial-state.json"


@pytest.fixture
def client(monkeypatch):
    async def no_watch():
        return None

    monkeypatch.setattr(server_mod, "_watch_projects", no_watch)
    monkeypatch.setattr(server_mod, "schedule_server_exit", lambda: None)
    with TestClient(server_mod.create_app()) as c:
        yield c


def test_default_board_is_spa(client):
    page = client.get("/p/demo-commercial")
    assert page.status_code == 200
    assert 'id="root"' in page.text
    assert "/ui/board.js" not in page.text


def test_board_shell_in_bundle(client):
    page = client.get("/p/demo-commercial")
    assert page.status_code == 200
    assert 'id="root"' in page.text
    assert "/ui/board-commercial.css" in page.text
    match = re.search(r'src="(/assets/[^"]+)"', page.text)
    assert match, page.text
    js = client.get(match.group(1))
    assert js.status_code == 200
    text = js.text
    for needle in (
        "commercial-board",
        "commercial-stage-status",
        "commercial-runner-status",
        "commercial-review-fold",
        "请留在本页确认",
        "/api/project/",
        "回顾",
        "commercial-decision-option",
        "/intents",
        "进入下一步",
        "清空并重选",
        "提交剪辑要求",
        "✂ 剪辑",
        "edit-clip",
        "render-hero",
        "cuts_revision",
        "结束并导出项目",
        "export-tab-btn",
        "interrupt-tab-btn",
        "project_export",
    ):
        assert needle in text, needle
    assert "/ui/board-edit.css" in page.text
    alias = client.get("/next/p/demo-commercial")
    assert alias.status_code == 200
    assert 'id="root"' in alias.text


def _available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def next_board_server(tmp_path):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    del playwright_sync
    original_stage_dir = backlot_screenshot_stage.STAGE_DIR
    original_projects_dir = os.environ.get("OPENMONTAGE_PROJECTS_DIR")
    stage_dir = tmp_path / "projects"
    stage_dir.mkdir()
    server = None
    try:
        backlot_screenshot_stage.STAGE_DIR = stage_dir
        os.environ["OPENMONTAGE_PROJECTS_DIR"] = str(stage_dir)
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
            if server.poll() is not None:
                raise RuntimeError(f"Backlot server exited (code {server.returncode})")
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
        backlot_screenshot_stage.STAGE_DIR = original_stage_dir
        if original_projects_dir is None:
            os.environ.pop("OPENMONTAGE_PROJECTS_DIR", None)
        else:
            os.environ["OPENMONTAGE_PROJECTS_DIR"] = original_projects_dir


def test_next_board_readonly_shell_renders(next_board_server):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.route(
                "**/api/project/*/state",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload),
                ),
            )
            page.goto(
                next_board_server + "/next/p/demo-commercial?static=1",
                wait_until="networkidle",
            )
            expect(page.locator(".commercial-board")).to_be_visible()
            expect(page.locator(".rail .stage")).to_have_count(7)
            expect(page.locator(".commercial-runner-status")).to_contain_text("暂停，要你选")
            expect(page.locator(".commercial-stage-status")).to_contain_text("方案确认")
            expect(page.locator(".commercial-beat-card[data-beat='beat_1']")).to_be_visible()
            expect(page.locator(".commercial-review-fold")).to_contain_text("回顾")
            expect(page.locator(".commercial-decision-option")).to_have_count(0)
            expect(page.get_by_role("link", name="所有项目")).to_be_visible()
            expect(page.get_by_role("button", name="结束并导出项目")).to_be_visible()
            expect(page.get_by_role("button", name="中断")).to_be_visible()
            expect(page.get_by_role("button", name="✂ 剪辑")).to_be_visible()
        finally:
            browser.close()


def _intent_payload(timestamp: str = "2026-08-13T08:00:00Z") -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["commercial"]["decision"] = {
        "stage": "brief_locked",
        "title_zh": "制作档位",
        "prompt_zh": "请选择制作档位",
        "timestamp": timestamp,
        "paused": False,
        "options": [
            {
                "id": "medium",
                "label_zh": "中度",
                "description_zh": "使用用户素材或 Stock",
                "impact_zh": "成本较低",
            },
            {
                "id": "heavy",
                "label_zh": "重度",
                "description_zh": "允许付费视频生成",
                "impact_zh": "成本与一致性风险较高",
            },
        ],
    }
    return payload


def test_next_board_intent_draft_submit_retry_and_stale(next_board_server):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    payload = _intent_payload()
    posts: list[int] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.route(
                "**/api/project/*/state",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload),
                ),
            )

            def handle_intent(route):
                if route.request.method != "POST":
                    route.fallback()
                    return
                posts.append(1)
                if len(posts) == 1:
                    route.fulfill(status=500, content_type="application/json", body="{}")
                    return
                route.fulfill(status=201, content_type="application/json", body="{}")

            page.route("**/intents", handle_intent)
            page.goto(
                next_board_server + "/next/p/demo-commercial?static=1",
                wait_until="networkidle",
            )
            expect(page.locator(".commercial-decision-option")).to_have_count(2)
            page.locator('.commercial-decision-option[data-option-id="heavy"]').click()
            expect(
                page.locator('.commercial-decision-option[data-option-id="heavy"]')
            ).to_have_attribute("aria-pressed", "true")
            assert "重度" in page.locator(".commercial-intent-summary").input_value()

            page.get_by_role("button", name="进入下一步").click()
            expect(page.locator(".commercial-intent-feedback")).to_contain_text(
                "提交失败，请留在本页重试。"
            )
            page.get_by_role("button", name="进入下一步").click()
            expect(page.locator(".commercial-intent-feedback")).to_contain_text(
                "已进入下一步，请留在本页等待本机处理。"
            )
            expect(page.get_by_role("button", name="已提交，等待处理")).to_be_disabled()
            page.get_by_role("button", name="已提交，等待处理").click(force=True)
            assert len(posts) == 2

            payload["commercial"]["decision"]["timestamp"] = "2026-08-13T08:01:00Z"
            page.reload(wait_until="networkidle")
            stale = page.locator(".intent-basket-stale")
            expect(stale).to_be_visible()
            expect(stale).to_contain_text("待确认内容已更新")
            expect(page.locator(".commercial-intent-summary")).to_have_count(0)
            page.get_by_role("button", name="清空并重选").click()
            expect(page.locator(".intent-basket-stale")).to_have_count(0)
            expect(page.locator(".commercial-intent-summary")).to_have_count(1)
        finally:
            browser.close()


def _sample_player_payload() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for stage in payload["stages"]:
        if stage["name"] == "brief_locked":
            stage["status"] = "completed"
        elif stage["name"] == "sample_review":
            stage["status"] = "awaiting_human"
        else:
            stage["status"] = "pending"
    payload["commercial"]["user_stage_zh"] = "试片确认"
    payload["commercial"]["stage_evidence"] = {
        "sample": {
            "path": "renders/sample.mp4",
            "exists": True,
            "status": "review",
            "duration_seconds": 2,
        }
    }
    payload["commercial"]["decision"] = {"paused": True, "options": []}
    return payload


def _edit_payload(*, enabled: bool = True, two_cuts: bool = True) -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cuts = [
        {
            "id": "cut_01",
            "source": "assets/video/cut_01.mp4",
            "in_seconds": 0,
            "out_seconds": 2,
        }
    ]
    if two_cuts:
        cuts.append(
            {
                "id": "cut_02",
                "source": "assets/video/cut_02.mp4",
                "in_seconds": 0,
                "out_seconds": 3,
            }
        )
    payload["artifacts"] = {"edit_decisions": {"cuts": cuts}}
    gate = {
        "enabled": enabled,
        "friendly_zh": (
            "剪辑输入已就绪，可提交轻量剪辑要求。"
            if enabled
            else "当前不可提交剪辑要求：阶段不对"
        ),
        "latest_render": {"path": "renders/draft.mp4", "exists": True},
    }
    payload["editing_gate"] = gate
    payload["commercial"]["editing_gate"] = gate
    return payload


def _goto_mocked(page, next_board_server: str, payload: dict) -> None:
    page.route(
        "**/api/project/*/state",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        ),
    )
    page.goto(
        next_board_server + "/next/p/demo-commercial?static=1",
        wait_until="networkidle",
    )


def _tiny_mp4_bytes() -> bytes | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "tiny.mp4"
        proc = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=64x64:d=2",
                "-pix_fmt",
                "yuv420p",
                str(dest),
            ],
            check=False,
        )
        if proc.returncode != 0 or not dest.exists():
            return None
        return dest.read_bytes()


def _write_tiny_mp4(rel: str) -> bool:
    data = _tiny_mp4_bytes()
    if not data:
        return False
    root = Path(os.environ["OPENMONTAGE_PROJECTS_DIR"])
    dest = root / "demo-commercial" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def test_next_board_player_keeps_progress_across_edit_toggle(next_board_server):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    payload = _sample_player_payload()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            seekable = _write_tiny_mp4("renders/sample.mp4")
            _goto_mocked(page, next_board_server, payload)
            hero = page.locator(".render-hero video")
            expect(hero).to_be_visible()
            assert "renders/sample.mp4" in (hero.get_attribute("src") or "")
            if seekable:
                page.wait_for_function(
                    "() => (document.querySelector('.render-hero video') || {}).readyState >= 1",
                    timeout=8000,
                )
                page.evaluate(
                    """() => {
                        const video = document.querySelector(".render-hero video");
                        video.pause();
                        video.currentTime = 0.5;
                    }"""
                )
                page.wait_for_function(
                    "() => (document.querySelector('.render-hero video') || {}).currentTime >= 0.45",
                    timeout=8000,
                )
            page.get_by_role("button", name="✂ 剪辑").click()
            expect(page.locator(".edit-tab")).to_be_visible()
            page.get_by_role("button", name="✂ 剪辑").click()
            expect(hero).to_be_visible()
            assert "renders/sample.mp4" in (hero.get_attribute("src") or "")
            if seekable:
                page.wait_for_function(
                    "() => (document.querySelector('.render-hero video') || {}).readyState >= 1",
                    timeout=8000,
                )
                restored = page.evaluate(
                    """() => document.querySelector(".render-hero video").currentTime"""
                )
                assert restored >= 0.45
        finally:
            browser.close()


def test_next_board_edit_gate_locked_hides_strip(next_board_server):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    payload = _edit_payload(enabled=False)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            _goto_mocked(page, next_board_server, payload)
            page.get_by_role("button", name="✂ 剪辑").click()
            expect(page.locator(".edit-tab")).to_contain_text("当前不可提交剪辑要求")
            expect(page.locator(".edit-clip")).to_have_count(0)
            expect(page.get_by_role("button", name="提交剪辑要求")).to_have_count(0)
        finally:
            browser.close()


def test_next_board_edit_delete_reorder_and_submit(next_board_server):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    payload = _edit_payload()
    posts: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.route(
                "**/api/project/*/state",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload),
                ),
            )

            def handle_intent(route):
                if route.request.method != "POST":
                    route.fallback()
                    return
                posts.append(json.loads(route.request.post_data or "{}"))
                route.fulfill(status=201, content_type="application/json", body="{}")

            page.route("**/intents", handle_intent)
            page.goto(
                next_board_server + "/next/p/demo-commercial?static=1",
                wait_until="networkidle",
            )
            page.get_by_role("button", name="✂ 剪辑").click()
            expect(page.locator(".edit-clip")).to_have_count(2)
            expect(page.locator(".edit-clip-del")).to_have_count(2)
            names = page.locator(".edit-clip-name").all_inner_texts()
            assert names[0].startswith("cut_01")
            page.locator(".edit-clip-handle-grip").first.drag_to(
                page.locator(".edit-clip").nth(1)
            )
            names_after = page.locator(".edit-clip-name").all_inner_texts()
            assert names_after[0].startswith("cut_02") or names_after != names
            page.locator(".edit-clip-del").first.click()
            expect(page.locator(".edit-clip")).to_have_count(1)
            expect(page.locator(".edit-clip-del")).to_have_count(0)
            page.locator("#edit-note-input").fill("片头缩短")
            page.get_by_role("button", name="提交剪辑要求").click()
            expect(page.locator(".edit-feedback")).to_contain_text("已提交")
            assert posts, "edit intent was not posted"
            body = posts[0]
            assert body["base"]["cuts_revision"]
            assert body["base"]["source_render"] == "renders/draft.mp4"
            assert any(item.get("type") in {"delete", "reorder"} for item in body["actions"])
        finally:
            browser.close()


def test_default_board_export_posts_project_export(next_board_server):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["commercial"]["final_video"] = {"exists": True, "path": "renders/final.mp4"}
    payload["commercial"]["completed"] = False
    posts: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.route(
                "**/api/project/*/state",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload),
                ),
            )

            def handle_intent(route):
                if route.request.method != "POST":
                    route.fallback()
                    return
                posts.append(json.loads(route.request.post_data or "{}"))
                route.fulfill(status=201, content_type="application/json", body="{}")

            page.route("**/intents", handle_intent)
            page.goto(next_board_server + "/p/demo-commercial?static=1", wait_until="domcontentloaded")
            expect(page.get_by_role("button", name="结束并导出项目")).to_be_visible()
            expect(page.get_by_role("button", name="中断")).to_be_visible()
            page.get_by_role("button", name="结束并导出项目").click()
            expect(page.locator(".export-tab-feedback").first).to_contain_text("已提交结束导出")
            assert posts and posts[0]["intent_type"] == "project_export"
            assert posts[0]["payload"]["action"] == "end_and_export"
        finally:
            browser.close()


def test_generic_board_shows_disk_notice(next_board_server):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    payload = {
        "project_id": "film",
        "title": "Film",
        "pipeline": {"pipeline_type": "explainer", "known": True},
        "stages": [{"name": "script", "status": "pending"}],
        "artifacts": {},
        "media": {"renders": [], "snapshots": [], "music": []},
        "events": [],
        "has_pipeline_state": False,
        "commercial": None,
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.route(
                "**/api/project/*/state",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload),
                ),
            )
            page.goto(next_board_server + "/p/film?static=1", wait_until="domcontentloaded")
            expect(page.locator(".notice").first).to_contain_text("No pipeline state")
            expect(page.get_by_role("button", name="结束并导出项目")).to_have_count(0)
        finally:
            browser.close()


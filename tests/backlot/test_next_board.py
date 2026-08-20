"""React commercial board shell on /next/p/<id>. Vanilla /p/ stays the default station."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
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


def test_vanilla_board_html_unchanged(client):
    page = client.get("/p/demo-commercial")
    assert page.status_code == 200
    assert "/ui/board.js" in page.text
    assert 'id="root"' not in page.text


def test_next_board_shell_in_bundle(client):
    page = client.get("/next/p/demo-commercial")
    assert page.status_code == 200
    assert 'id="root"' in page.text
    assert "/ui/board-commercial.css" in page.text
    match = re.search(r'src="(/next/assets/[^"]+)"', page.text)
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
        "打开默认站看板",
        "回顾",
        "commercial-decision-option",
        "/intents",
        "进入下一步",
        "清空并重选",
    ):
        assert needle in text, needle
    assert "提交剪辑要求" not in text
    assert "✂ 剪辑" not in text


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
            expect(page.get_by_role("link", name="打开默认站看板（确认 / 剪辑 / 播放）")).to_be_visible()
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


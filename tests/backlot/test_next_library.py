"""React library page on /next/. Vanilla / stays the default station."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from fastapi.testclient import TestClient

from backlot import server as server_mod
from scripts import backlot_screenshot_stage


@pytest.fixture
def client(monkeypatch):
    async def no_watch():
        return None

    monkeypatch.setattr(server_mod, "_watch_projects", no_watch)
    monkeypatch.setattr(server_mod, "schedule_server_exit", lambda: None)
    with TestClient(server_mod.create_app()) as c:
        yield c


def test_default_library_html_unchanged(client):
    page = client.get("/")
    assert page.status_code == 200
    assert 'id="runner-occupant"' in page.text
    assert "/ui/library.js" in page.text
    assert 'id="root"' not in page.text


def test_next_library_shell_and_bundle_copy(client):
    page = client.get("/next/")
    assert page.status_code == 200
    assert "Backlot — 项目库" in page.text
    assert "/ui/library.css" in page.text
    assert 'id="root"' in page.text
    src = re.search(r'src="(/next/assets/[^"]+)"', page.text)
    assert src, page.text
    js = client.get(src.group(1))
    assert js.status_code == 200
    text = js.text
    for needle in (
        "创建新商品片",
        "开始创建项目",
        "复制到聊天",
        "中断并做别的",
        "/api/library/create-project",
        "/api/library/continue-project",
        "/api/library/events",
    ):
        assert needle in text, needle


def _available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def next_library_server(tmp_path):
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


def test_next_library_onboarding_renders(next_library_server):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                next_library_server + "/next/?static=1",
                wait_until="networkidle",
            )
            expect(page.get_by_role("heading", name="项目库")).to_be_visible()
            expect(page.locator(".library-onboarding")).to_contain_text("创建新商品片")
            expect(page.get_by_role("button", name="开始创建项目")).to_be_visible()
            expect(page.get_by_role("button", name="复制到聊天")).to_be_visible()
            expect(page.get_by_role("radio", name="普通")).to_have_attribute(
                "aria-checked", "true"
            )
            page.get_by_role("radio", name="极简").click()
            expect(page.locator(".library-mode-step")).to_have_count(3)
        finally:
            browser.close()

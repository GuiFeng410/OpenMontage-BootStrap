"""Same-fixture parity: default `/` `/p/` vs alias `/next/` `/next/p/`."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from backlot import server as server_mod
from scripts import backlot_screenshot_stage
from scripts.backlot_visual_eval import compare_images

BOARD_FIXTURE = Path(__file__).parent / "fixtures" / "next-board-commercial-state.json"
SELECTOR_CONTRACT = Path(__file__).parent / "fixtures" / "b1-ui-selector-contract.json"

STATIONS = (
    ("vanilla", "/", "/p/demo-commercial?static=1"),
    ("next", "/next/", "/next/p/demo-commercial?static=1"),
)


@pytest.fixture
def client(monkeypatch):
    async def no_watch():
        return None

    monkeypatch.setattr(server_mod, "_watch_projects", no_watch)
    monkeypatch.setattr(server_mod, "schedule_server_exit", lambda: None)
    with TestClient(server_mod.create_app()) as c:
        yield c


def test_default_routes_are_spa(client):
    home = client.get("/")
    board = client.get("/p/demo-commercial")
    assert home.status_code == 200
    assert board.status_code == 200
    assert "/ui/library.js" not in home.text
    assert 'id="root"' in home.text
    assert "/ui/board.js" not in board.text
    assert 'id="root"' in board.text
    nxt = client.get("/next/")
    assert nxt.status_code == 200
    assert 'id="root"' in nxt.text


def _available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def parity_server(tmp_path):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    del playwright_sync
    original_stage_dir = backlot_screenshot_stage.STAGE_DIR
    original_projects_dir = os.environ.get("OPENMONTAGE_PROJECTS_DIR")
    stage_dir = tmp_path / "projects"
    stage_dir.mkdir()
    server = None
    log_file = None
    try:
        backlot_screenshot_stage.STAGE_DIR = stage_dir
        os.environ["OPENMONTAGE_PROJECTS_DIR"] = str(stage_dir)
        port = _available_local_port()
        env = dict(os.environ)
        env["OPENMONTAGE_PROJECTS_DIR"] = str(stage_dir)
        log_file = (tmp_path / "backlot-serve.log").open("w", encoding="utf-8")
        server = subprocess.Popen(
            [sys.executable, "-m", "backlot", "serve", "--port", str(port)],
            cwd=backlot_screenshot_stage.REPO_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
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
        if log_file is not None:
            log_file.close()
        backlot_screenshot_stage.STAGE_DIR = original_stage_dir
        if original_projects_dir is None:
            os.environ.pop("OPENMONTAGE_PROJECTS_DIR", None)
        else:
            os.environ["OPENMONTAGE_PROJECTS_DIR"] = original_projects_dir


def _intent_payload() -> dict:
    payload = json.loads(BOARD_FIXTURE.read_text(encoding="utf-8"))
    payload["commercial"]["runner_status"] = {
        "phase": "idle",
        "runner_alive": True,
        "friendly_zh": "等你在本页确认方案。",
    }
    payload["commercial"]["decision"] = {
        "stage": "brief_locked",
        "title_zh": "制作档位",
        "prompt_zh": "请选择制作档位",
        "timestamp": "2026-08-13T08:00:00Z",
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


def _edit_payload() -> dict:
    payload = json.loads(BOARD_FIXTURE.read_text(encoding="utf-8"))
    payload["artifacts"] = {
        "edit_decisions": {
            "cuts": [
                {
                    "id": "cut_01",
                    "source": "assets/video/cut_01.mp4",
                    "in_seconds": 0,
                    "out_seconds": 2,
                }
            ]
        }
    }
    gate = {
        "enabled": True,
        "friendly_zh": "剪辑输入已就绪，可提交轻量剪辑要求。",
        "latest_render": {"path": "renders/draft.mp4", "exists": True},
    }
    payload["editing_gate"] = gate
    payload["commercial"]["editing_gate"] = gate
    return payload


def _crop_to_common(path_a: Path, path_b: Path) -> None:
    img_a = Image.open(path_a)
    img_b = Image.open(path_b)
    width = min(img_a.size[0], img_b.size[0])
    height = min(img_a.size[1], img_b.size[1])
    if img_a.size != (width, height):
        img_a.crop((0, 0, width, height)).save(path_a)
    if img_b.size != (width, height):
        img_b.crop((0, 0, width, height)).save(path_b)


def _screenshot_locator(locator, dest: Path) -> None:
    locator.page.evaluate(
        """() => Promise.race([
          document.fonts.ready,
          new Promise((resolve) => setTimeout(resolve, 800)),
        ])"""
    )
    box = locator.bounding_box()
    assert box, "locator has no box"
    locator.page.screenshot(
        path=str(dest),
        clip={
            "x": box["x"],
            "y": box["y"],
            "width": max(1, box["width"]),
            "height": max(1, box["height"]),
        },
        timeout=8_000,
        animations="disabled",
    )


def _goto(page, url: str, ready: str) -> None:
    # commit：只等响应头。load/networkidle 会被 SSE 或未完成媒体卡住。
    # 库页 HTML 里已有空的 .library-onboarding，必须等到 JS 填入正文。
    last_error = None
    for _ in range(2):
        try:
            page.goto(url, wait_until="commit", timeout=30_000)
            page.locator(ready).first.wait_for(timeout=20_000)
            page.wait_for_function(
                """(sel) => {
                  const node = document.querySelector(sel);
                  return Boolean(node && node.innerText && node.innerText.trim());
                }""",
                arg=ready,
                timeout=20_000,
            )
            return
        except Exception as exc:  # noqa: BLE001 — 导航偶发超时后换一次再试
            last_error = exc
            page.wait_for_timeout(400)
    raise last_error


def _goto_state(page, origin: str, path: str, payload: dict) -> None:
    page.unroute_all()
    page.route(
        "**/api/project/*/state",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        ),
    )
    _goto(page, origin + path, ".commercial-board")


@pytest.mark.parametrize("station,library_path,_board_path", STATIONS)
def test_library_copy_parity(parity_server, station, library_path, _board_path):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            _goto(page, parity_server + library_path + "?static=1", ".library-onboarding")
            expect(page.get_by_role("heading", name="项目库")).to_be_visible()
            expect(page.locator("#runner-occupant")).to_have_count(1)
            expect(page.locator(".library-onboarding")).to_contain_text("创建新商品片")
            expect(page.get_by_role("button", name="开始创建项目")).to_be_visible()
            expect(page.get_by_role("button", name="复制到聊天")).to_be_visible()
            expect(page.locator(".library-occupant-release")).to_have_count(1)
        finally:
            browser.close()


@pytest.mark.parametrize("station,library_path,board_path", STATIONS)
def test_board_selector_contract_parity(parity_server, station, library_path, board_path):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    contract = json.loads(SELECTOR_CONTRACT.read_text(encoding="utf-8"))
    payload = json.loads(BOARD_FIXTURE.read_text(encoding="utf-8"))
    skip = {".sse-banner", ".sse-refresh-btn", ".commercial-chat-only", ".commercial-decision-option"}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            _goto_state(page, parity_server, board_path, payload)
            for selector in contract["selectors"]:
                if selector in skip:
                    continue
                expect(page.locator(selector).first).to_be_visible()
            expect(page.locator(".commercial-review-fold")).to_contain_text("回顾")
            expect(page.get_by_role("button", name="✂ 剪辑")).to_be_visible()
        finally:
            browser.close()


@pytest.mark.parametrize("station,_library_path,board_path", STATIONS)
def test_board_intent_options_parity(parity_server, station, _library_path, board_path):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    payload = _intent_payload()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            _goto_state(page, parity_server, board_path, payload)
            expect(page.locator(".commercial-decision-option")).to_have_count(2)
            page.locator('.commercial-decision-option[data-option-id="heavy"]').click()
            expect(
                page.locator('.commercial-decision-option[data-option-id="heavy"]')
            ).to_have_attribute("aria-pressed", "true")
            expect(page.locator(".commercial-chat-only").first).to_contain_text("请留在本页")
        finally:
            browser.close()


@pytest.mark.parametrize("station,_library_path,board_path", STATIONS)
def test_board_edit_copy_parity(parity_server, station, _library_path, board_path):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    payload = _edit_payload()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            _goto_state(page, parity_server, board_path, payload)
            page.get_by_role("button", name="✂ 剪辑").click()
            expect(page.locator(".edit-tab")).to_be_visible()
            expect(page.get_by_role("button", name="提交剪辑要求")).to_be_visible()
            expect(page.locator(".edit-clip")).to_have_count(1)
        finally:
            browser.close()


def test_export_and_interrupt_on_default_board(parity_server):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    payload = json.loads(BOARD_FIXTURE.read_text(encoding="utf-8"))
    payload["commercial"]["final_video"] = {"exists": True, "path": "renders/final.mp4"}
    payload["commercial"]["completed"] = False
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            _goto_state(page, parity_server, "/p/demo-commercial?static=1", payload)
            expect(page.get_by_role("button", name="结束并导出项目")).to_be_visible()
            expect(page.get_by_role("button", name="中断")).to_be_visible()
            _goto_state(page, parity_server, "/next/p/demo-commercial?static=1", payload)
            expect(page.get_by_role("button", name="结束并导出项目")).to_be_visible()
        finally:
            browser.close()


def test_library_visual_parity(parity_server, tmp_path):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    with urllib.request.urlopen(parity_server + "/", timeout=5) as resp:
        assert resp.status == 200
    shots = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        try:
            for station, library_path, _board in STATIONS:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                try:
                    _goto(page, parity_server + library_path + "?static=1", ".library-onboarding")
                    dest = tmp_path / f"library-{station}.png"
                    _screenshot_locator(page.locator(".library-onboarding"), dest)
                    shots[station] = dest
                finally:
                    page.close()
        finally:
            browser.close()
    _crop_to_common(shots["vanilla"], shots["next"])
    result = compare_images(
        shots["vanilla"],
        shots["next"],
        tmp_path / "library-diff.png",
        threshold=0.08,
    )
    assert result["passed"], result


def test_board_visual_parity(parity_server, tmp_path):
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright
    expect = playwright_sync.expect
    payload = json.loads(BOARD_FIXTURE.read_text(encoding="utf-8"))
    shots = {}
    texts = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        try:
            for station, _library, board_path in STATIONS:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                try:
                    _goto_state(page, parity_server, board_path, payload)
                    card = page.locator(".commercial-stage-status").first
                    expect(card).to_be_visible()
                    texts[station] = " ".join(card.inner_text().split())
                    dest = tmp_path / f"board-status-{station}.png"
                    _screenshot_locator(card, dest)
                    shots[station] = dest
                finally:
                    page.close()
        finally:
            browser.close()
    assert texts["vanilla"] == texts["next"], texts
    _crop_to_common(shots["vanilla"], shots["next"])
    result = compare_images(
        shots["vanilla"],
        shots["next"],
        tmp_path / "board-status-diff.png",
        threshold=0.20,
    )
    assert result["passed"], result

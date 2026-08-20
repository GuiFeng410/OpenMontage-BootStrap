"""Server/API tests for Backlot.

These cover the deterministic eval surface in internal/evals/BACKLOT_EVAL_PLAN.md:
API shape, path safety, media/thumb serving, range requests, and loose
performance budgets.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backlot import server as server_mod
from backlot import state as state_mod


@pytest.fixture
def projects_root(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(state_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(server_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(server_mod, "_summary_cache", {})
    monkeypatch.setattr(server_mod, "_PROJECTS_ROOT_STR", __import__("os").path.normcase(str(root.resolve())))
    monkeypatch.setattr(server_mod, "THUMB_CACHE_DIR", tmp_path / "thumbs")
    return root


@pytest.fixture
def client(projects_root, monkeypatch):
    async def no_watch():
        return None

    monkeypatch.setattr(server_mod, "_watch_projects", no_watch)
    monkeypatch.setattr(server_mod, "schedule_server_exit", lambda: None)
    with TestClient(server_mod.create_app()) as c:
        yield c


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_project(root: Path, project_id: str = "film") -> Path:
    project = root / project_id
    (project / "artifacts").mkdir(parents=True)
    (project / "assets" / "images").mkdir(parents=True)
    (project / "assets" / "video").mkdir(parents=True)
    (project / "renders").mkdir(parents=True)
    _write_json(
        project / "project.json",
        {
            "project_id": project_id,
            "title": "Film",
            "pipeline_type": "cinematic",
            "created_at": "2026-07-02T00:00:00Z",
        },
    )
    _write_json(
        project / "checkpoint_script.json",
        {
            "version": "1.0",
            "project_id": project_id,
            "pipeline_type": "cinematic",
            "stage": "script",
            "status": "awaiting_human",
            "timestamp": "2026-07-02T00:01:00Z",
            "artifacts": {},
        },
    )
    return project


def _write_png(path: Path, color: tuple[int, int, int] = (200, 40, 80)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (24, 16), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    path.write_bytes(buf.getvalue())


class TestBacklotServerApi:
    def test_health(self, client, projects_root):
        response = client.get("/api/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["app"] == "backlot"
        assert payload["projects_dir"] == str(projects_root)
        assert "verify_ready" in payload
        assert "video_key_present" in payload
        assert "stock_key_present" in payload
        assert "runner_code_current" in payload
        assert isinstance(payload["runner_code_current"], bool)
        assert "runner_occupant" in payload
        assert "project_id" in payload["runner_occupant"]
        assert "title" in payload["runner_occupant"]

    def test_keys_refresh_never_returns_secret_values(self, client, monkeypatch):
        monkeypatch.setattr(
            "lib.library_create.refresh_key_availability",
            lambda **kwargs: {
                "ok": True,
                "video_key_present": True,
                "stock_key_present": True,
                "video_key_names_present": ["TOKENHUB_API_KEY"],
                "stock_key_names_present": ["PEXELS_API_KEY"],
                "friendly_zh": "已刷新：重度与中度均可用。",
                "note_zh": "只报告变量名是否非空，不返回 Key 值。",
            },
        )
        response = client.post("/api/keys/refresh")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["video_key_present"] is True
        assert payload["stock_key_present"] is True
        assert "secret" not in response.text.lower()

    def test_start_production_rejects_heavy_without_key(self, client, projects_root, monkeypatch):
        from lib.library_create import LibraryCreateError

        def boom(**kwargs):
            raise LibraryCreateError(
                "重度需要视频模型 Key。请写入仓根 .env 后点「已填入 Key，刷新可用性」。",
                code="missing_video_key",
            )

        monkeypatch.setattr("lib.library_create.start_production", boom)
        project = projects_root / "shop-demo"
        project.mkdir()
        (project / "project.json").write_text("{}", encoding="utf-8")
        response = client.post(
            "/api/project/shop-demo/start-production",
            json={"production_tier": "heavy"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "missing_video_key"

    def test_health_exposes_projects_root(self, client):
        payload = client.get("/api/health").json()
        assert payload["ok"] is True
        assert payload["app"] == "backlot"
        assert payload["projects_dir"]
        assert "active_project_id" in payload
        assert payload["active_project_id"] == "" or isinstance(payload["active_project_id"], str)

    def test_create_project_rejects_empty_title(self, client, monkeypatch):
        from lib.library_create import LibraryCreateError

        def boom(**kwargs):
            raise LibraryCreateError("请先填写商品主题", code="missing_title")

        monkeypatch.setattr("lib.library_create.create_library_project", boom)
        response = client.post(
            "/api/library/create-project",
            json={"title": "", "review_mode": "normal"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "missing_title"

    def test_continue_project_rejects_missing_id(self, client, monkeypatch):
        from lib.library_create import LibraryCreateError

        def boom(**kwargs):
            raise LibraryCreateError("无效的项目编号", code="bad_project")

        monkeypatch.setattr("lib.library_create.continue_library_project", boom)
        response = client.post("/api/library/continue-project", json={})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "bad_project"

    def test_library_static_assets_and_css_cache_bust(self, client):
        css = client.get("/ui/library.css")
        js = client.get("/ui/library-onboarding.js")
        page = client.get("/")

        assert css.status_code == 200
        assert js.status_code == 200
        assert "/ui/library.css?v=" in page.text
        assert 'id="runner-occupant"' in page.text

    def test_next_spa_serves_uidist_and_keeps_default_library(self, client):
        home = client.get("/")
        next_page = client.get("/next/")
        board = client.get("/next/p/demo")
        assets = list((server_mod.UI_NEXT_DIR / "assets").glob("*.js"))

        assert home.status_code == 200
        assert "/ui/library.css?v=" in home.text
        assert 'id="runner-occupant"' in home.text
        assert "Backlot — 项目库" in home.text
        assert next_page.status_code == 200
        assert next_page.headers.get("cache-control") == "no-cache"
        assert "Backlot — 项目库" in next_page.text
        assert 'id="root"' in next_page.text
        assert board.status_code == 200
        assert 'id="root"' in board.text
        assert assets, "ui-dist assets missing; run npm run build in backlot/frontend"
        asset = client.get(f"/next/assets/{assets[0].name}")
        assert asset.status_code == 200

    def test_next_404_when_dist_missing_does_not_take_default(self, projects_root, monkeypatch, tmp_path):
        async def no_watch():
            return None

        monkeypatch.setattr(server_mod, "_watch_projects", no_watch)
        monkeypatch.setattr(server_mod, "schedule_server_exit", lambda: None)
        monkeypatch.setattr(server_mod, "UI_NEXT_DIR", tmp_path / "missing-ui-dist")
        with TestClient(server_mod.create_app()) as missing:
            next_page = missing.get("/next/")
            home = missing.get("/")

        assert next_page.status_code == 404
        assert next_page.json()["detail"]["code"] == "next_frontend_missing"
        assert home.status_code == 200
        assert 'id="runner-occupant"' in home.text

    def test_projects_shape_and_state(self, client, projects_root):
        _make_project(projects_root, "film")

        projects = client.get("/api/projects")
        assert projects.status_code == 200
        body = projects.json()
        assert len(body) == 1
        assert body[0]["project_id"] == "film"
        assert body[0]["awaiting_human"] is True
        assert "stage_states" in body[0]

        state = client.get("/api/project/film/state")
        assert state.status_code == 200
        state_body = state.json()
        assert state_body["project_id"] == "film"
        assert state_body["title"] == "Film"
        assert state_body["stages"]

    @pytest.mark.parametrize(
        ("url", "status"),
        [
            ("/api/project/../state", 404),
            ("/api/project/C:/state", 400),
            ("/api/project/nope/state", 404),
        ],
    )
    def test_project_id_rejects_bad_or_unknown_ids(self, client, url, status):
        response = client.get(url)
        assert response.status_code == status

    def test_media_rejects_path_traversal(self, client, projects_root):
        _make_project(projects_root, "film")
        response = client.get("/media/film/%2E%2E/project.json")
        assert response.status_code == 403

    def test_media_serves_range_requests(self, client, projects_root):
        project = _make_project(projects_root, "film")
        media = project / "renders" / "final.mp4"
        media.write_bytes(b"0123456789")

        response = client.get("/media/film/renders/final.mp4", headers={"Range": "bytes=2-5"})

        assert response.status_code == 206
        assert response.content == b"2345"
        assert response.headers["content-range"].startswith("bytes 2-5/10")

    def test_thumb_downscales_image_and_passes_through_non_media(self, client, projects_root):
        project = _make_project(projects_root, "film")
        _write_png(project / "assets" / "images" / "sc1.png")
        text = project / "artifacts" / "note.txt"
        text.write_text("hello", encoding="utf-8")

        image = client.get("/thumb/film/assets/images/sc1.png?w=320")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/jpeg"
        assert image.content.startswith(b"\xff\xd8")

        passthrough = client.get("/thumb/film/artifacts/note.txt")
        assert passthrough.status_code == 200
        assert passthrough.content == b"hello"


class TestBacklotPerformanceBudgets:
    def test_projects_and_state_stay_within_loose_budgets(self, client, projects_root):
        for i in range(25):
            project = _make_project(projects_root, f"film-{i:02d}")
            _write_json(
                project / "artifacts" / "scene_plan.json",
                {"version": "1.0", "scenes": [{"id": "sc1", "start_seconds": 0, "end_seconds": 1}]},
            )

        t0 = time.perf_counter()
        cold = client.get("/api/projects")
        cold_s = time.perf_counter() - t0
        assert cold.status_code == 200
        assert cold_s < 2.0

        t1 = time.perf_counter()
        warm = client.get("/api/projects")
        warm_s = time.perf_counter() - t1
        assert warm.status_code == 200
        assert warm_s < 0.150

        t2 = time.perf_counter()
        state = client.get("/api/project/film-00/state")
        state_s = time.perf_counter() - t2
        assert state.status_code == 200
        assert state_s < 0.400

    def test_image_thumb_generation_stays_within_budget(self, client, projects_root):
        project = _make_project(projects_root, "film")
        _write_png(project / "assets" / "images" / "sc1.png")

        t0 = time.perf_counter()
        response = client.get("/thumb/film/assets/images/sc1.png?w=640")
        elapsed = time.perf_counter() - t0

        assert response.status_code == 200
        assert elapsed < 1.5


    def test_runtime_stop_requires_confirm(self, client):
        response = client.post("/api/runtime/stop", json={})
        assert response.status_code == 400

    def test_runtime_stop_blocks_when_producing(self, client, projects_root, monkeypatch):
        project = _make_project(projects_root, "busy")
        _write_json(
            project / "artifacts" / "produce_job.json",
            {"status": "running", "engine": "paid_video"},
        )
        stopped = {"n": 0}
        monkeypatch.setattr("backlot.runner.stop_runner", lambda: stopped.__setitem__("n", 1))
        response = client.post("/api/runtime/stop", json={"confirm": True})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "producing"
        assert stopped["n"] == 0

    def test_runtime_stop_ok_when_idle(self, client, monkeypatch):
        stopped = {"n": 0}
        monkeypatch.setattr("backlot.runner.stop_runner", lambda: stopped.__setitem__("n", 1))
        response = client.post("/api/runtime/stop", json={"confirm": True})
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert stopped["n"] == 1


    def test_release_runner_requires_confirm(self, client):
        response = client.post("/api/library/release-runner", json={})
        assert response.status_code == 400

    def test_release_runner_blocks_when_producing(self, client, projects_root, monkeypatch):
        project = _make_project(projects_root, "busy")
        _write_json(
            project / "artifacts" / "produce_job.json",
            {"status": "running", "engine": "paid_video"},
        )
        stopped = {"n": 0}
        exits = {"n": 0}
        monkeypatch.setattr("backlot.runner.stop_runner", lambda: stopped.__setitem__("n", 1))
        monkeypatch.setattr(server_mod, "schedule_server_exit", lambda: exits.__setitem__("n", 1))
        response = client.post("/api/library/release-runner", json={"confirm": True})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "producing"
        assert stopped["n"] == 0
        assert exits["n"] == 0

    def test_release_runner_ok_when_idle_keeps_server(self, client, monkeypatch):
        stopped = {"n": 0}
        exits = {"n": 0}
        monkeypatch.setattr("backlot.runner.stop_runner", lambda: stopped.__setitem__("n", 1))
        monkeypatch.setattr(server_mod, "schedule_server_exit", lambda: exits.__setitem__("n", 1))
        monkeypatch.setattr("backlot.runner.runner_alive", lambda: True)
        monkeypatch.setattr("backlot.runner.active_project_id", lambda: "film-idle")
        response = client.post("/api/library/release-runner", json={"confirm": True})
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert stopped["n"] == 1
        assert exits["n"] == 0
        assert "网页服务还在" in payload["friendly_zh"]
        assert "已中断" in payload["friendly_zh"]

    def test_release_runner_interrupt_when_producing(self, client, projects_root, monkeypatch):
        project = _make_project(projects_root, "busy")
        _write_json(
            project / "artifacts" / "produce_job.json",
            {"status": "running", "engine": "paid_video"},
        )
        stopped = {"n": 0}
        exits = {"n": 0}
        monkeypatch.setattr("backlot.runner.stop_runner", lambda: stopped.__setitem__("n", 1))
        monkeypatch.setattr(server_mod, "schedule_server_exit", lambda: exits.__setitem__("n", 1))
        monkeypatch.setattr("backlot.runner.runner_alive", lambda: True)
        monkeypatch.setattr("backlot.runner.active_project_id", lambda: "busy")
        blocked = client.post("/api/library/release-runner", json={"confirm": True})
        assert blocked.status_code == 409
        response = client.post(
            "/api/library/release-runner",
            json={"confirm": True, "interrupt": True},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert stopped["n"] == 1
        assert exits["n"] == 0
        marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
        assert marker["lifecycle_status"] == "interrupted"


class TestFindingsFixes:
    """Regression tests for dogfood findings F-03 (thumb video fallback)."""

    def test_thumb_never_serves_raw_video_bytes(self, client, projects_root):
        p = _make_project(projects_root, "vid")
        fake_video = p / "renders" / "final.mp4"
        fake_video.parent.mkdir(parents=True, exist_ok=True)
        # Not a real video: ffmpeg poster extraction will fail.
        fake_video.write_bytes(b"\x00" * 4096)
        res = client.get("/thumb/vid/renders/final.mp4")
        assert res.status_code == 404  # never the raw video bytes (F-03)

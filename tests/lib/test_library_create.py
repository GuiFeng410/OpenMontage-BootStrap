import json
from pathlib import Path

import pytest

from lib.library_create import (
    LibraryCreateError,
    continue_library_project,
    create_library_project,
    list_commercial_video_models,
    public_install_flags,
    refresh_key_availability,
    slug_project_id,
    start_production,
)
from openmontage.mcp.bootstrap.install_state import snapshot_install_state


@pytest.fixture(autouse=True)
def _isolate_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backlot.runner.active_project_id", lambda: "")
    monkeypatch.setattr("backlot.runner.runner_alive", lambda: False)


def test_flags_default_not_ready(tmp_path: Path) -> None:
    flags = public_install_flags(repo_root=tmp_path)
    assert flags["install_state_exists"] is False
    assert flags["verify_ready"] is False
    assert flags["video_key_present"] is False
    assert flags["stock_key_present"] is False
    assert flags["video_models"][0]["id"] == "agnes-video-v2.0"
    assert flags["video_models"][0]["available"] is False
    assert flags["video_models"][0]["board_generate"] is True
    assert flags["video_models"][1]["id"] == "hy-video-1.5"
    assert flags["video_models"][1]["board_generate"] is True
    assert flags["video_models"][2]["id"] == "pixverse-video-v6.0"
    assert flags["video_models"][2]["board_generate"] is True
    image_ids = [item["id"] for item in flags["image_models"]]
    assert image_ids[0] == "dashscope"
    assert "agnes" in image_ids
    assert "pixverse" not in image_ids


def test_tokenhub_alias_marks_key_ready_and_board_generate() -> None:
    models = {item["id"]: item for item in list_commercial_video_models(["TENCENT_TOKENHUB_API_KEY"])}
    assert models["agnes-video-v2.0"]["available"] is False
    assert models["hy-video-1.5"]["key_ready"] is True
    assert models["hy-video-1.5"]["board_generate"] is True
    assert models["hy-video-1.5"]["available"] is True
    assert models["pixverse-video-v6.0"]["key_ready"] is True
    assert models["pixverse-video-v6.0"]["board_generate"] is True
    assert models["pixverse-video-v6.0"]["available"] is True


def test_flags_live_scan_env_ignores_stale_install_state(tmp_path: Path) -> None:
    snapshot_install_state(repo_root=tmp_path, verify_ready=True, environ={})
    (tmp_path / ".env-example.md").write_text(EXAMPLE, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "TOKENHUB_API_KEY=th-secret-do-not-leak-live\n",
        encoding="utf-8",
    )
    flags = public_install_flags(repo_root=tmp_path)
    assert flags["video_key_present"] is True
    assert "TOKENHUB_API_KEY" in flags["video_key_names_present"]
    models = {item["id"]: item for item in flags["video_models"]}
    assert models["hy-video-1.5"]["key_ready"] is True
    assert models["hy-video-1.5"]["available"] is True
    assert models["pixverse-video-v6.0"]["key_ready"] is True
    assert models["pixverse-video-v6.0"]["available"] is True
    assert models["agnes-video-v2.0"]["available"] is False
    assert "th-secret-do-not-leak-live" not in str(flags)


def test_create_requires_title(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    with pytest.raises(LibraryCreateError) as caught:
        create_library_project(title="  ", repo_root=tmp_path)
    assert caught.value.code == "missing_title"


def test_create_patches_review_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    snapshot_install_state(repo_root=tmp_path, verify_ready=True)
    result = create_library_project(
        title="Jade Bangle",
        review_mode="pro",
        duration_seconds=20,
        asset_location="https://example.com/jade",
        repo_root=tmp_path,
        asset_files=[("hero.png", b"fake-image")],
    )
    assert result["ok"] is True
    project_dir = tmp_path / "projects" / result["project_id"]
    assert result["board_path"] == f"/p/{result['project_id']}"
    marker = (project_dir / "project.json").read_text(encoding="utf-8")
    assert '"review_mode": "pro"' in marker
    assert '"review_mode_preset": "pro"' in marker
    assert '"asset_location": "https://example.com/jade"' in marker
    assert '"duration_seconds": 20' in marker
    assert (project_dir / "assets" / "images" / "hero.png").read_bytes() == b"fake-image"
    assert result["imported_count"] == 1


def test_slug_falls_back_for_chinese_title() -> None:
    assert slug_project_id("翡翠手镯").startswith("commercial-")
    assert "jade" in slug_project_id("Jade Bangle")


EXAMPLE = """
## 【二、视频生成专项服务】

AGNES_API_KEY=
TOKENHUB_API_KEY=
KLING_API_KEY=
"""


def _write_ready_project(tmp_path: Path, project_id: str = "shop-demo") -> Path:
    project_dir = tmp_path / "projects" / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(
        '{"project_id":"shop-demo","title":"Shop","pipeline_type":"bootstrap-commercial"}',
        encoding="utf-8",
    )
    (tmp_path / ".env-example.md").write_text(EXAMPLE, encoding="utf-8")
    return project_dir


def test_refresh_then_keys_become_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    (tmp_path / ".env-example.md").write_text(EXAMPLE, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "TOKENHUB_API_KEY=\nPEXELS_API_KEY=\n",
        encoding="utf-8",
    )
    empty = refresh_key_availability(repo_root=tmp_path, environ={})
    assert empty["video_key_present"] is False
    assert empty["stock_key_present"] is False
    (tmp_path / ".env").write_text(
        "TOKENHUB_API_KEY=th-secret-do-not-leak-aaa\nPEXELS_API_KEY=px-secret-do-not-leak-bbb\n",
        encoding="utf-8",
    )
    filled = refresh_key_availability(repo_root=tmp_path, environ={})
    assert filled["video_key_present"] is True
    assert filled["stock_key_present"] is True
    dumped = str(filled)
    assert "th-secret-do-not-leak-aaa" not in dumped
    assert "px-secret-do-not-leak-bbb" not in dumped


def test_refresh_reports_multiple_image_models_without_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    (tmp_path / ".env-example.md").write_text(EXAMPLE, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "DASHSCOPE_API_KEY=sk-dash-secret-do-not-leak\n"
        "AGNES_API_KEY=ag-secret-do-not-leak\n"
        "FAL_KEY=fal-secret-do-not-leak\n",
        encoding="utf-8",
    )
    filled = refresh_key_availability(repo_root=tmp_path, environ={})
    assert filled["image_key_present"] is True
    models = {item["id"]: item for item in filled["image_models"]}
    assert models["dashscope"]["available"] is True
    assert models["agnes"]["available"] is True
    assert models["flux"]["available"] is True
    available_count = sum(1 for item in filled["image_models"] if item.get("available"))
    assert available_count >= 3
    assert "全片共用" in filled["friendly_zh"]
    dumped = str(filled)
    assert "sk-dash-secret-do-not-leak" not in dumped
    assert "ag-secret-do-not-leak" not in dumped
    assert "fal-secret-do-not-leak" not in dumped


def test_start_production_blocks_heavy_without_video_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    _write_ready_project(tmp_path)
    (tmp_path / ".env").write_text("TOKENHUB_API_KEY=\n", encoding="utf-8")
    with pytest.raises(LibraryCreateError) as caught:
        start_production(
            project_id="shop-demo",
            production_tier="heavy",
            repo_root=tmp_path,
            environ={},
        )
    assert caught.value.code == "missing_video_key"
    marker = (tmp_path / "projects" / "shop-demo" / "project.json").read_text(encoding="utf-8")
    assert "production_tier" not in marker


def test_start_production_blocks_medium_without_stock_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    _write_ready_project(tmp_path)
    (tmp_path / ".env").write_text("PEXELS_API_KEY=\n", encoding="utf-8")
    with pytest.raises(LibraryCreateError) as caught:
        start_production(
            project_id="shop-demo",
            production_tier="medium",
            repo_root=tmp_path,
            environ={},
        )
    assert caught.value.code == "missing_stock_key"


def test_start_production_locks_light_and_heavy_when_keys_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    project_dir = _write_ready_project(tmp_path)
    (tmp_path / ".env").write_text(
        "AGNES_API_KEY=ag-secret-do-not-leak-ccc\nPEXELS_API_KEY=px-secret-do-not-leak-ddd\n",
        encoding="utf-8",
    )
    light = start_production(
        project_id="shop-demo",
        production_tier="light",
        repo_root=tmp_path,
        environ={},
    )
    assert light["production_tier"] == "light"
    heavy = start_production(
        project_id="shop-demo",
        production_tier="heavy",
        repo_root=tmp_path,
        environ={},
    )
    assert heavy["ok"] is True
    assert heavy["production_tier"] == "heavy"
    marker = (project_dir / "project.json").read_text(encoding="utf-8")
    assert '"production_tier": "heavy"' in marker
    assert "ag-secret-do-not-leak-ccc" not in marker
    assert "ag-secret-do-not-leak-ccc" not in str(heavy)


def test_start_production_seeds_stop_card_without_recommend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    project_dir = _write_ready_project(tmp_path)
    (tmp_path / ".env").write_text("TOKENHUB_API_KEY=\n", encoding="utf-8")
    result = start_production(
        project_id="shop-demo",
        production_tier="light",
        repo_root=tmp_path,
        environ={},
    )
    assert result["next_stop"] == "brief_locked"
    assert "请留在本页" in result["friendly_zh"]
    checkpoint = json.loads(
        (project_dir / "checkpoint_brief_locked.json").read_text(encoding="utf-8")
    )
    options = checkpoint["metadata"]["decision_options"]
    assert options
    assert all("recommended" not in item for item in options)
    assert "recommendation_zh" not in checkpoint["metadata"]
    marker = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    assert marker["production_profile"]["runner_start_pending"] is False
    assert marker["board_stop"]["stage"] == "brief_locked"
    assert all(
        "recommended" not in item
        for item in marker["board_stop"]["decision_options"]
    )


def test_start_production_persists_ai_share_pct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    project_dir = _write_ready_project(tmp_path)
    (tmp_path / ".env").write_text(
        "AGNES_API_KEY=ag-secret-do-not-leak-eee\nPEXELS_API_KEY=px-secret-do-not-leak-fff\n",
        encoding="utf-8",
    )
    heavy = start_production(
        project_id="shop-demo",
        production_tier="heavy",
        ai_share_pct=70,
        video_model="agnes-video-v2.0",
        repo_root=tmp_path,
        environ={},
    )
    assert heavy["ai_share_pct"] == 70
    assert heavy["motion_mix"] == "1:2"
    assert heavy["video_model"] == "agnes-video-v2.0"
    assert heavy["video_channel"] == "agnes"
    marker = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    assert marker["production_profile"]["ai_share_pct"] == 70
    assert marker["production_profile"]["motion_mix"] == "1:2"
    assert marker["production_profile"]["video_model"] == "agnes-video-v2.0"


def test_start_production_defaults_to_first_available_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    project_dir = _write_ready_project(tmp_path)
    (tmp_path / ".env").write_text(
        "AGNES_API_KEY=ag-secret-do-not-leak\nTOKENHUB_API_KEY=th-secret-do-not-leak-ggg\n",
        encoding="utf-8",
    )
    heavy = start_production(
        project_id="shop-demo",
        production_tier="heavy",
        repo_root=tmp_path,
        environ={},
    )
    assert heavy["video_model"] == "agnes-video-v2.0"
    assert heavy["ai_share_pct"] == 100
    assert heavy["motion_mix"] == "0:1"
    marker = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    assert marker["production_profile"]["video_model"] == "agnes-video-v2.0"
    assert marker["production_profile"]["ai_video"] == "enabled"


def test_start_production_rejects_model_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    _write_ready_project(tmp_path)
    (tmp_path / ".env").write_text(
        "TOKENHUB_API_KEY=th-secret-do-not-leak-hhh\n",
        encoding="utf-8",
    )
    with pytest.raises(LibraryCreateError) as caught:
        start_production(
            project_id="shop-demo",
            production_tier="heavy",
            video_model="agnes-video-v2.0",
            repo_root=tmp_path,
            environ={},
        )
    assert caught.value.code == "missing_model_key"


def test_start_production_accepts_pixverse_with_tokenhub_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    _write_ready_project(tmp_path)
    (tmp_path / ".env").write_text(
        "TOKENHUB_API_KEY=th-secret-do-not-leak-pix\n",
        encoding="utf-8",
    )
    result = start_production(
        project_id="shop-demo",
        production_tier="heavy",
        video_model="pixverse-video-v6.0",
        repo_root=tmp_path,
        environ={},
    )
    assert result["ok"] is True
    marker = json.loads(
        (tmp_path / "projects" / "shop-demo" / "project.json").read_text(encoding="utf-8")
    )
    assert marker["production_profile"]["video_model"] == "pixverse-video-v6.0"
    assert marker["production_profile"]["video_channel"] == "tokenhub"


def test_create_blocked_when_runner_busy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr("backlot.runner.runner_alive", lambda: True)
    monkeypatch.setattr("backlot.runner.active_project_id", lambda: "other-pro")
    with pytest.raises(LibraryCreateError) as caught:
        create_library_project(title="Jade", repo_root=tmp_path)
    assert caught.value.code == "runner_busy"
    assert caught.value.http_status == 409


def test_continue_rejects_completed_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    snapshot_install_state(repo_root=tmp_path, verify_ready=True)
    project = tmp_path / "projects" / "shop-demo"
    project.mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps(
            {
                "project_id": "shop-demo",
                "pipeline_type": "bootstrap-commercial",
                "lifecycle_status": "completed",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(LibraryCreateError) as caught:
        continue_library_project(project_id="shop-demo", repo_root=tmp_path)
    assert caught.value.code == "already_completed"


def test_continue_same_project_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    snapshot_install_state(repo_root=tmp_path, verify_ready=True)
    monkeypatch.setattr("backlot.runner.runner_alive", lambda: True)
    monkeypatch.setattr("backlot.runner.active_project_id", lambda: "shop-demo")
    project = tmp_path / "projects" / "shop-demo"
    project.mkdir(parents=True)
    (project / "project.json").write_text(
        json.dumps(
            {
                "project_id": "shop-demo",
                "pipeline_type": "bootstrap-commercial",
                "board_stop": {"stage": "assets_gate", "decision_prompt_zh": "素材检查"},
            }
        ),
        encoding="utf-8",
    )
    result = continue_library_project(project_id="shop-demo", repo_root=tmp_path)
    assert result["ok"] is True
    assert result["project_id"] == "shop-demo"
    assert result["current_stop"] == "assets_gate"
    assert result["spawn_runner"] is True

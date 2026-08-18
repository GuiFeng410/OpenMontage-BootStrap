"""Minimal board produce starts local compose and never downgrades paid tiers."""

from __future__ import annotations

import json
from pathlib import Path

import lib.board_produce as board_produce
from tests.lib.test_board_advance import _seed_minimal_ready_for_delivery, _write_project


def _marker(project: Path) -> dict:
    return json.loads((project / "project.json").read_text(encoding="utf-8"))


def _set_profile(project: Path, **fields) -> dict:
    marker = _marker(project)
    profile = marker.get("production_profile")
    if not isinstance(profile, dict):
        profile = {}
    profile.update(fields)
    marker["production_profile"] = profile
    (project / "project.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return marker


def _stub_start(*_args, **_kwargs):
    return {"job_id": "compose-job-1", "output_path": "renders/final.mp4"}


def test_maybe_start_writes_light_compose_job(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    calls: list[tuple] = []

    def starter(edit_json, manifest_json, output=""):
        calls.append((edit_json, manifest_json, output))
        return _stub_start()

    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=starter,
    )
    assert result["action"] == "produce_start"
    assert result["status"] == board_produce.STATUS_QUEUED
    assert calls
    job = json.loads(
        (root / "shop-demo" / "artifacts" / "produce_job.json").read_text(
            encoding="utf-8"
        )
    )
    assert job["engine"] == "compose"
    assert job["job_id"] == "compose-job-1"
    overlay = _marker(root / "shop-demo")
    assert overlay["board_stop"]["producing_wait"] is True
    assert "轻度合成" in overlay["board_stop"]["decision_prompt_zh"]
    assert "1–3 分钟" in overlay["board_stop"]["decision_prompt_zh"]


def test_maybe_start_skips_when_assets_gate_open(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
    )
    assert result["skipped"] is True
    assert result["status"] == board_produce.STATUS_SKIPPED


def test_maybe_start_skips_non_minimal(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    marker = _set_profile(root / "shop-demo", review_mode_preset="normal")
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
    )
    assert result["skipped"] is True


def test_heavy_without_key_pauses_and_does_not_compose(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    marker = _set_profile(
        root / "shop-demo",
        production_tier="heavy",
        provider="agnes",
        video_channel="agnes",
    )
    monkeypatch.setattr(board_produce, "_present_key_names", lambda: set())
    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
    )
    assert result["action"] == "produce_paused"
    assert result["job"]["code"] == "video_key_missing"
    assert "不降为轻度" in result["job"]["friendly_zh"]
    assert (root / "shop-demo" / "production_profile.json").exists() is False
    still = _marker(root / "shop-demo")
    assert still["production_profile"]["production_tier"] == "heavy"


def test_heavy_with_key_starts_paid_generate(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    marker = _set_profile(
        root / "shop-demo",
        production_tier="heavy",
        provider="agnes",
        video_channel="agnes",
        resolution="1080x1920",
    )
    monkeypatch.setattr(board_produce, "_present_key_names", lambda: {"AGNES_API_KEY"})
    gen_calls: list[dict] = []

    def generate(provider, prompt, output_path, extras_json="{}", confirm=False, confirm_sample_ok=False):
        gen_calls.append(
            {
                "provider": provider,
                "prompt": prompt,
                "output_path": output_path,
                "extras_json": extras_json,
                "confirm": confirm,
                "confirm_sample_ok": confirm_sample_ok,
            }
        )
        dest = root / output_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"clip")
        return {"success": True, "output_path": str(dest)}

    def starter(edit_json, _manifest_json, _output=""):
        edit = json.loads(edit_json)
        assert edit["cuts"][0]["source"].startswith("assets/video/seg_")
        renders = root / "shop-demo" / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        (renders / "final.mp4").write_bytes(b"film")
        return _stub_start()

    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=starter,
        video_generate=generate,
        paid_inline=True,
    )
    assert result["action"] == "produce_start"
    assert result["job"]["engine"] == "paid_video"
    assert gen_calls
    assert gen_calls[0]["confirm"] is True
    assert gen_calls[0]["confirm_sample_ok"] is True
    assert gen_calls[0]["provider"] == "agnes"
    extras = json.loads(gen_calls[0]["extras_json"])
    assert extras["operation"] == "image_to_video"
    assert extras["aspect_ratio"] == "9:16"
    assert extras["image_path"]
    overlay = _marker(root / "shop-demo")
    assert "大约" in overlay["board_stop"]["decision_prompt_zh"] or result["job"]["status"] == board_produce.STATUS_DONE
    assert still_tier(root / "shop-demo") == "heavy"


def still_tier(project: Path) -> str:
    return str(_marker(project)["production_profile"]["production_tier"])


def test_medium_stock_without_key_pauses(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    marker = _set_profile(
        root / "shop-demo",
        production_tier="medium",
        medium_source="stock",
    )
    monkeypatch.setattr(board_produce, "_present_key_names", lambda: set())
    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
    )
    assert result["job"]["code"] == "stock_key_missing"


def test_medium_user_assets_composes_like_light(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    marker = _set_profile(
        root / "shop-demo",
        production_tier="medium",
        medium_source="user_assets",
    )
    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=_stub_start,
    )
    assert result["action"] == "produce_start"


def test_light_does_not_call_video_generate(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=_stub_start,
        video_generate=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("no generate")
        ),
    )
    assert result["action"] == "produce_start"
    assert result["job"]["engine"] == "compose"


def test_heavy_unknown_channel_pauses(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    marker = _set_profile(
        root / "shop-demo",
        production_tier="heavy",
        provider="pixverse",
        video_channel="pixverse",
    )
    monkeypatch.setattr(board_produce, "_present_key_names", lambda: {"PIXVERSE_API_KEY"})
    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
        video_generate=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no generate")),
    )
    assert result["action"] == "produce_paused"
    assert result["job"]["code"] == "video_channel_missing"


def test_heavy_skips_existing_segment_file(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    marker = _set_profile(
        root / "shop-demo",
        production_tier="heavy",
        provider="agnes",
        video_channel="agnes",
    )
    monkeypatch.setattr(board_produce, "_present_key_names", lambda: {"AGNES_API_KEY"})
    dest = root / "shop-demo" / "assets" / "video"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "seg_beat_01.mp4").write_bytes(b"clip")
    gen_calls: list = []

    def starter(_edit_json, _manifest_json, _output=""):
        renders = root / "shop-demo" / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        (renders / "final.mp4").write_bytes(b"film")
        return _stub_start()

    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=starter,
        video_generate=lambda *_a, **_k: gen_calls.append(1) or {"success": True},
        paid_inline=True,
    )
    assert result["action"] == "produce_start"
    assert gen_calls == []


def test_poll_marks_done_when_final_exists(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    project = root / "shop-demo"
    (project / "artifacts").mkdir(parents=True, exist_ok=True)
    (project / "renders").mkdir(parents=True, exist_ok=True)
    board_produce.write_job(
        "shop-demo",
        {"status": board_produce.STATUS_RUNNING, "job_id": "j1"},
        projects_dir=root,
    )
    (project / "renders" / "final.mp4").write_bytes(b"film")
    result = board_produce.poll("shop-demo", projects_dir=root)
    assert result["status"] == board_produce.STATUS_DONE


def test_poll_records_compose_failure(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    board_produce.write_job(
        "shop-demo",
        {"status": board_produce.STATUS_RUNNING, "job_id": "j1"},
        projects_dir=root,
    )
    result = board_produce.poll(
        "shop-demo",
        projects_dir=root,
        job_status=lambda _jid: {"status": "failed", "error": "Remotion 退出码 1"},
    )
    assert result["status"] == board_produce.STATUS_FAILED
    assert "Remotion" in result["job"]["friendly_zh"]

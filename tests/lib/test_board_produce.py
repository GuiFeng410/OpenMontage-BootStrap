"""Minimal board produce starts local compose and never downgrades paid tiers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_atomic_json_write_retries_transient_permission_error(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "state.json"
    original_replace = board_produce.os.replace
    attempts = 0

    def flaky_replace(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("transient sharing violation")
        return original_replace(source, destination)

    monkeypatch.setattr(board_produce.os, "replace", flaky_replace)

    board_produce._write_json(target, {"ready": True})

    assert attempts == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"ready": True}


def test_maybe_start_writes_light_compose_job(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    calls: list[tuple] = []

    def starter(edit_json, manifest_json, output=""):
        calls.append((edit_json, manifest_json, output))
        reserved = json.loads(
            (root / "shop-demo" / "artifacts" / "produce_job.json").read_text(
                encoding="utf-8"
            )
        )
        assert reserved["status"] == board_produce.STATUS_QUEUED
        assert reserved["job_id"] == ""
        assert reserved["job_key"].startswith("job_")
        assert (root / "shop-demo" / "production_run.json").is_file()
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
    assert job["version"] == "2.0"
    assert job["expected_outputs"] == [
        "renders/final.mp4",
        "artifacts/final_review.json",
    ]
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


def test_maybe_start_skips_professional(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    marker = _set_profile(root / "shop-demo", review_mode_preset="pro")
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
    )
    assert result["skipped"] is True


def test_maybe_start_normal_light_skips_until_heavy_sample(tmp_path: Path) -> None:
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
        video_model="agnes-video-v2.0",
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
    assert extras["model"] == "agnes-video-v2.0"
    project = root / "shop-demo"
    overview = json.loads(
        (project / "artifacts" / "review_overview.json").read_text(encoding="utf-8")
    )
    final_review = json.loads(
        (project / "artifacts" / "final_review.json").read_text(encoding="utf-8")
    )
    assert overview["status"] == "completed"
    assert overview["overview"][0]["output_path"].startswith(
        "assets/video/seg_beat_01_"
    )
    assert final_review["status"] == "pass"
    assert final_review["output_path"] == "renders/final.mp4"
    segment_checkpoint = json.loads(
        (project / "checkpoint_segment_build.json").read_text(encoding="utf-8")
    )
    final_checkpoint = json.loads(
        (project / "checkpoint_final_compose.json").read_text(encoding="utf-8")
    )
    assert segment_checkpoint["status"] == "completed"
    assert final_checkpoint["status"] == "completed"
    run = json.loads((project / "production_run.json").read_text(encoding="utf-8"))
    assert run["stage_results"]["sample_review"]["status"] == "not_required"
    assert run["stage_results"]["draft_review"]["status"] == "not_required"
    assert run["stage_results"]["segment_build"]["status"] == "completed"
    assert run["stage_results"]["final_compose"]["status"] == "completed"
    segment_jobs = [
        item
        for item in run["task_summaries"]
        if item["stage"] == "segment_build" and item["kind"] == "segment"
    ]
    assert [item["batch_id"] for item in segment_jobs] == ["beat_01"]
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
        provider="madeup",
        video_channel="madeup-channel",
    )
    monkeypatch.setattr(board_produce, "_present_key_names", lambda: {"AGNES_API_KEY"})
    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
        video_generate=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no generate")),
    )
    assert result["action"] == "produce_paused"
    assert result["job"]["code"] == "video_channel_missing"
    assert "看板本机分段目前不能走该渠道" in result["job"]["friendly_zh"]
    overlay = json.loads((root / "shop-demo" / "project.json").read_text(encoding="utf-8"))
    assert overlay["board_stop"]["paused"] is True
    assert overlay["board_stop"]["producing_wait"] is False
    assert overlay["board_stop"]["decision_title_zh"] == "已暂停"


def test_heavy_pixverse_with_tokenhub_starts(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    marker = _set_profile(
        root / "shop-demo",
        production_tier="heavy",
        provider="tokenhub",
        video_channel="tokenhub",
        video_model="pixverse-video-v6.0",
    )
    monkeypatch.setattr(
        board_produce, "_present_key_names", lambda: {"TOKENHUB_API_KEY"}
    )
    calls: list[str] = []

    def generate(provider, _prompt, output_path, extras_json="{}", confirm=False, confirm_sample_ok=False):
        calls.append(provider)
        dest = root / output_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"clip")
        extras = json.loads(extras_json)
        assert extras["model"] == "pixverse-video-v6.0"
        assert extras["image_path"]
        return {"success": True, "output_path": str(dest)}

    def starter(_edit, _manifest, _output=""):
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
    assert result["action"] == "produce_start", {
        "code": (result.get("job") or {}).get("code"),
        "friendly": (result.get("job") or {}).get("friendly_zh"),
        "error": (result.get("job") or {}).get("error"),
        "calls": calls,
    }
    assert calls == ["tokenhub"]
    assert (root / "shop-demo" / "renders" / "final.mp4").is_file()


def test_resolve_video_generate_routes_tokenhub() -> None:
    assert (
        board_produce._resolve_video_generate("tokenhub", None)
        is board_produce._board_tokenhub_generate
    )
    assert (
        board_produce._resolve_video_generate("pixverse", None)
        is board_produce._board_tokenhub_generate
    )


def test_normal_heavy_writes_sample_not_final(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    project = root / "shop-demo"
    marker = _set_profile(
        project,
        review_mode_preset="normal",
        production_tier="heavy",
        provider="agnes",
        video_channel="agnes",
        video_model="agnes-video-v2.0",
    )
    monkeypatch.setattr(board_produce, "_present_key_names", lambda: {"AGNES_API_KEY"})
    outputs: list[str] = []

    def generate(_provider, _prompt, output_path, extras_json="{}", confirm=False, confirm_sample_ok=False):
        outputs.append(output_path)
        dest = root / output_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"clip")
        return {"success": True, "output_path": str(dest)}

    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
        video_generate=generate,
        paid_inline=True,
    )
    assert result["action"] == "produce_start"
    assert outputs and "sample_" in outputs[0]
    assert "seg_" not in Path(outputs[0]).name
    reel = json.loads((project / "artifacts" / "sample_reel.json").read_text(encoding="utf-8"))
    assert reel["path"].startswith("assets/video/sample_")
    assert not (project / "renders" / "final.mp4").exists()
    skipped = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
        video_generate=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no generate")),
        paid_inline=True,
    )
    assert skipped["skipped"] is True


def test_normal_heavy_continues_after_sample_review(tmp_path: Path, monkeypatch) -> None:
    from lib.checkpoint import merge_write_checkpoint

    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    project = root / "shop-demo"
    marker = _set_profile(
        project,
        review_mode_preset="normal",
        production_tier="heavy",
        provider="agnes",
        video_channel="agnes",
        video_model="agnes-video-v2.0",
    )
    monkeypatch.setattr(board_produce, "_present_key_names", lambda: {"AGNES_API_KEY"})
    outputs: list[str] = []

    def generate(_provider, _prompt, output_path, extras_json="{}", confirm=False, confirm_sample_ok=False):
        outputs.append(output_path)
        dest = root / output_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"clip")
        return {"success": True, "output_path": str(dest)}

    first = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
        video_generate=generate,
        paid_inline=True,
    )
    assert first["action"] == "produce_start"
    reel = json.loads((project / "artifacts" / "sample_reel.json").read_text(encoding="utf-8"))
    merge_write_checkpoint(
        root,
        "shop-demo",
        "sample_review",
        "completed",
        {"sample_reel": reel},
        pipeline_type="bootstrap-commercial",
        human_approval_required=True,
        human_approved=True,
    )

    second = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no compose")),
        video_generate=generate,
        paid_inline=True,
    )
    assert second["action"] == "produce_start", {
        "code": (second.get("job") or {}).get("code"),
        "friendly": (second.get("job") or {}).get("friendly_zh"),
        "error": (second.get("job") or {}).get("error"),
    }
    assert len(outputs) == 1
    assert "sample_" in outputs[0]
    revision = board_produce._locked_artifact_revision(project)
    assert (project / board_produce._seg_rel("beat_01", revision)).is_file()
    assert not (project / "renders" / "final.mp4").exists()
    draft = json.loads((project / "artifacts" / "full_draft_pro.json").read_text(encoding="utf-8"))
    merge_write_checkpoint(
        root,
        "shop-demo",
        "draft_review",
        "completed",
        {"full_draft_pro": draft},
        pipeline_type="bootstrap-commercial",
        human_approval_required=True,
        human_approved=True,
    )

    def starter(_edit, _manifest, _output=""):
        renders = project / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        (renders / "final.mp4").write_bytes(b"film")
        return _stub_start()

    third = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=starter,
        video_generate=generate,
        paid_inline=True,
    )
    assert third["action"] == "produce_start"
    assert len(outputs) == 1
    assert (project / "renders" / "final.mp4").is_file()


def test_heavy_reuses_evidenced_segment_for_same_revision(
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
    monkeypatch.setattr(board_produce, "_present_key_names", lambda: {"AGNES_API_KEY"})
    project = root / "shop-demo"
    revision = board_produce._locked_artifact_revision(project)
    segment_rel = board_produce._seg_rel("beat_01", revision)
    segment_path = project / segment_rel
    segment_path.parent.mkdir(parents=True, exist_ok=True)
    segment_path.write_bytes(b"clip")
    (project / "artifacts" / "review_overview.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "overview": [
                    {
                        "beat": "beat_01",
                        "output_path": segment_rel,
                        "status": "completed",
                        "artifact_revision": revision,
                        "provider": "agnes",
                        "model": "",
                    }
                ],
                "batches": [],
                "artifact_revision": revision,
                "provider": "agnes",
                "model": "",
                "status": "completed",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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
    run = json.loads((project / "production_run.json").read_text(encoding="utf-8"))
    reused = [
        item
        for item in run["task_summaries"]
        if item["stage"] == "segment_build" and item["batch_id"] == "beat_01"
    ]
    assert len(reused) == 1
    assert reused[0]["status"] == board_produce.STATUS_DONE


def test_heavy_does_not_reuse_segment_from_old_revision(
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
    monkeypatch.setattr(board_produce, "_present_key_names", lambda: {"AGNES_API_KEY"})
    project = root / "shop-demo"
    old_revision = board_produce._locked_artifact_revision(project)
    old_rel = board_produce._seg_rel("beat_01", old_revision)
    old_path = project / old_rel
    old_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.write_bytes(b"old-clip")
    (project / "artifacts" / "review_overview.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "overview": [
                    {
                        "beat": "beat_01",
                        "output_path": old_rel,
                        "status": "completed",
                        "artifact_revision": old_revision,
                    }
                ],
                "batches": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    plan_path = project / "artifacts" / "video_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["revision_marker"] = "changed"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    new_revision = board_produce._locked_artifact_revision(project)
    assert new_revision != old_revision
    generated: list[str] = []

    def generate(_provider, _prompt, output_path, *_args):
        generated.append(output_path)
        dest = root / output_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"new-clip")
        return {"success": True}

    def starter(_edit_json, _manifest_json, _output=""):
        renders = project / "renders"
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
    assert len(generated) == 1
    assert board_produce._seg_rel("beat_01", new_revision) in generated[0]
    assert old_rel not in generated[0]


def test_compose_bundle_does_not_use_unevidenced_legacy_segment(
    tmp_path: Path,
) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    project = root / "shop-demo"
    legacy = project / "assets" / "video" / "seg_beat_01.mp4"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"stale")

    bundle = board_produce.build_compose_bundle(
        "shop-demo",
        projects_dir=root,
    )

    cut = bundle["edit_decisions"]["cuts"][0]
    assert cut["kind"] == "image"
    assert cut["source"] == "assets/images/001.png"
    assert bundle["edit_decisions"]["render_runtime"] == "remotion"
    assert bundle["edit_decisions"]["renderer_family"] == "product-reveal"


def test_compose_bundle_uses_ffmpeg_for_evidenced_video_cuts(tmp_path: Path) -> None:
    from lib.board_stage_artifacts import build_review_overview

    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    project = root / "shop-demo"
    revision = board_produce._locked_artifact_revision(project)
    rel = board_produce._seg_rel("beat_01", revision)
    dest = project / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"clip")
    overview = build_review_overview(
        [
            {
                "beat": "beat_01",
                "output_path": rel,
                "status": "completed",
                "artifact_revision": revision,
            }
        ],
        extra={"status": "completed", "artifact_revision": revision},
    )
    (project / "artifacts" / "review_overview.json").write_text(
        json.dumps(overview, ensure_ascii=False),
        encoding="utf-8",
    )

    bundle = board_produce.build_compose_bundle(
        "shop-demo",
        projects_dir=root,
    )

    cut = bundle["edit_decisions"]["cuts"][0]
    assert cut["kind"] == "video"
    assert cut["source"] == rel
    assert bundle["edit_decisions"]["render_runtime"] == "ffmpeg"
    assert "renderer_family" not in bundle["edit_decisions"]


def test_poll_marks_done_when_final_exists(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
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
    assert board_produce.final_ready_for_delivery("shop-demo", projects_dir=root)


def test_new_run_requires_completed_final_evidence_for_delivery(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    project = root / "shop-demo"
    (project / "renders").mkdir(parents=True, exist_ok=True)
    (project / "renders" / "final.mp4").write_bytes(b"film")
    board_produce.write_job(
        "shop-demo",
        {"status": board_produce.STATUS_RUNNING, "job_id": "j1"},
        projects_dir=root,
    )

    assert not board_produce.final_ready_for_delivery(
        "shop-demo", projects_dir=root
    )

    result = board_produce.poll("shop-demo", projects_dir=root)

    assert result["status"] == board_produce.STATUS_DONE
    assert board_produce.final_ready_for_delivery("shop-demo", projects_dir=root)


def test_final_checkpoint_failure_cannot_open_delivery(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    project = root / "shop-demo"
    (project / "renders").mkdir(parents=True, exist_ok=True)
    (project / "renders" / "final.mp4").write_bytes(b"film")
    board_produce.write_job(
        "shop-demo",
        {"status": board_produce.STATUS_RUNNING, "job_id": "j1"},
        projects_dir=root,
    )

    result = board_produce.poll("shop-demo", projects_dir=root)

    assert result["action"] == "produce_failed"
    assert result["job"]["code"] == "final_evidence_failed"
    assert (project / "artifacts" / "final_review.json").is_file()
    assert not (project / "checkpoint_final_compose.json").is_file()
    assert not board_produce.final_ready_for_delivery(
        "shop-demo", projects_dir=root
    )


def test_stale_final_review_revision_is_not_delivery_ready(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    project = root / "shop-demo"
    (project / "renders").mkdir(parents=True, exist_ok=True)
    board_produce.write_job(
        "shop-demo",
        {"status": board_produce.STATUS_RUNNING, "job_id": "j1"},
        projects_dir=root,
    )
    (project / "renders" / "final.mp4").write_bytes(b"film")
    assert board_produce.poll("shop-demo", projects_dir=root)["status"] == "done"
    review_path = project / "artifacts" / "final_review.json"
    old_review = review_path.read_text(encoding="utf-8")
    plan_path = project / "artifacts" / "video_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["revision_marker"] = "new-input"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    assert not board_produce.final_ready_for_delivery(
        "shop-demo", projects_dir=root
    )
    result = board_produce.maybe_start(
        "shop-demo",
        _marker(project),
        projects_dir=root,
    )
    assert result["action"] == "produce_failed"
    assert result["job"]["code"] == "final_evidence_failed"
    assert review_path.read_text(encoding="utf-8") == old_review


def test_remote_completion_materializes_evidence_before_done(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    project = root / "shop-demo"
    board_produce.write_job(
        "shop-demo",
        {"status": board_produce.STATUS_RUNNING, "job_id": "j1"},
        projects_dir=root,
    )

    def completed(_job_id):
        renders = project / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        (renders / "final.mp4").write_bytes(b"film")
        return {"status": "completed"}

    result = board_produce.poll(
        "shop-demo",
        projects_dir=root,
        job_status=completed,
    )

    assert result["status"] == board_produce.STATUS_DONE
    assert (project / "artifacts" / "final_review.json").is_file()
    checkpoint = json.loads(
        (project / "checkpoint_final_compose.json").read_text(encoding="utf-8")
    )
    assert checkpoint["status"] == "completed"
    assert board_produce.final_ready_for_delivery("shop-demo", projects_dir=root)


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


def test_invalid_run_state_blocks_start_without_overwriting_it(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    marker = _write_project(root)
    _seed_minimal_ready_for_delivery(root, "shop-demo")
    invalid = root / "shop-demo" / "production_run.json"
    invalid.write_text("{broken", encoding="utf-8")

    result = board_produce.maybe_start(
        "shop-demo",
        marker,
        projects_dir=root,
        compose_start=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("must not start compose")
        ),
    )

    assert result["status"] == board_produce.STATUS_PAUSED
    assert result["job"]["code"] == "run_state_invalid"
    assert invalid.read_text(encoding="utf-8") == "{broken"


def test_locked_artifact_revision_changes_with_plan_content(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    project = root / "shop-demo"
    artifacts = project / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    plan = artifacts / "video_plan.json"
    plan.write_text(json.dumps({"segments": [{"id": "beat_01"}]}), encoding="utf-8")
    first = board_produce._locked_artifact_revision(project)

    plan.write_text(json.dumps({"segments": [{"id": "beat_02"}]}), encoding="utf-8")
    second = board_produce._locked_artifact_revision(project)

    assert first.startswith("sha256:")
    assert second.startswith("sha256:")
    assert second != first


def test_poll_pauses_orphaned_job_without_retry(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    board_produce.write_job(
        "shop-demo",
        {"status": board_produce.STATUS_RUNNING, "job_id": ""},
        projects_dir=root,
    )

    result = board_produce.poll("shop-demo", projects_dir=root)

    assert result["action"] == "produce_paused"
    assert result["status"] == board_produce.STATUS_PAUSED
    assert result["job"]["code"] == "orphaned"
    assert result["job"]["orphaned"] is True
    assert result["job"]["attempt"] == 1


def test_poll_paid_running_without_job_id_does_not_orphan(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    board_produce.write_job(
        "shop-demo",
        {
            "status": board_produce.STATUS_RUNNING,
            "engine": "paid_video",
            "job_id": "",
            "stage": "segment_build",
            "kind": "segment",
            "batch_id": "B04",
            "beat_ids": ["B04"],
            "expected_outputs": [
                "assets/video/seg_B04.mp4",
                "artifacts/review_overview.json",
            ],
        },
        projects_dir=root,
    )

    result = board_produce.poll("shop-demo", projects_dir=root)

    assert result["action"] == ""
    assert result["status"] == board_produce.STATUS_RUNNING
    assert result["job"].get("code") != "orphaned"


def test_write_job_keeps_background_id_when_batch_changes(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    _write_project(root)
    board_produce.write_job(
        "shop-demo",
        {
            "status": board_produce.STATUS_QUEUED,
            "engine": "paid_video",
            "job_id": "media-job-1",
            "stage": "draft_review",
            "kind": "draft",
            "batch_id": "",
            "expected_outputs": [
                "artifacts/review_overview.json",
                "artifacts/full_draft_pro.json",
            ],
        },
        projects_dir=root,
    )
    written = board_produce.write_job(
        "shop-demo",
        {
            "status": board_produce.STATUS_RUNNING,
            "engine": "paid_video",
            "stage": "segment_build",
            "kind": "segment",
            "batch_id": "B04",
            "beat_ids": ["B04"],
            "expected_outputs": [
                "assets/video/seg_B04.mp4",
                "artifacts/review_overview.json",
            ],
        },
        projects_dir=root,
    )
    assert written["job_id"] == "media-job-1"


def test_poll_not_found_background_job_pauses_as_orphan(tmp_path: Path) -> None:
    class MissingJob(Exception):
        code = "not_found"

    root = tmp_path / "projects"
    _write_project(root)
    board_produce.write_job(
        "shop-demo",
        {"status": board_produce.STATUS_RUNNING, "job_id": "gone-job"},
        projects_dir=root,
    )

    result = board_produce.poll(
        "shop-demo",
        projects_dir=root,
        job_status=lambda _job_id: (_ for _ in ()).throw(MissingJob("missing")),
    )

    assert result["action"] == "produce_paused"
    assert result["job"]["code"] == "orphaned"


def test_generate_retries_until_fifth_success() -> None:
    calls = {"n": 0}

    def generate(*_a, **_k):
        calls["n"] += 1
        if calls["n"] < 5:
            return {"success": False, "error": "503"}
        return {"success": True}

    result = board_produce.call_video_generate_with_retries(generate, "agnes", "prompt")
    assert calls["n"] == 5
    assert result["success"] is True


def test_generate_stops_after_five_failures() -> None:
    calls = {"n": 0}

    def generate(*_a, **_k):
        calls["n"] += 1
        return {"success": False, "error": "429"}

    with pytest.raises(board_produce.ProduceJobError) as caught:
        board_produce.call_video_generate_with_retries(generate, "agnes", "prompt")
    assert calls["n"] == 5
    assert caught.value.extra["retry_exhausted"] is True
    assert caught.value.extra["generate_attempts"] == 5

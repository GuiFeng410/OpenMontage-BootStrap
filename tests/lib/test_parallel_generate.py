"""Unit tests for lib.parallel_generate (no cloud / no ffmpeg required)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.parallel_generate import (  # noqa: E402
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_SKIPPED,
    assemble_ffmpeg,
    build_scene_plan,
    build_srt_from_scenes,
    estimate_wall_seconds,
    generate_one_scene_with_retries,
    init_generation_manifest,
    is_rate_limit_error,
    mark_existing_clips,
    normalize_agnes_account_tier,
    ordered_clip_paths,
    pending_scene_ids,
    plan_segments,
    planning_report,
    progress_report,
    resolve_agnes_concurrency,
    retry_wait_seconds,
    run_parallel_generate,
    save_manifest,
    update_manifest_scene,
    write_concat_list,
)


def test_plan_segments_30s_default_10():
    segs = plan_segments(30)
    assert len(segs) == 3
    assert segs[0].scene_id == "scene01"
    assert abs(sum(s.duration for s in segs) - 30) < 0.01
    assert all(s.duration <= 10.001 for s in segs)


def test_plan_segments_60s():
    segs = plan_segments(60)
    assert len(segs) == 6
    assert abs(sum(s.duration for s in segs) - 60) < 0.01


def test_plan_segments_rejects_non_positive():
    try:
        plan_segments(0)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_estimate_wall_batches():
    est = estimate_wall_seconds(6, max_concurrency=3, cloud_seconds_per_clip=300, assemble_seconds=60)
    assert est["batches"] == 2
    assert est["generate_seconds"] == 600
    assert est["total_seconds"] == 660
    assert est["optimistic_seconds"] == 660
    assert est["conservative_seconds"] > est["optimistic_seconds"]


def test_build_scene_plan_and_manifest(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("AGNES_ACCOUNT_TIER", raising=False)
    monkeypatch.delenv("AGNES_VIDEO_MAX_CONCURRENCY", raising=False)
    scenes = [
        {"id": "scene01", "duration": 10, "prompt": "a", "caption": "一"},
        {"id": "scene02", "duration": 10, "prompt": "b", "caption": "二"},
    ]
    plan = build_scene_plan(scenes, provider="agnes")
    assert plan["parallel"]["max_concurrency"] == 1
    assert plan["scenes"][0]["asset"] == "assets/video/scene01_agnes.mp4"

    manifest = init_generation_manifest("demo", plan["scenes"], max_concurrency=2)
    assert manifest["summary"]["pending"] == 2
    assert manifest["summary"]["total"] == 2

    project = tmp_path / "demo"
    (project / "artifacts").mkdir(parents=True)
    save_manifest(project, manifest)
    assert (project / "artifacts" / "generation_manifest.json").exists()


def test_mark_existing_and_pending(tmp_path: Path):
    project = tmp_path / "proj"
    video = project / "assets" / "video"
    video.mkdir(parents=True)
    clip = video / "scene01_agnes.mp4"
    clip.write_bytes(b"x" * 150_000)

    plan = build_scene_plan(
        [
            {"id": "scene01", "duration": 10, "prompt": "a"},
            {"id": "scene02", "duration": 10, "prompt": "b"},
        ]
    )
    manifest = init_generation_manifest("proj", plan["scenes"])
    mark_existing_clips(project, manifest, plan)
    assert manifest["scenes"][0]["status"] == STATUS_SKIPPED
    assert pending_scene_ids(manifest) == ["scene02"]


def test_update_manifest_scene_summary():
    plan = build_scene_plan([{"id": "scene01", "duration": 5, "prompt": "a"}])
    manifest = init_generation_manifest("p", plan["scenes"])
    update_manifest_scene(manifest, "scene01", status=STATUS_COMPLETED, attempts=1, wall_seconds=12.5)
    assert manifest["summary"]["completed"] == 1
    assert manifest["summary"]["pending"] == 0


def test_retry_then_success(tmp_path: Path):
    calls = {"n": 0}
    out = tmp_path / "scene01.mp4"

    def gen(scene, path: Path):
        calls["n"] += 1
        if calls["n"] < 3:
            return {"success": False, "error": "503 Service Unavailable"}
        path.write_bytes(b"ok" * 1000)
        return {"success": True, "duration_actual": 10.0, "wall_seconds": 1.0}

    sleeps: list[float] = []
    result = generate_one_scene_with_retries(
        {"id": "scene01", "duration": 10, "prompt": "x", "asset": "a.mp4"},
        out,
        gen,
        retry_max=4,
        retry_base_seconds=1,
        sleep_fn=sleeps.append,
    )
    assert result.status == STATUS_COMPLETED
    assert result.attempts == 3
    # 503 uses rate-limit floor (≥20s) even when retry_base_seconds=1
    assert sleeps == [20.0, 20.0]


def test_non_retryable_fails_immediately(tmp_path: Path):
    def gen(scene, out: Path):
        return {"success": False, "error": "401 invalid token"}

    result = generate_one_scene_with_retries(
        {"id": "scene01", "duration": 10, "prompt": "x"},
        tmp_path / "x.mp4",
        gen,
        retry_max=4,
        sleep_fn=lambda _s: None,
    )
    assert result.status == STATUS_FAILED
    assert result.attempts == 1


def test_run_parallel_generate_concurrency(tmp_path: Path):
    project = tmp_path / "par"
    plan = build_scene_plan(
        [
            {"id": "scene01", "duration": 5, "prompt": "a", "caption": "A"},
            {"id": "scene02", "duration": 5, "prompt": "b", "caption": "B"},
            {"id": "scene03", "duration": 5, "prompt": "c", "caption": "C"},
        ],
        parallel={
            "max_concurrency": 2,
            "retry_max": 1,
            "retry_base_seconds": 0,
            "skip_if_exists_min_bytes": 10,
        },
    )
    (project / "artifacts").mkdir(parents=True)
    (project / "assets" / "video").mkdir(parents=True)
    (project / "artifacts" / "scene_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    def gen(scene, out: Path):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"clip-" + scene["id"].encode() + b"-" * 50)
        return {"success": True, "duration_actual": 5.0, "wall_seconds": 0.01}

    done: list[str] = []
    manifest = run_parallel_generate(
        project,
        plan,
        gen,
        on_scene_done=lambda r, _m: done.append(r.scene_id),
    )
    assert set(done) == {"scene01", "scene02", "scene03"}
    assert manifest["summary"]["completed"] == 3
    assert pending_scene_ids(manifest) == []
    for s in plan["scenes"]:
        assert (project / s["asset"]).is_file()


def test_run_parallel_skips_existing(tmp_path: Path):
    project = tmp_path / "skip"
    plan = build_scene_plan(
        [{"id": "scene01", "duration": 5, "prompt": "a"}],
        parallel={"max_concurrency": 1, "skip_if_exists_min_bytes": 10, "retry_max": 1},
    )
    out = project / plan["scenes"][0]["asset"]
    out.parent.mkdir(parents=True)
    out.write_bytes(b"existing" * 20)
    (project / "artifacts").mkdir(parents=True)

    calls = {"n": 0}

    def gen(scene, path: Path):
        calls["n"] += 1
        return {"success": True}

    manifest = run_parallel_generate(project, plan, gen)
    assert calls["n"] == 0
    assert manifest["scenes"][0]["status"] == STATUS_SKIPPED


def test_srt_and_concat_order(tmp_path: Path):
    scenes = [
        {"id": "scene01", "duration": 10, "caption": "雨夜巷口"},
        {"id": "scene02", "duration": 10, "caption": "湿街向前"},
        {"id": "scene03", "duration": 10, "caption": "灯海横移"},
    ]
    srt = build_srt_from_scenes(scenes)
    assert "00:00:00,000 --> 00:00:10,000" in srt
    assert "00:00:10,000 --> 00:00:20,000" in srt
    assert "00:00:20,000 --> 00:00:30,000" in srt
    assert "雨夜巷口" in srt

    project = tmp_path / "ord"
    video = project / "assets" / "video"
    video.mkdir(parents=True)
    paths = []
    for i, _s in enumerate(scenes, 1):
        p = video / f"scene{i:02d}_agnes.mp4"
        p.write_bytes(b"m" * 100)
        paths.append(p)
    list_file = video / "concat_list.txt"
    write_concat_list(list_file, paths)
    text = list_file.read_text(encoding="utf-8")
    assert text.index("scene01") < text.index("scene02") < text.index("scene03")


def test_ordered_clip_paths_and_assemble_mock(tmp_path: Path):
    project = tmp_path / "asm"
    plan = build_scene_plan(
        [
            {"id": "scene01", "duration": 10, "prompt": "a", "caption": "一"},
            {"id": "scene02", "duration": 10, "prompt": "b", "caption": "二"},
        ]
    )
    for s in plan["scenes"]:
        p = project / s["asset"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"v" * 200)

    ordered = ordered_clip_paths(project, plan)
    assert [p.name for p in ordered] == ["scene01_agnes.mp4", "scene02_agnes.mp4"]

    calls: list[list[str]] = []

    def fake_run(cmd, check=True, cwd=None):  # noqa: ANN001
        calls.append(list(cmd))

        class R:
            returncode = 0

        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"out")
        return R()

    final = assemble_ffmpeg(project, plan, burn_subtitles=True, run=fake_run)
    assert final.name == "final.mp4"
    assert final.is_file()
    assert len(calls) == 2
    assert (project / "assets" / "subs" / "captions.srt").is_file()
    assert (project / "assets" / "subs" / "_work" / "captions.srt").is_file()


def test_pending_includes_orphaned_running():
    plan = build_scene_plan(
        [
            {"id": "scene01", "duration": 5, "prompt": "a"},
            {"id": "scene02", "duration": 5, "prompt": "b"},
        ]
    )
    manifest = init_generation_manifest("p", plan["scenes"])
    update_manifest_scene(manifest, "scene01", status=STATUS_COMPLETED)
    update_manifest_scene(manifest, "scene02", status="running", error="stale")
    assert pending_scene_ids(manifest) == ["scene02"]


def test_progress_report_contains_counts():
    plan = build_scene_plan([{"id": "scene01", "duration": 5, "prompt": "a"}])
    manifest = init_generation_manifest("p", plan["scenes"])
    update_manifest_scene(manifest, "scene01", status=STATUS_COMPLETED)
    text = progress_report(manifest)
    assert "1/1" in text
    assert "scene01" in text


def test_resolve_agnes_concurrency_tiers(monkeypatch):
    monkeypatch.delenv("AGNES_VIDEO_MAX_CONCURRENCY", raising=False)
    monkeypatch.setenv("AGNES_ACCOUNT_TIER", "default")
    assert resolve_agnes_concurrency()["concurrency"] == 1
    monkeypatch.setenv("AGNES_ACCOUNT_TIER", "enterprise")
    assert resolve_agnes_concurrency()["concurrency"] == 2
    monkeypatch.setenv("AGNES_ACCOUNT_TIER", "tokenplan")
    assert resolve_agnes_concurrency()["concurrency"] == 3


def test_resolve_agnes_concurrency_caps_without_force(monkeypatch):
    monkeypatch.delenv("AGNES_VIDEO_MAX_CONCURRENCY", raising=False)
    resolved = resolve_agnes_concurrency(3, force=False, tier="default")
    assert resolved["concurrency"] == 1
    assert resolved["capped"] is True
    forced = resolve_agnes_concurrency(3, force=True, tier="default")
    assert forced["concurrency"] == 3
    assert forced["capped"] is False


def test_normalize_agnes_account_tier_aliases():
    assert normalize_agnes_account_tier("TokenPlan") == "tokenplan"
    assert normalize_agnes_account_tier("FREE") == "default"
    assert normalize_agnes_account_tier("enterprise") == "enterprise"


def test_retry_wait_longer_for_429():
    assert retry_wait_seconds("429 Too Many Requests", 1, 20) >= 30
    assert retry_wait_seconds("generic error", 1, 20) == 20
    assert is_rate_limit_error("503 Service Unavailable")


def test_planning_report_has_dual_estimates():
    segs = plan_segments(30)
    text = planning_report(
        project_id="demo",
        target_seconds=30,
        segments=segs,
        max_concurrency=1,
        provider="agnes",
        model="agnes-video-v2.0",
        subtitles=True,
        account_tier="default",
    )
    assert "乐观" in text
    assert "保守" in text
    assert "default" in text


def test_run_parallel_reduces_concurrency_on_429(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("AGNES_ACCOUNT_TIER", raising=False)
    monkeypatch.delenv("AGNES_VIDEO_MAX_CONCURRENCY", raising=False)
    project = tmp_path / "rl"
    plan = build_scene_plan(
        [
            {"id": "scene01", "duration": 5, "prompt": "a"},
            {"id": "scene02", "duration": 5, "prompt": "b"},
            {"id": "scene03", "duration": 5, "prompt": "c"},
        ],
        parallel={
            "max_concurrency": 3,
            "account_tier": "tokenplan",
            "retry_max": 1,
            "retry_base_seconds": 0,
            "skip_if_exists_min_bytes": 10,
        },
    )
    (project / "artifacts").mkdir(parents=True)
    (project / "assets" / "video").mkdir(parents=True)

    calls: list[str] = []
    reductions: list[int] = []

    def gen(scene, out: Path):
        calls.append(scene["id"])
        if scene["id"] == "scene01":
            return {"success": False, "error": "429 Too Many Requests", "wall_seconds": 0.01}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"ok" * 40)
        return {"success": True, "duration_actual": 5.0, "wall_seconds": 0.01}

    manifest = run_parallel_generate(
        project,
        plan,
        gen,
        max_concurrency=3,
        force_concurrency=True,
        on_concurrency_reduced=lambda c, _r: reductions.append(c),
    )
    assert reductions == [1]
    assert manifest.get("max_concurrency") == 1
    # scene01 failed; others may complete depending on timing — at least reduction happened
    assert any(s["id"] == "scene01" and s["status"] == STATUS_FAILED for s in manifest["scenes"])

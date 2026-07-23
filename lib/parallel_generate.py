"""Parallel long-video clip generation helpers.

Python = persistence + concurrency + FFmpeg assemble.
Creative decisions (prompts, theme, whether to generate) stay with the agent.

See: docs/Phase/A_01-长视频生成-steps/01-编排规范.md
     docs/Plan/A_01-长视频生成/01-总流程-v1.0.md
     skills/meta/parallel-video-orchestration.md
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from lib.paths import PROJECTS_DIR, REPO_ROOT

DEFAULT_SEGMENT_SECONDS = 10.0
DEFAULT_MAX_SEGMENT_SECONDS = 10.0
DEFAULT_MIN_SEGMENT_SECONDS = 5.0
# Safe Agnes default (official default-tier video RPM ≈ 1). Prefer resolve_agnes_concurrency().
DEFAULT_MAX_CONCURRENCY = 1
DEFAULT_RETRY_MAX = 4
DEFAULT_RETRY_BASE_SECONDS = 20
DEFAULT_SKIP_IF_EXISTS_MIN_BYTES = 100_000
DEFAULT_CLOUD_SECONDS_PER_CLIP = 300.0  # ~5 min Agnes 10s wall estimate
DEFAULT_AGNES_POLL_INTERVAL_SECONDS = 8
DEFAULT_AGNES_ACCOUNT_TIER = "default"

# Official video RPM caps (Token Plan FAQ): default=1, enterprise=2, TokenPlan=5.
# Code defaults leave headroom for create+poll; TokenPlan default concurrency=3 per product decision.
AGNES_TIER_DEFAULT_CONCURRENCY = {
    "default": 1,
    "enterprise": 2,
    "tokenplan": 3,
}
AGNES_TIER_MAX_CONCURRENCY = {
    "default": 1,
    "enterprise": 2,
    "tokenplan": 3,
}

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

RETRYABLE_MARKERS = ("503", "502", "429", "timeout", "Unavailable", "timed out")
RATE_LIMIT_MARKERS = ("503", "502", "429", "Unavailable")


def normalize_agnes_account_tier(raw: str | None = None) -> str:
    """Normalize AGNES_ACCOUNT_TIER to default|enterprise|tokenplan."""
    value = (raw if raw is not None else os.environ.get("AGNES_ACCOUNT_TIER", DEFAULT_AGNES_ACCOUNT_TIER)) or ""
    key = value.strip().lower().replace("-", "").replace("_", "")
    aliases = {
        "default": "default",
        "free": "default",
        "enterprise": "enterprise",
        "tokenplan": "tokenplan",
        "token": "tokenplan",
        "plan": "tokenplan",
    }
    return aliases.get(key, DEFAULT_AGNES_ACCOUNT_TIER)


def resolve_agnes_concurrency(
    requested: int | None = None,
    *,
    force: bool = False,
    tier: str | None = None,
) -> dict[str, Any]:
    """Resolve concurrency from tier + optional request/env override.

    Returns dict: tier, default, cap, concurrency, capped, force.
    """
    resolved_tier = normalize_agnes_account_tier(tier)
    tier_default = int(AGNES_TIER_DEFAULT_CONCURRENCY[resolved_tier])
    tier_cap = int(AGNES_TIER_MAX_CONCURRENCY[resolved_tier])

    env_raw = os.environ.get("AGNES_VIDEO_MAX_CONCURRENCY")
    env_value: int | None = None
    if env_raw is not None and str(env_raw).strip() != "":
        env_value = max(1, int(env_raw))

    if requested is not None:
        desired = max(1, int(requested))
    elif env_value is not None:
        desired = env_value
    else:
        desired = tier_default

    capped = False
    if not force and desired > tier_cap:
        desired = tier_cap
        capped = True

    return {
        "tier": resolved_tier,
        "default": tier_default,
        "cap": tier_cap,
        "concurrency": desired,
        "capped": capped,
        "force": bool(force),
    }


def default_parallel_config(
    *,
    max_concurrency: int | None = None,
    force: bool = False,
    tier: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_agnes_concurrency(max_concurrency, force=force, tier=tier)
    return {
        "max_concurrency": resolved["concurrency"],
        "account_tier": resolved["tier"],
        "retry_max": DEFAULT_RETRY_MAX,
        "retry_base_seconds": DEFAULT_RETRY_BASE_SECONDS,
        "skip_if_exists_min_bytes": DEFAULT_SKIP_IF_EXISTS_MIN_BYTES,
        "poll_interval_seconds": DEFAULT_AGNES_POLL_INTERVAL_SECONDS,
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def project_dir(project_id: str, projects_root: Path | None = None) -> Path:
    root = projects_root or PROJECTS_DIR
    return Path(root) / project_id


def artifacts_dir(project: Path) -> Path:
    return project / "artifacts"


def video_dir(project: Path) -> Path:
    return project / "assets" / "video"


def subs_dir(project: Path) -> Path:
    return project / "assets" / "subs"


def renders_dir(project: Path) -> Path:
    return project / "renders"


def scene_plan_path(project: Path) -> Path:
    return artifacts_dir(project) / "scene_plan.json"


def generation_manifest_path(project: Path) -> Path:
    return artifacts_dir(project) / "generation_manifest.json"


def brief_path(project: Path) -> Path:
    return artifacts_dir(project) / "brief.json"


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


@dataclass
class SegmentSpec:
    index: int  # 1-based
    duration: float

    @property
    def scene_id(self) -> str:
        return f"scene{self.index:02d}"


def plan_segments(
    target_seconds: float,
    *,
    segment_seconds: float = DEFAULT_SEGMENT_SECONDS,
    max_segment_seconds: float = DEFAULT_MAX_SEGMENT_SECONDS,
    min_segment_seconds: float = DEFAULT_MIN_SEGMENT_SECONDS,
) -> list[SegmentSpec]:
    """Split target duration into equal-ish segments within [min, max]."""
    if target_seconds <= 0:
        raise ValueError("target_seconds must be > 0")
    seg = float(segment_seconds)
    if seg <= 0:
        raise ValueError("segment_seconds must be > 0")
    seg = min(seg, float(max_segment_seconds))
    seg = max(seg, float(min_segment_seconds)) if target_seconds >= min_segment_seconds else seg

    count = max(1, int(math.ceil(target_seconds / seg)))
    base = target_seconds / count
    # Keep each segment within bounds when possible
    if base > max_segment_seconds:
        count = max(1, int(math.ceil(target_seconds / max_segment_seconds)))
        base = target_seconds / count
    if base < min_segment_seconds and count > 1 and target_seconds >= min_segment_seconds:
        # Prefer fewer longer clips when target is small relative to count
        count = max(1, int(math.floor(target_seconds / min_segment_seconds)))
        base = target_seconds / count

    durations: list[float] = []
    remaining = float(target_seconds)
    for i in range(count):
        if i == count - 1:
            d = round(remaining, 3)
        else:
            d = round(base, 3)
            remaining = round(remaining - d, 3)
        # Clamp last leftovers under min into previous if tiny
        durations.append(d)

    if len(durations) >= 2 and durations[-1] < min_segment_seconds / 2:
        durations[-2] = round(durations[-2] + durations[-1], 3)
        durations.pop()

    return [SegmentSpec(index=i + 1, duration=d) for i, d in enumerate(durations)]


def estimate_wall_seconds(
    segment_count: int,
    *,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    cloud_seconds_per_clip: float = DEFAULT_CLOUD_SECONDS_PER_CLIP,
    assemble_seconds: float = 90.0,
) -> dict[str, float]:
    """Rough wall-clock estimate for parallel cloud generation + assemble.

    Returns optimistic (one-shot success) and conservative (retries/rate-limit) totals.
    """
    conc = max(1, int(max_concurrency))
    n = max(0, int(segment_count))
    batches = math.ceil(n / conc) if n else 0
    gen = batches * float(cloud_seconds_per_clip)
    assemble = float(assemble_seconds)
    optimistic = gen + assemble
    # Conservative: slower effective cloud time + per-clip retry/backoff overhead
    conservative = batches * float(cloud_seconds_per_clip) * 1.6 + assemble + n * 60.0
    return {
        "generate_seconds": gen,
        "assemble_seconds": assemble,
        "total_seconds": optimistic,  # backward-compatible alias = optimistic
        "optimistic_seconds": optimistic,
        "conservative_seconds": conservative,
        "batches": float(batches),
    }


def asset_relpath(scene_id: str, provider: str = "agnes") -> str:
    return f"assets/video/{scene_id}_{provider}.mp4"


def build_scene_plan(
    scenes: list[dict[str, Any]],
    *,
    provider: str = "agnes",
    model: str = "agnes-video-v2.0",
    parallel: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize scenes into a scene_plan dict with parallel metadata."""
    normalized: list[dict[str, Any]] = []
    for i, raw in enumerate(scenes, 1):
        scene_id = str(raw.get("id") or f"scene{i:02d}")
        prov = str(raw.get("provider") or provider)
        entry = {
            "id": scene_id,
            "duration": float(raw["duration"]),
            "prompt": str(raw.get("prompt") or ""),
            "caption": raw.get("caption"),
            "asset": str(raw.get("asset") or asset_relpath(scene_id, prov)),
            "provider": prov,
            "model": str(raw.get("model") or model),
        }
        # Drop None caption to keep plan clean
        if entry["caption"] is None:
            entry.pop("caption")
        normalized.append(entry)

    plan: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "compose": "ffmpeg_concat",
        "parallel": parallel or default_parallel_config(),
        "scenes": normalized,
    }
    if extra:
        for k, v in extra.items():
            if k not in plan:
                plan[k] = v
    return plan


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def init_generation_manifest(
    project_id: str,
    scenes: Iterable[dict[str, Any]],
    *,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    provider: str = "agnes",
) -> dict[str, Any]:
    now = utc_now_iso()
    entries = []
    for s in scenes:
        entries.append(
            {
                "id": s["id"],
                "status": STATUS_PENDING,
                "asset": s.get("asset") or asset_relpath(s["id"], provider),
                "attempts": 0,
                "wall_seconds": None,
                "duration_actual": None,
                "error": None,
                "updated_at": now,
            }
        )
    return {
        "project_id": project_id,
        "provider": provider,
        "max_concurrency": int(max_concurrency),
        "started_at": now,
        "updated_at": now,
        "scenes": entries,
        "summary": summarize_manifest_scenes(entries),
    }


def summarize_manifest_scenes(scenes: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "total": len(scenes),
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "skipped": 0,
    }
    for s in scenes:
        st = s.get("status", STATUS_PENDING)
        if st in counts:
            counts[st] += 1
    return counts


def refresh_manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest["summary"] = summarize_manifest_scenes(manifest.get("scenes") or [])
    manifest["updated_at"] = utc_now_iso()
    return manifest


def update_manifest_scene(
    manifest: dict[str, Any],
    scene_id: str,
    *,
    status: str,
    attempts: int | None = None,
    wall_seconds: float | None = None,
    duration_actual: float | None = None,
    error: str | None = None,
    asset: str | None = None,
    clear_error: bool = False,
) -> dict[str, Any]:
    found = False
    for entry in manifest.get("scenes") or []:
        if entry.get("id") == scene_id:
            found = True
            entry["status"] = status
            entry["updated_at"] = utc_now_iso()
            if attempts is not None:
                entry["attempts"] = attempts
            if wall_seconds is not None:
                entry["wall_seconds"] = wall_seconds
            if duration_actual is not None:
                entry["duration_actual"] = duration_actual
            if clear_error or error is not None or status in (STATUS_COMPLETED, STATUS_SKIPPED, STATUS_RUNNING):
                # Explicit None clears stale errors when entering running/success
                entry["error"] = error
            if asset is not None:
                entry["asset"] = asset
            break
    if not found:
        raise KeyError(f"scene_id not in manifest: {scene_id}")
    return refresh_manifest_summary(manifest)


def load_or_init_manifest(project: Path, scene_plan: dict[str, Any]) -> dict[str, Any]:
    path = generation_manifest_path(project)
    if path.exists():
        return read_json(path)
    parallel = scene_plan.get("parallel") or {}
    manifest = init_generation_manifest(
        project.name,
        scene_plan.get("scenes") or [],
        max_concurrency=int(parallel.get("max_concurrency", DEFAULT_MAX_CONCURRENCY)),
        provider=str(scene_plan.get("provider") or "agnes"),
    )
    write_json(path, manifest)
    return manifest


def save_manifest(project: Path, manifest: dict[str, Any]) -> Path:
    refresh_manifest_summary(manifest)
    return write_json(generation_manifest_path(project), manifest)


# ---------------------------------------------------------------------------
# Clip existence / resolve paths
# ---------------------------------------------------------------------------


def resolve_asset_path(project: Path, asset_rel: str) -> Path:
    return (project / asset_rel).resolve()


def clip_is_valid(path: Path, *, min_bytes: int = DEFAULT_SKIP_IF_EXISTS_MIN_BYTES) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= int(min_bytes)
    except OSError:
        return False


def mark_existing_clips(
    project: Path,
    manifest: dict[str, Any],
    scene_plan: dict[str, Any],
) -> dict[str, Any]:
    """Mark completed/skipped for clips already on disk."""
    parallel = scene_plan.get("parallel") or {}
    min_bytes = int(parallel.get("skip_if_exists_min_bytes", DEFAULT_SKIP_IF_EXISTS_MIN_BYTES))
    asset_by_id = {s["id"]: s.get("asset") for s in scene_plan.get("scenes") or []}
    for entry in manifest.get("scenes") or []:
        if entry.get("status") in (STATUS_COMPLETED, STATUS_SKIPPED):
            continue
        rel = entry.get("asset") or asset_by_id.get(entry["id"])
        if not rel:
            continue
        path = resolve_asset_path(project, rel)
        if clip_is_valid(path, min_bytes=min_bytes):
            entry["status"] = STATUS_SKIPPED
            entry["asset"] = rel
            entry["error"] = None
            entry["updated_at"] = utc_now_iso()
    return refresh_manifest_summary(manifest)


def pending_scene_ids(manifest: dict[str, Any]) -> list[str]:
    """Scenes that still need generation.

    Includes orphaned ``running`` entries left by interrupted jobs.
    """
    return [
        s["id"]
        for s in manifest.get("scenes") or []
        if s.get("status") in (STATUS_PENDING, STATUS_FAILED, STATUS_RUNNING)
    ]


def ordered_clip_paths(project: Path, scene_plan: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for scene in scene_plan.get("scenes") or []:
        rel = scene["asset"]
        path = resolve_asset_path(project, rel)
        if not path.is_file():
            raise FileNotFoundError(f"missing clip for {scene['id']}: {path}")
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# Parallel generate (callable injected — agent/tools supply the real generator)
# ---------------------------------------------------------------------------

GenerateFn = Callable[[dict[str, Any], Path], dict[str, Any]]
# Expected return: {"success": bool, "duration_actual": float|None, "error": str|None, "wall_seconds": float}


@dataclass
class SceneGenerateResult:
    scene_id: str
    status: str
    attempts: int = 0
    wall_seconds: float | None = None
    duration_actual: float | None = None
    error: str | None = None
    asset: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_retryable_error(message: str) -> bool:
    return any(m in message for m in RETRYABLE_MARKERS)


def is_rate_limit_error(message: str | None) -> bool:
    if not message:
        return False
    return any(m in message for m in RATE_LIMIT_MARKERS)


def retry_wait_seconds(message: str, attempt: int, retry_base_seconds: int) -> float:
    """Longer backoff for 429/503 to avoid amplifying rate limits."""
    base = float(retry_base_seconds) * attempt
    if "429" in message:
        return max(30.0, base * 1.5)
    if is_rate_limit_error(message):
        return max(20.0, base)
    return base


def generate_one_scene_with_retries(
    scene: dict[str, Any],
    output_path: Path,
    generate_fn: GenerateFn,
    *,
    retry_max: int = DEFAULT_RETRY_MAX,
    retry_base_seconds: int = DEFAULT_RETRY_BASE_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> SceneGenerateResult:
    """Run generate_fn with retry/backoff. Does not touch the network itself."""
    scene_id = scene["id"]
    last_error = "unknown"
    for attempt in range(1, int(retry_max) + 1):
        t0 = time.perf_counter()
        try:
            result = generate_fn(scene, output_path)
        except Exception as exc:  # noqa: BLE001 — worker boundary
            last_error = str(exc)
            result = {"success": False, "error": last_error, "duration_actual": None, "wall_seconds": None}

        wall = float(result.get("wall_seconds") or (time.perf_counter() - t0))
        if result.get("success"):
            return SceneGenerateResult(
                scene_id=scene_id,
                status=STATUS_COMPLETED,
                attempts=attempt,
                wall_seconds=wall,
                duration_actual=result.get("duration_actual"),
                error=None,
                asset=scene.get("asset"),
            )

        last_error = str(result.get("error") or "unknown")
        if not is_retryable_error(last_error) or attempt >= retry_max:
            return SceneGenerateResult(
                scene_id=scene_id,
                status=STATUS_FAILED,
                attempts=attempt,
                wall_seconds=wall,
                duration_actual=None,
                error=last_error,
                asset=scene.get("asset"),
            )
        sleep_fn(retry_wait_seconds(last_error, attempt, retry_base_seconds))

    return SceneGenerateResult(
        scene_id=scene_id,
        status=STATUS_FAILED,
        attempts=retry_max,
        error=last_error,
        asset=scene.get("asset"),
    )


def run_parallel_generate(
    project: Path,
    scene_plan: dict[str, Any],
    generate_fn: GenerateFn,
    *,
    max_concurrency: int | None = None,
    force_concurrency: bool = False,
    on_scene_done: Callable[[SceneGenerateResult, dict[str, Any]], None] | None = None,
    on_concurrency_reduced: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    """Generate pending scenes with a sliding-window pool; update generation_manifest.json.

    On 429/503 failures, concurrency drops to 1 for remaining not-yet-started scenes.
    generate_fn(scene, output_path) -> dict with success/error/duration_actual/wall_seconds.
    """
    artifacts_dir(project).mkdir(parents=True, exist_ok=True)
    video_dir(project).mkdir(parents=True, exist_ok=True)

    parallel = scene_plan.get("parallel") or {}
    tier = parallel.get("account_tier") or scene_plan.get("account_tier")
    requested = max_concurrency if max_concurrency is not None else parallel.get("max_concurrency")
    resolved = resolve_agnes_concurrency(
        int(requested) if requested is not None else None,
        force=force_concurrency,
        tier=str(tier) if tier else None,
    )
    conc = int(resolved["concurrency"])
    retry_max = int(parallel.get("retry_max", DEFAULT_RETRY_MAX))
    retry_base = int(parallel.get("retry_base_seconds", DEFAULT_RETRY_BASE_SECONDS))
    min_bytes = int(parallel.get("skip_if_exists_min_bytes", DEFAULT_SKIP_IF_EXISTS_MIN_BYTES))

    manifest = load_or_init_manifest(project, scene_plan)
    manifest["max_concurrency"] = conc
    manifest["account_tier"] = resolved["tier"]
    mark_existing_clips(project, manifest, scene_plan)
    save_manifest(project, manifest)

    scenes_by_id = {s["id"]: s for s in scene_plan.get("scenes") or []}
    todo = pending_scene_ids(manifest)
    if not todo:
        return manifest

    def _worker(scene_id: str) -> SceneGenerateResult:
        scene = scenes_by_id[scene_id]
        out = resolve_asset_path(project, scene["asset"])
        if clip_is_valid(out, min_bytes=min_bytes):
            return SceneGenerateResult(
                scene_id=scene_id,
                status=STATUS_SKIPPED,
                attempts=0,
                asset=scene["asset"],
            )
        return generate_one_scene_with_retries(
            scene,
            out,
            generate_fn,
            retry_max=retry_max,
            retry_base_seconds=retry_base,
        )

    # Mark running (clear stale error from prior failed attempts)
    for sid in todo:
        update_manifest_scene(manifest, sid, status=STATUS_RUNNING, error=None)
    save_manifest(project, manifest)

    pending: deque[str] = deque(todo)
    inflight: dict[Future[SceneGenerateResult], str] = {}
    # Pool size = initial concurrency; sliding window enforces active cap (may drop to 1).
    with ThreadPoolExecutor(max_workers=max(1, conc)) as pool:
        while pending or inflight:
            while pending and len(inflight) < conc:
                sid = pending.popleft()
                fut = pool.submit(_worker, sid)
                inflight[fut] = sid
            if not inflight:
                break
            done, _ = wait(tuple(inflight.keys()), return_when=FIRST_COMPLETED)
            for fut in done:
                inflight.pop(fut, None)
                result = fut.result()
                update_manifest_scene(
                    manifest,
                    result.scene_id,
                    status=result.status,
                    attempts=result.attempts,
                    wall_seconds=result.wall_seconds,
                    duration_actual=result.duration_actual,
                    error=result.error,
                    asset=result.asset,
                )
                save_manifest(project, manifest)
                if (
                    result.status == STATUS_FAILED
                    and is_rate_limit_error(result.error)
                    and conc > 1
                ):
                    conc = 1
                    manifest["max_concurrency"] = 1
                    manifest["concurrency_reduced_reason"] = result.error
                    save_manifest(project, manifest)
                    if on_concurrency_reduced:
                        on_concurrency_reduced(1, result.error or "rate_limit")
                if on_scene_done:
                    on_scene_done(result, manifest)

    return manifest


# ---------------------------------------------------------------------------
# Subtitles + FFmpeg assemble
# ---------------------------------------------------------------------------


def _srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt_from_scenes(scenes: list[dict[str, Any]]) -> str:
    """Build SRT text from ordered scenes with caption + duration."""
    lines: list[str] = []
    t = 0.0
    idx = 0
    for scene in scenes:
        caption = scene.get("caption")
        if not caption:
            t += float(scene.get("duration") or 0)
            continue
        idx += 1
        start = t
        end = t + float(scene["duration"])
        lines.extend(
            [
                str(idx),
                f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}",
                str(caption),
                "",
            ]
        )
        t = end
    return "\n".join(lines)


def write_captions_srt(project: Path, scene_plan: dict[str, Any]) -> Path | None:
    """Write captions.srt (+ _work copy). Returns work SRT path, or None if no captions."""
    text = build_srt_from_scenes(scene_plan.get("scenes") or [])
    if not text.strip():
        return None
    sd = subs_dir(project)
    work = sd / "_work"
    sd.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    srt = sd / "captions.srt"
    srt.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    work_srt = work / "captions.srt"
    shutil.copy2(srt, work_srt)
    return work_srt


def write_concat_list(list_file: Path, clip_paths: list[Path]) -> Path:
    entries = []
    for p in clip_paths:
        ap = p.resolve().as_posix().replace("'", r"'\''")
        entries.append(f"file '{ap}'")
    list_file.parent.mkdir(parents=True, exist_ok=True)
    list_file.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return list_file


def assemble_ffmpeg(
    project: Path,
    scene_plan: dict[str, Any],
    *,
    burn_subtitles: bool = True,
    ffmpeg_bin: str = "ffmpeg",
    run: Callable[..., subprocess.CompletedProcess[Any]] | None = None,
) -> Path:
    """Concat clips in scene order; optionally burn SRT. Returns final.mp4 path."""
    runner = run or subprocess.run
    rd = renders_dir(project)
    vd = video_dir(project)
    rd.mkdir(parents=True, exist_ok=True)

    paths = ordered_clip_paths(project, scene_plan)
    list_file = vd / "concat_list.txt"
    write_concat_list(list_file, paths)

    concat_mp4 = rd / "concat_raw.mp4"
    final_mp4 = rd / "final.mp4"

    cmd1 = [
        ffmpeg_bin,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(concat_mp4),
    ]
    runner(cmd1, check=True)

    work_srt = write_captions_srt(project, scene_plan) if burn_subtitles else None
    if work_srt is None:
        shutil.copy2(concat_mp4, final_mp4)
        return final_mp4

    vf = (
        "subtitles=captions.srt:force_style="
        "'Fontsize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,"
        "BorderStyle=3,Outline=2,Shadow=0,MarginV=36'"
    )
    cmd2 = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(concat_mp4.resolve()),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(final_mp4.resolve()),
    ]
    runner(cmd2, check=True, cwd=str(work_srt.parent))
    return final_mp4


def progress_report(manifest: dict[str, Any]) -> str:
    """Human-readable progress block for the agent to show the user."""
    summary = manifest.get("summary") or summarize_manifest_scenes(manifest.get("scenes") or [])
    done = int(summary.get("completed", 0)) + int(summary.get("skipped", 0))
    total = int(summary.get("total", 0))
    lines = [f"**生成进度** {done}/{total}"]
    for s in manifest.get("scenes") or []:
        st = s.get("status")
        # ASCII markers — Windows consoles often cannot encode emoji (GBK)
        icon = {
            STATUS_COMPLETED: "[OK]",
            STATUS_SKIPPED: "[SKIP]",
            STATUS_RUNNING: "[RUN]",
            STATUS_FAILED: "[FAIL]",
            STATUS_PENDING: "[WAIT]",
        }.get(st, "[?]")
        extra = ""
        if s.get("wall_seconds") is not None:
            extra = f" — wall {s['wall_seconds']:.0f}s"
        if s.get("error"):
            extra += f" — {s['error']}"
        lines.append(f"- {icon} {s.get('id')} ({st}){extra}")
    return "\n".join(lines)


def planning_report(
    *,
    project_id: str,
    target_seconds: float,
    segments: list[SegmentSpec],
    max_concurrency: int,
    provider: str,
    model: str,
    subtitles: bool,
    account_tier: str | None = None,
) -> str:
    tier = normalize_agnes_account_tier(account_tier)
    est = estimate_wall_seconds(len(segments), max_concurrency=max_concurrency)
    opt_min = est["optimistic_seconds"] / 60.0
    cons_min = est["conservative_seconds"] / 60.0
    dur_note = ", ".join(f"{s.scene_id}={s.duration}s" for s in segments)
    return "\n".join(
        [
            "**并行编排规划**",
            f"- 项目：`projects/{project_id}/`",
            f"- 目标时长：{target_seconds}s → {len(segments)} 段（{dur_note}）",
            f"- Provider：{provider} / {model}",
            f"- 账号档位：{tier}（Agnes 视频并发上限见 Token Plan RPM）",
            f"- 并发：{max_concurrency}",
            f"- 预估墙钟：",
            f"  - 乐观：约 {opt_min:.0f} 分钟（各段一次成功）",
            f"  - 保守：约 {cons_min:.0f} 分钟（含 503/429 重试与退避）",
            f"- 拼接：FFmpeg 直拼 + {'字幕' if subtitles else '无字幕'}",
            "",
            "确认后开始生成。",
        ]
    )


# Convenience: default Agnes generate_fn factory (not imported unless used)
def make_agnes_generate_fn(
    *,
    frame_rate: int = 24,
    aspect_ratio: str = "16:9",
    poll_interval_seconds: int = DEFAULT_AGNES_POLL_INTERVAL_SECONDS,
    timeout_seconds: int = 900,
) -> GenerateFn:
    """Build a GenerateFn that calls tools.video.agnes_video.AgnesVideo."""

    from tools.video.agnes_video import AgnesVideo

    tool = AgnesVideo()

    def _fn(scene: dict[str, Any], output_path: Path) -> dict[str, Any]:
        t0 = time.perf_counter()
        result = tool.execute(
            {
                "prompt": scene["prompt"],
                "operation": "text_to_video",
                "duration": float(scene["duration"]),
                "frame_rate": frame_rate,
                "aspect_ratio": aspect_ratio,
                "output_path": str(output_path),
                "poll_interval_seconds": poll_interval_seconds,
                "timeout_seconds": timeout_seconds,
            }
        )
        wall = result.duration_seconds if result.duration_seconds is not None else (time.perf_counter() - t0)
        if not result.success:
            return {"success": False, "error": result.error or "unknown", "wall_seconds": wall}
        seconds = None
        if result.data:
            seconds = result.data.get("seconds")
            if seconds is not None:
                try:
                    seconds = float(seconds)
                except (TypeError, ValueError):
                    seconds = None
        return {
            "success": True,
            "duration_actual": seconds,
            "error": None,
            "wall_seconds": wall,
        }

    return _fn


__all__ = [
    "REPO_ROOT",
    "PROJECTS_DIR",
    "SegmentSpec",
    "SceneGenerateResult",
    "plan_segments",
    "estimate_wall_seconds",
    "build_scene_plan",
    "default_parallel_config",
    "normalize_agnes_account_tier",
    "resolve_agnes_concurrency",
    "init_generation_manifest",
    "load_or_init_manifest",
    "save_manifest",
    "update_manifest_scene",
    "mark_existing_clips",
    "pending_scene_ids",
    "run_parallel_generate",
    "generate_one_scene_with_retries",
    "is_rate_limit_error",
    "retry_wait_seconds",
    "assemble_ffmpeg",
    "build_srt_from_scenes",
    "write_captions_srt",
    "write_concat_list",
    "progress_report",
    "planning_report",
    "make_agnes_generate_fn",
    "project_dir",
    "clip_is_valid",
    "ordered_clip_paths",
]

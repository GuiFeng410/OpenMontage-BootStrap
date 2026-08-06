"""P0 assert03 five-image 60s bench: scheme -> sample reel -> full draft.

Follows frozen BootStrap P0:
- experimental API budget default ¥8 (not selling price)
- adaptive single candidate
- sample reel 10-15s before full-length Agnes batch
- CostTracker USD ledger + CNY display gate
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env", override=True)

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.experiment_budget import (  # noqa: E402
    DEFAULT_USD_CNY,
    cny_display_snapshot,
    resolve_experiment_budget,
    would_exceed_budget_cny,
)
from tools.cost_tracker import BudgetMode, CostTracker  # noqa: E402
from tools.video.agnes_video import AgnesVideo  # noqa: E402

PROJECT_ID = "p0-assert03-60s-bench"
PROJECT = REPO / "projects" / PROJECT_ID
SRC_DIR = REPO / "Agent-Temp" / "mats" / "picture" / "assert03"
IMAGES = PROJECT / "assets" / "images"
VIDEO = PROJECT / "assets" / "video"
RENDERS = PROJECT / "renders"
ARTIFACTS = PROJECT / "artifacts"
STILLS = VIDEO / "stills"

# Typical-user 5-role pack (icy-blue identity locked on 05)
FIVE = {
    "05.png": "product_identity_anchor",
    "04.png": "product_angle",
    "03.png": "product_hero",
    "07.png": "lifestyle",
    "01.png": "on_body",  # pinkish wear — not identity geometry source
}

NEG = (
    "warped product, morphing shape, broken silhouette, changing proportions, "
    "melted material, duplicated product, missing section, extra decorations, "
    "text, watermark, logo deformation, face morphing"
)

PROMPT_MICRO = (
    "the same single icy-blue jade donut pendant necklace from the reference image, "
    "preserve the exact circular ring, floral silver metalwork, gold stamen accents, "
    "and chain bail, fixed camera, very slight parallax, extremely slow micro push-in, "
    "soft studio light, sharp product focus, realistic subtle motion only, "
    "no rotation, no change of viewpoint, no object transformation, no text, no watermark"
)

PROMPT_LATERAL = (
    "the same single icy-blue jade donut pendant necklace from the reference image, "
    "preserve the exact circular ring, floral silver metalwork, gold stamen accents, "
    "and chain bail, camera almost fixed with extremely slight horizontal parallax drift, "
    "no push-in, no rotation, soft studio light, sharp product focus, "
    "realistic subtle motion only, no object transformation, no text, no watermark"
)

PROMPT_LUSTRE = (
    "the same single icy-blue jade donut pendant necklace from the reference image, "
    "preserve the exact circular ring, floral silver metalwork, gold stamen accents, "
    "and chain bail, fixed camera, very soft specular light sweep across the stone, "
    "minimal camera movement, sharp product focus, realistic subtle motion only, "
    "no rotation, no change of viewpoint, no object transformation, no text, no watermark"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def ensure_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH")
    return exe


def setup_project() -> dict:
    for d in (IMAGES, VIDEO, STILLS, RENDERS, ARTIFACTS):
        d.mkdir(parents=True, exist_ok=True)

    copied = {}
    for name, role in FIVE.items():
        src = SRC_DIR / name
        if not src.exists():
            raise FileNotFoundError(src)
        dst = IMAGES / name
        shutil.copy2(src, dst)
        copied[name] = {"path": f"assets/images/{name}", "role": role, "bytes": dst.stat().st_size}

    budget = resolve_experiment_budget("standard", 8, usd_cny_rate=DEFAULT_USD_CNY)
    marker = {
        "version": "1.0",
        "created_at": utc_now(),
        "project_id": PROJECT_ID,
        "title": "P0 assert03 五图60s商品实验",
        "pipeline_type": "animated-explainer",
        "production_profile": {
            "production_tier": "heavy",
            "visual_source": "paid_gen",
            "tts_source": "edge_tts",
            **budget.to_dict(),
            "review_mode": "normal",
            "candidate_mode": "adaptive",
            "motion_target_band": "60s_cost_ref",
            "true_video_seconds_target_min": 16,
            "true_video_seconds_target_max": 24,
            "is_hard_gate": False,
            "note_zh": "实验目标，非普遍质量硬门槛",
            "style_label_zh": "电商清晰展示",
            "video_channel": "agnes",
            "video_model": "agnes-video-v2.0",
            "ai_video": "enabled",
            "duration_seconds": 60,
        },
    }
    (PROJECT / "project.json").write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")

    brief = {
        "theme": "冰蓝玉环吊坠项链商品展示",
        "duration_seconds": 60,
        "identity_anchor": "assets/images/05.png",
        "five_images": copied,
        "identity_notes_zh": (
            "以 05.png 为身份基准（冰蓝）；01.png 为佩戴图偏粉，仅作氛围，不作几何锚点。"
        ),
        "hard_gates": ["H1_identity", "H2_structure", "H3_playable_non_monotone"],
        "motion_target": {"band": "60s_cost_ref", "true_video_seconds": [16, 24]},
        "budget": budget.to_dict(),
        "flow": ["scheme", "sample_reel", "full_draft", "problem_clips", "final"],
    }
    (ARTIFACTS / "brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")

    video_plan = {
        "segments": [
            {"id": "beat_01", "t": "0-4", "method": "still_zoom", "ref": "05.png", "ai": False},
            {"id": "beat_02", "t": "4-9", "method": "agnes_i2v", "ref": "05.png", "ai": True, "duration": 5},
            {"id": "beat_03", "t": "9-14", "method": "still_zoom", "ref": "04.png", "ai": False},
            {"id": "beat_04", "t": "14-19", "method": "agnes_i2v", "ref": "04.png", "ai": True, "duration": 5},
            {"id": "beat_05", "t": "19-26", "method": "still_zoom", "ref": "03.png", "ai": False},
            {"id": "beat_06", "t": "26-31", "method": "agnes_i2v", "ref": "03.png", "ai": True, "duration": 5},
            {"id": "beat_07", "t": "31-38", "method": "still_zoom", "ref": "07.png", "ai": False},
            {"id": "beat_08", "t": "38-43", "method": "agnes_i2v", "ref": "05.png", "ai": True, "duration": 5},
            {"id": "beat_09", "t": "43-52", "method": "still_zoom", "ref": "01.png", "ai": False},
            {"id": "beat_10", "t": "52-60", "method": "still_hold", "ref": "05.png", "ai": False},
        ],
        "true_video_seconds_planned": 20,
        "candidate_mode": "adaptive",
    }
    (ARTIFACTS / "video_plan.json").write_text(
        json.dumps(video_plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return marker


def make_still_clip(image: Path, out: Path, seconds: float, mode: str = "zoom") -> Path:
    """Render a still with optional slow push-in or gentle pan.

    Product stills: do NOT use ffmpeg zoompan (float crop => visible jitter).
    Zoom/pan modes render frames in Python with integer crop boxes, then encode.
    """
    ffmpeg = ensure_ffmpeg()
    out.parent.mkdir(parents=True, exist_ok=True)
    if mode == "hold":
        vf = (
            "scale=1280:720:force_original_aspect_ratio=decrease,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xD6E6F5,"
            "setsar=1,fps=30"
        )
        run(
            [
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-i",
                str(image),
                "-vf",
                vf,
                "-t",
                str(seconds),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(out),
            ]
        )
        return out

    # Integer-safe motion via Pillow frames (anti-jitter).
    from PIL import Image

    fps = 30
    frames = max(1, int(round(float(seconds) * fps)))
    src = Image.open(image).convert("RGB")
    canvas_w, canvas_h = 1920, 1080
    fitted = Image.new("RGB", (canvas_w, canvas_h), (214, 230, 245))
    scale = max(canvas_w / src.width, canvas_h / src.height)
    resized = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.Resampling.LANCZOS)
    ox = (resized.width - canvas_w) // 2
    oy = (resized.height - canvas_h) // 2
    fitted.paste(resized.crop((ox, oy, ox + canvas_w, oy + canvas_h)), (0, 0))

    frame_dir = out.parent / f"_frames_{out.stem}"
    if frame_dir.exists():
        shutil.rmtree(frame_dir)
    frame_dir.mkdir(parents=True, exist_ok=True)

    out_w, out_h = 1280, 720
    for i in range(frames):
        t = i / max(1, frames - 1)
        if mode == "pan":
            # Gentle left-to-right crop drift at fixed zoom 1.04
            z = 1.04
            crop_w = int(round(out_w / z))
            crop_h = int(round(out_h / z))
            crop_w -= crop_w % 2
            crop_h -= crop_h % 2
            crop_w = max(2, min(crop_w, canvas_w))
            crop_h = max(2, min(crop_h, canvas_h))
            max_shift = max(0, canvas_w - crop_w)
            left = int(round(max_shift * t))
            top = (canvas_h - crop_h) // 2
        else:
            # zoom: 1.00 -> 1.05
            z = 1.0 + 0.05 * t
            crop_w = int(round(out_w / z))
            crop_h = int(round(out_h / z))
            crop_w -= crop_w % 2
            crop_h -= crop_h % 2
            crop_w = max(2, min(crop_w, canvas_w))
            crop_h = max(2, min(crop_h, canvas_h))
            left = (canvas_w - crop_w) // 2
            top = (canvas_h - crop_h) // 2
        tile = fitted.crop((left, top, left + crop_w, top + crop_h))
        frame = tile.resize((out_w, out_h), Image.Resampling.LANCZOS)
        frame.save(frame_dir / f"f_{i:04d}.png")

    run(
        [
            ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_dir / "f_%04d.png"),
            "-vf",
            "setsar=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(out),
        ]
    )
    shutil.rmtree(frame_dir, ignore_errors=True)
    return out


def normalize_clip(src: Path, out: Path, seconds: float | None = None) -> Path:
    """Force 1280x720 / 30fps / SAR=1 before concat to avoid splice jitter."""
    ffmpeg = ensure_ffmpeg()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-vf",
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xD6E6F5,"
        "setsar=1,fps=30",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
    ]
    if seconds is not None:
        cmd.extend(["-t", str(seconds)])
    cmd.append(str(out))
    run(cmd)
    return out


def tracker() -> CostTracker:
    return CostTracker(
        budget_total_usd=resolve_experiment_budget("standard", 8).budget_total_usd,
        mode=BudgetMode.CAP,
        cost_log_path=ARTIFACTS / "cost_log.json",
        require_approval_for_new_paid_tool=False,
        single_action_approval_usd=5.0,
    )


def gate_or_raise(ct: CostTracker, next_usd: float) -> dict:
    budget = resolve_experiment_budget("standard", 8)
    exceeded, detail = would_exceed_budget_cny(
        spent_usd=ct.budget_spent_usd,
        reserved_usd=ct.budget_reserved_usd,
        next_estimate_usd=next_usd,
        budget_cny=budget.budget_cny,
        usd_cny_rate=budget.usd_cny_rate,
    )
    snap = cny_display_snapshot(
        ct.cost_snapshot(),
        usd_cny_rate=budget.usd_cny_rate,
        budget_cny=budget.budget_cny,
    )
    payload = {"gate": detail, "cny_snapshot": snap, "budget": budget.to_dict()}
    (ARTIFACTS / "budget_gate_latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if exceeded:
        raise RuntimeError(f"experimental API budget gate tripped: {json.dumps(detail, ensure_ascii=False)}")
    return payload


def generate_agnes(
    ct: CostTracker,
    *,
    beat_id: str,
    image: Path,
    out: Path,
    duration: float = 5.0,
    prompt: str | None = None,
) -> dict:
    if out.exists() and out.stat().st_size > 100_000:
        # Recover cost if prior run wrote file but failed before reconcile.
        size_mb = out.stat().st_size / (1024 * 1024)
        return {
            "beat_id": beat_id,
            "status": "skipped_exists",
            "path": str(out),
            "actual_usd": 0.0,
            "note": f"reused existing file ({size_mb:.2f} MiB); cost may be in prior log",
        }

    tool = AgnesVideo()
    inputs = {
        "prompt": prompt or PROMPT_MICRO,
        "negative_prompt": NEG,
        "operation": "image_to_video",
        "duration": duration,
        "frame_rate": 24,
        "aspect_ratio": "16:9",
        "image_path": str(image),
        "output_path": str(out),
        "poll_interval_seconds": 8,
        "timeout_seconds": 900,
    }
    est = float(tool.estimate_cost(inputs))
    gate_or_raise(ct, est)
    entry_id = ct.estimate("agnes_video", beat_id, est)
    ct.approve_tool("agnes_video")
    ct.reserve(entry_id)

    print(f"Agnes I2V {beat_id} duration={duration}s est_usd={est:.4f} -> {out.name}")
    last_error = "unknown"
    for attempt in range(1, 4):
        result = tool.execute(inputs)
        if result.success:
            actual = float(getattr(result, "cost_usd", None) or est)
            ct.reconcile(entry_id, actual, success=True)
            meta = {
                "beat_id": beat_id,
                "status": "completed",
                "path": str(out),
                "attempt": attempt,
                "actual_usd": actual,
                "wall_seconds": result.duration_seconds,
                "estimate_usd": est,
            }
            print(json.dumps(meta, ensure_ascii=False))
            return meta
        last_error = result.error or "unknown"
        retryable = any(x in last_error for x in ("503", "502", "429", "timeout", "Unavailable"))
        if not retryable or attempt >= 3:
            ct.reconcile(entry_id, 0.0, success=False)
            raise RuntimeError(f"{beat_id} failed: {last_error}")
        wait = 20 * attempt
        print(f"  retry {attempt} after {wait}s: {last_error}")
        time.sleep(wait)
    ct.reconcile(entry_id, 0.0, success=False)
    raise RuntimeError(f"{beat_id} failed: {last_error}")


def concat(paths: list[Path], out: Path) -> Path:
    ffmpeg = ensure_ffmpeg()
    list_file = VIDEO / f"_concat_{out.stem}.txt"
    lines = []
    for p in paths:
        # ffmpeg concat demuxer needs escaped single quotes on Windows paths
        ap = p.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{ap}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(out),
        ]
    )
    return out


def probe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float((proc.stdout or "").strip())
    except ValueError:
        return 0.0


def phase_sample(ct: CostTracker) -> Path:
    """10-15s sample: identity still + Agnes + still motion."""
    # v3 stills: no zoompan; even-dimension scale+crop push-in
    still1 = make_still_clip(IMAGES / "05.png", STILLS / "sample_identity_4s_v3.mp4", 4.0, "zoom")
    agnes = generate_agnes(
        ct,
        beat_id="sample_agnes_05",
        image=IMAGES / "05.png",
        out=VIDEO / "sample_agnes_05.mp4",
        duration=5.0,
    )
    agnes_norm = normalize_clip(Path(agnes["path"]), VIDEO / "sample_agnes_05_norm.mp4")
    still2 = make_still_clip(IMAGES / "04.png", STILLS / "sample_angle_4s_v3.mp4", 4.0, "zoom")
    out = RENDERS / "sample_reel_13s_v3.mp4"
    concat([still1, agnes_norm, still2], out)
    sample = {
        "path": str(out),
        "duration_probe": probe_duration(out),
        "contains": ["identity_still_05_v3", "agnes_i2v_05_norm", "angle_still_04_v3"],
        "status": "pending_human_review",
        "approved": False,
        "jitter_fix": {
            "issue": "v1 first 3s strong jitter from float zoompan crop + odd SAR",
            "attempt_v2": "trunc zoompan + setsar=1 — partial",
            "attempt_v3_ffmpeg_scale": "failed filter init",
            "fix_v3": "Pillow integer crop+LANCZOS frames (no zoompan); normalize Agnes 1280x720@30 SAR=1",
            "version": "v3",
        },
        "cost_snapshot": cny_display_snapshot(
            ct.cost_snapshot(),
            usd_cny_rate=DEFAULT_USD_CNY,
            budget_cny=8,
        ),
        "created_at": utc_now(),
        "note_zh": "普通评审试片关：请确认身份/动态/抖动后继续全长",
        "previous_samples": [
            str(RENDERS / "sample_reel_13s.mp4"),
            str(RENDERS / "sample_reel_13s_v2.mp4"),
        ],
    }
    (ARTIFACTS / "sample_reel.json").write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def phase_batch2(ct: CostTracker) -> Path:
    """Batch 02: 00:14-00:31 — beat_04 Agnes + beat_05 pan still + beat_06 Agnes."""
    overview_path = ARTIFACTS / "review_overview.json"
    overview = json.loads(overview_path.read_text(encoding="utf-8")) if overview_path.exists() else {}
    for b in overview.get("batches", []):
        if b.get("id") == "batch_01":
            b["status"] = "approved"
            b["approved_at"] = utc_now()
        if b.get("id") == "batch_02":
            b["status"] = "in_review"

    # beat_04 — lateral feel to reduce monotony vs push-in
    a04 = generate_agnes(
        ct,
        beat_id="beat_04",
        image=IMAGES / "04.png",
        out=VIDEO / "beat04_agnes.mp4",
        duration=5.0,
        prompt=PROMPT_LATERAL,
    )
    a04_norm = normalize_clip(Path(a04["path"]), VIDEO / "beat04_agnes_norm.mp4")

    # beat_05 — gentle pan instead of another push-in
    still05 = make_still_clip(IMAGES / "03.png", STILLS / "b05_03_7s_pan.mp4", 7.0, mode="pan")

    # beat_06 — lustre / light sweep
    a06 = generate_agnes(
        ct,
        beat_id="beat_06",
        image=IMAGES / "03.png",
        out=VIDEO / "beat06_agnes.mp4",
        duration=5.0,
        prompt=PROMPT_LUSTRE,
    )
    a06_norm = normalize_clip(Path(a06["path"]), VIDEO / "beat06_agnes_norm.mp4")

    out = RENDERS / "batch02_14_31.mp4"
    concat([a04_norm, still05, a06_norm], out)

    report = {
        "batch_id": "batch_02",
        "time_span": "00:14-00:31",
        "path": str(out),
        "duration_probe": probe_duration(out),
        "beats": [
            {
                "beat": "beat_04",
                "time": "00:14-00:19",
                "method": "视频生成（Agnes）",
                "angle_use": "平铺角度微横移感",
                "prompt_style": "lateral",
                "ref": "04.png",
                "path": str(a04_norm),
                "raw_path": a04.get("path"),
                "status": "待过目",
                "actual_usd": a04.get("actual_usd"),
            },
            {
                "beat": "beat_05",
                "time": "00:19-00:26",
                "method": "图片运镜（确定性微横移）",
                "angle_use": "柔焦氛围主图",
                "ref": "03.png",
                "path": str(still05),
                "status": "待过目",
            },
            {
                "beat": "beat_06",
                "time": "00:26-00:31",
                "method": "视频生成（Agnes）",
                "angle_use": "材质/光泽微变",
                "prompt_style": "lustre",
                "ref": "03.png",
                "path": str(a06_norm),
                "raw_path": a06.get("path"),
                "status": "待过目",
                "actual_usd": a06.get("actual_usd"),
            },
        ],
        "cost_snapshot": cny_display_snapshot(
            ct.cost_snapshot(),
            usd_cny_rate=DEFAULT_USD_CNY,
            budget_cny=8,
        ),
        "created_at": utc_now(),
        "note_zh": "第2批待用户确认；确认后才进入第3批",
    }
    (ARTIFACTS / "batch02_review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # refresh overview statuses for beats 04-06
    for row in overview.get("overview", []):
        if row.get("beat") in {"beat_04", "beat_05", "beat_06"}:
            row["status"] = "待过目"
            if row["beat"] == "beat_04":
                row["asset"] = "beat04_agnes_norm.mp4"
            if row["beat"] == "beat_05":
                row["asset"] = "b05_03_7s_pan.mp4"
            if row["beat"] == "beat_06":
                row["asset"] = "beat06_agnes_norm.mp4"
    overview_path.write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
    print("BATCH2_READY", out)
    return out


def phase_batch3(ct: CostTracker) -> Path:
    """Batch 03: 00:31-00:60 — scene still + return-anchor Agnes + on-body + hold."""
    overview_path = ARTIFACTS / "review_overview.json"
    overview = json.loads(overview_path.read_text(encoding="utf-8")) if overview_path.exists() else {}
    for b in overview.get("batches", []):
        if b.get("id") == "batch_02":
            b["status"] = "approved"
            b["approved_at"] = utc_now()
        if b.get("id") == "batch_03":
            b["status"] = "in_review"

    for row in overview.get("overview", []):
        if row.get("beat") in {"beat_04", "beat_05", "beat_06"}:
            row["status"] = "可以"

    # beat_07 — lifestyle/scene, gentle zoom (batch2 used pan)
    still07 = make_still_clip(IMAGES / "07.png", STILLS / "b07_07_7s_zoom.mp4", 7.0, mode="zoom")

    # beat_08 — return to identity anchor with micro push
    a08 = generate_agnes(
        ct,
        beat_id="beat_08",
        image=IMAGES / "05.png",
        out=VIDEO / "beat08_agnes.mp4",
        duration=5.0,
        prompt=PROMPT_MICRO,
    )
    a08_norm = normalize_clip(Path(a08["path"]), VIDEO / "beat08_agnes_norm.mp4")

    # beat_09 — on_body atmosphere only (pinkish); slow pan, not identity geometry
    still09 = make_still_clip(IMAGES / "01.png", STILLS / "b09_01_9s_pan.mp4", 9.0, mode="pan")

    # beat_10 — hero hold / close
    still10 = make_still_clip(IMAGES / "05.png", STILLS / "b10_05_8s_hold.mp4", 8.0, mode="hold")

    out = RENDERS / "batch03_31_60.mp4"
    concat([still07, a08_norm, still09, still10], out)

    report = {
        "batch_id": "batch_03",
        "time_span": "00:31-00:60",
        "path": str(out),
        "duration_probe": probe_duration(out),
        "beats": [
            {
                "beat": "beat_07",
                "time": "00:31-00:38",
                "method": "图片运镜（确定性微推）",
                "angle_use": "场景/花艺对照",
                "ref": "07.png",
                "path": str(still07),
                "status": "待过目",
            },
            {
                "beat": "beat_08",
                "time": "00:38-00:43",
                "method": "视频生成（Agnes）",
                "angle_use": "回身份锚点特写",
                "prompt_style": "micro_push",
                "ref": "05.png",
                "path": str(a08_norm),
                "raw_path": a08.get("path"),
                "status": "待过目",
                "actual_usd": a08.get("actual_usd"),
            },
            {
                "beat": "beat_09",
                "time": "00:43-00:52",
                "method": "图片运镜（确定性微横移）",
                "angle_use": "佩戴氛围（偏粉，不作身份几何）",
                "ref": "01.png",
                "path": str(still09),
                "status": "待过目",
            },
            {
                "beat": "beat_10",
                "time": "00:52-00:60",
                "method": "图片持镜",
                "angle_use": "正面收束",
                "ref": "05.png",
                "path": str(still10),
                "status": "待过目",
            },
        ],
        "cost_snapshot": cny_display_snapshot(
            ct.cost_snapshot(),
            usd_cny_rate=DEFAULT_USD_CNY,
            budget_cny=8,
        ),
        "created_at": utc_now(),
        "note_zh": "第3批待用户确认；确认后才整片终合成",
    }
    (ARTIFACTS / "batch03_review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for row in overview.get("overview", []):
        if row.get("beat") == "beat_07":
            row["asset"] = "b07_07_7s_zoom.mp4"
            row["status"] = "待过目"
        if row.get("beat") == "beat_08":
            row["asset"] = "beat08_agnes_norm.mp4"
            row["status"] = "待过目"
        if row.get("beat") == "beat_09":
            row["asset"] = "b09_01_9s_pan.mp4"
            row["status"] = "待过目"
        if row.get("beat") == "beat_10":
            row["asset"] = "b10_05_8s_hold.mp4"
            row["status"] = "待过目"
    overview_path.write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
    print("BATCH3_READY", out)
    return out


def phase_full(ct: CostTracker, *, continue_without_human: bool) -> Path:
    sample_meta = json.loads((ARTIFACTS / "sample_reel.json").read_text(encoding="utf-8"))
    if not sample_meta.get("approved") and not continue_without_human:
        raise RuntimeError("sample_reel not approved; pass --continue-full after review")

    clips: list[Path] = []
    # beat_01
    clips.append(make_still_clip(IMAGES / "05.png", STILLS / "b01_05_4s.mp4", 4.0))
    # beat_02 reuse sample agnes if present
    sample_agnes = VIDEO / "sample_agnes_05.mp4"
    if sample_agnes.exists():
        clips.append(sample_agnes)
        ai_meta = [{"beat_id": "beat_02", "status": "reused_sample", "path": str(sample_agnes)}]
    else:
        ai_meta = [
            generate_agnes(ct, beat_id="beat_02", image=IMAGES / "05.png", out=VIDEO / "beat02_agnes.mp4")
        ]
        clips.append(Path(ai_meta[-1]["path"]))

    clips.append(make_still_clip(IMAGES / "04.png", STILLS / "b03_04_5s.mp4", 5.0))
    ai_meta.append(
        generate_agnes(ct, beat_id="beat_04", image=IMAGES / "04.png", out=VIDEO / "beat04_agnes.mp4")
    )
    clips.append(Path(ai_meta[-1]["path"]))

    clips.append(make_still_clip(IMAGES / "03.png", STILLS / "b05_03_7s.mp4", 7.0))
    ai_meta.append(
        generate_agnes(ct, beat_id="beat_06", image=IMAGES / "03.png", out=VIDEO / "beat06_agnes.mp4")
    )
    clips.append(Path(ai_meta[-1]["path"]))

    clips.append(make_still_clip(IMAGES / "07.png", STILLS / "b07_07_7s.mp4", 7.0))
    ai_meta.append(
        generate_agnes(ct, beat_id="beat_08", image=IMAGES / "05.png", out=VIDEO / "beat08_agnes.mp4")
    )
    clips.append(Path(ai_meta[-1]["path"]))

    clips.append(make_still_clip(IMAGES / "01.png", STILLS / "b09_01_9s.mp4", 9.0))
    clips.append(make_still_clip(IMAGES / "05.png", STILLS / "b10_05_8s.mp4", 8.0, mode="hold"))

    out = RENDERS / "draft_60s.mp4"
    concat(clips, out)
    true_ai = 20.0  # 4 x 5s planned (sample reuse counts)
    report = {
        "path": str(out),
        "duration_probe": probe_duration(out),
        "true_video_seconds": true_ai,
        "meaningful_composed_motion_seconds": true_ai + 4 + 5 + 7 + 7 + 9,  # zooms counted soft
        "ai_clips": ai_meta,
        "cost_snapshot": cny_display_snapshot(
            ct.cost_snapshot(),
            usd_cny_rate=DEFAULT_USD_CNY,
            budget_cny=8,
        ),
        "hard_gate_pending_human": ["H1", "H2", "H3"],
        "created_at": utc_now(),
    }
    (ARTIFACTS / "draft_60s_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ARTIFACTS / "generation_manifest.json").write_text(
        json.dumps({"ai_clips": ai_meta, "updated_at": utc_now()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def approve_sample() -> None:
    path = ARTIFACTS / "sample_reel.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["approved"] = True
    data["status"] = "approved"
    data["approved_at"] = utc_now()
    data["approved_by"] = "operator_continue_full"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup-only", action="store_true")
    parser.add_argument("--sample", action="store_true", help="run sample reel only")
    parser.add_argument("--batch2", action="store_true", help="generate batch 02 (00:14-00:31) for review")
    parser.add_argument("--batch3", action="store_true", help="generate batch 03 (00:31-00:60) for review")
    parser.add_argument("--approve-sample", action="store_true")
    parser.add_argument("--full", action="store_true", help="run full 60s after sample approved")
    parser.add_argument(
        "--continue-full",
        action="store_true",
        help="mark sample approved by experiment authorization and run full",
    )
    args = parser.parse_args()

    marker = setup_project()
    print("project ready:", PROJECT)
    print("budget:", marker["production_profile"]["budget_cny"], "CNY experimental cap")

    if args.setup_only:
        return

    ct = tracker()

    if args.batch2:
        phase_batch2(ct)
        return

    if args.batch3:
        phase_batch3(ct)
        return

    if args.sample or (not args.full and not args.continue_full and not args.approve_sample):
        # default action when no flags: sample
        out = phase_sample(ct)
        print("SAMPLE_READY", out)
        print("Review sample then: --approve-sample --full   OR   --continue-full")
        if not args.continue_full and not args.full:
            return

    if args.approve_sample:
        approve_sample()
        print("sample approved")

    if args.continue_full:
        approve_sample()
        out = phase_full(ct, continue_without_human=True)
        print("DRAFT_READY", out)
        return

    if args.full:
        out = phase_full(ct, continue_without_human=False)
        print("DRAFT_READY", out)


if __name__ == "__main__":
    main()

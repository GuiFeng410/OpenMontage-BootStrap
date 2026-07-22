"""One-off production runner for agnes-neon-rain-30s (Agnes 3x10s + ffmpeg).

Prefer the shared orchestration path for new work:
  skills/meta/parallel-video-orchestration.md
  lib/parallel_generate.py
  scripts/run_parallel_video.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env", override=True)

from tools.video.agnes_video import AgnesVideo  # noqa: E402

MAX_RETRIES = 4
RETRY_BASE_SEC = 20

PROJECT = REPO / "projects" / "agnes-neon-rain-30s"
VIDEO_DIR = PROJECT / "assets" / "video"
SUBS_DIR = PROJECT / "assets" / "subs"
SUBS_WORK = SUBS_DIR / "_work"
RENDERS = PROJECT / "renders"
ARTIFACTS = PROJECT / "artifacts"

SCENES = [
    {
        "id": "scene01",
        "duration": 10,
        "prompt": (
            "Cinematic night alley entrance in a rainy East Asian city, neon signs glowing pink and cyan, "
            "wet cobblestones reflecting light, gentle rain droplets, slow forward camera push into the alley, "
            "moody atmosphere, realistic motion, filmic color grade, no text, no watermark"
        ),
        "caption": "雨夜巷口，霓虹初亮",
    },
    {
        "id": "scene02",
        "duration": 10,
        "prompt": (
            "Tracking shot along a rain-slicked neon city street at night, warm orange and cool blue reflections "
            "on wet asphalt, soft volumetric fog, pedestrians with umbrellas in soft focus background, "
            "smooth forward camera move, realistic motion, cinematic lighting, no text, no watermark"
        ),
        "caption": "湿街向前，灯影流动",
    },
    {
        "id": "scene03",
        "duration": 10,
        "prompt": (
            "Elevated side tracking shot of a rainy neon city skyline at night, dense glowing windows and billboards, "
            "misty air, slow lateral camera glide, distant traffic light trails, contemplative ending mood, "
            "realistic motion, filmic color grade, no text, no watermark"
        ),
        "caption": "灯海横移，夜色收束",
    },
]


def write_artifacts() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    brief = {
        "title": "雨夜霓虹·城市漫游",
        "theme": "A",
        "duration_sec": 30,
        "pipeline": "cinematic",
        "provider": "agnes",
        "model": "agnes-video-v2.0",
        "audio": {"narration": False, "subtitles": True, "bgm": False},
        "compose": "ffmpeg_concat",
    }
    (ARTIFACTS / "brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    scene_plan = {
        "scenes": [
            {
                "id": s["id"],
                "duration": s["duration"],
                "caption": s["caption"],
                "prompt": s["prompt"],
                "asset": f"assets/video/{s['id']}_agnes.mp4",
            }
            for s in SCENES
        ]
    }
    (ARTIFACTS / "scene_plan.json").write_text(
        json.dumps(scene_plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def generate_clips() -> list[Path]:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    tool = AgnesVideo()
    paths: list[Path] = []
    for i, scene in enumerate(SCENES, 1):
        out = VIDEO_DIR / f"{scene['id']}_agnes.mp4"
        if out.exists() and out.stat().st_size > 100_000:
            print(f"[{i}/3] skip existing {out.name} ({out.stat().st_size} bytes)")
            paths.append(out)
            continue

        print(f"[{i}/3] tool=agnes_video model=agnes-video-v2.0 duration={scene['duration']}s -> {out.name}")
        last_error = "unknown"
        for attempt in range(1, MAX_RETRIES + 1):
            result = tool.execute(
                {
                    "prompt": scene["prompt"],
                    "operation": "text_to_video",
                    "duration": scene["duration"],
                    "frame_rate": 24,
                    "aspect_ratio": "16:9",
                    "output_path": str(out),
                    "poll_interval_seconds": 5,
                    "timeout_seconds": 900,
                }
            )
            if result.success:
                print(
                    json.dumps(
                        {
                            "scene": scene["id"],
                            "seconds": result.data.get("seconds"),
                            "size": result.data.get("size"),
                            "wall": result.duration_seconds,
                            "attempt": attempt,
                        },
                        ensure_ascii=False,
                    )
                )
                break
            last_error = result.error or "unknown"
            retryable = any(x in last_error for x in ("503", "502", "429", "timeout", "Unavailable"))
            if not retryable or attempt >= MAX_RETRIES:
                raise RuntimeError(f"{scene['id']} failed: {last_error}")
            wait = RETRY_BASE_SEC * attempt
            print(f"  retry {attempt}/{MAX_RETRIES} after {wait}s: {last_error}")
            time.sleep(wait)
        else:
            raise RuntimeError(f"{scene['id']} failed: {last_error}")
        paths.append(out)
    return paths


def write_srt() -> Path:
    SUBS_DIR.mkdir(parents=True, exist_ok=True)
    SUBS_WORK.mkdir(parents=True, exist_ok=True)
    # 3 x 10s captions
    lines = [
        "1",
        "00:00:00,000 --> 00:00:10,000",
        SCENES[0]["caption"],
        "",
        "2",
        "00:00:10,000 --> 00:00:20,000",
        SCENES[1]["caption"],
        "",
        "3",
        "00:00:20,000 --> 00:00:30,000",
        SCENES[2]["caption"],
        "",
    ]
    srt = SUBS_DIR / "captions.srt"
    srt.write_text("\n".join(lines), encoding="utf-8")
    # E02: copy to work dir for relative path burn-in
    work_srt = SUBS_WORK / "captions.srt"
    shutil.copy2(srt, work_srt)
    return work_srt


def stitch(paths: list[Path], work_srt: Path) -> Path:
    RENDERS.mkdir(parents=True, exist_ok=True)
    list_file = VIDEO_DIR / "concat_list.txt"
    # ffmpeg concat demuxer needs forward-ish escaping; use absolute posix-ish for Windows carefully
    entries = []
    for p in paths:
        # Escape single quotes for concat file format
        ap = p.resolve().as_posix().replace("'", "'\\''")
        entries.append(f"file '{ap}'")
    list_file.write_text("\n".join(entries) + "\n", encoding="utf-8")

    concat_mp4 = RENDERS / "concat_raw.mp4"
    final_mp4 = RENDERS / "final.mp4"

    # Step 1: concat copy
    cmd1 = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(concat_mp4),
    ]
    print("concat...", " ".join(cmd1[:6]), "...")
    subprocess.run(cmd1, check=True, cwd=str(SUBS_WORK))

    # Step 2: burn subs from relative path inside SUBS_WORK (avoid D: colon bug)
    # Force style for readability on dark neon footage
    vf = "subtitles=captions.srt:force_style='Fontsize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=3,Outline=2,Shadow=0,MarginV=36'"
    cmd2 = [
        "ffmpeg", "-y",
        "-i", str(concat_mp4.resolve()),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(final_mp4.resolve()),
    ]
    print("burn_subs...")
    subprocess.run(cmd2, check=True, cwd=str(SUBS_WORK))
    return final_mp4


def main() -> None:
    write_artifacts()
    paths = generate_clips()
    work_srt = write_srt()
    final = stitch(paths, work_srt)
    print("DONE", final, "bytes", final.stat().st_size)


if __name__ == "__main__":
    main()

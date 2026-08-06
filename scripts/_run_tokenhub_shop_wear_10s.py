#!/usr/bin/env python3
"""TokenHub hy-video-1.5 shop-wear ~10s I2V smoke (2× clips + ffmpeg concat).

Usage:
  python scripts/_run_tokenhub_shop_wear_10s.py
  python scripts/_run_tokenhub_shop_wear_10s.py --force

Requires TOKENHUB_API_KEY in .env. Skips generation when final mp4 already exists
unless --force is set. Does not print or commit keys.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

load_dotenv(REPO / ".env", override=True)

from tools._tokenhub.client import (  # noqa: E402
    get_tokenhub_api_key,
    get_tokenhub_base_url,
)
from tools._tokenhub.models import DEFAULT_VIDEO_MODEL  # noqa: E402
from tools._tokenhub.video import generate_video  # noqa: E402

REF_DIR = REPO / "projects" / "agnes-test-shop-wear-10s" / "assets" / "images"
OUT_ROOT = REPO / "projects" / "tokenhub-shop-wear-10s"
SCENE_DIR = OUT_ROOT / "assets" / "video"
RENDER_DIR = OUT_ROOT / "renders"
FINAL_MP4 = RENDER_DIR / "product_10s.mp4"

SCENES = (
    {
        "name": "scene01_tokenhub",
        "image": REF_DIR / "woman-wear.png",
        "prompt": (
            "Elegant product showcase of a woman wearing statement earrings, "
            "gentle camera push-in, soft studio lighting, luxury jewelry commercial feel, "
            "subtle head turn, keep face and earrings sharp"
        ),
    },
    {
        "name": "scene02_tokenhub",
        "image": REF_DIR / "006.jpg",
        "prompt": (
            "Close-up jewelry commercial of earrings with soft sparkle highlights, "
            "slow orbiting camera, clean background, premium product video, "
            "metal and gem detail remain crisp"
        ),
    },
)


def _concat_ffmpeg(clips: list[Path], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    list_file = output.with_suffix(".txt")
    list_file.write_text(
        "".join(f"file '{c.resolve().as_posix()}'\n" for c in clips),
        encoding="utf-8",
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(output),
    ]
    subprocess.run(cmd, check=True)
    list_file.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="TokenHub shop-wear ~10s I2V smoke")
    parser.add_argument(
        "--force",
        action="store_true",
        help="regenerate even if product_10s.mp4 already exists",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_VIDEO_MODEL,
        help=f"video model id (default: {DEFAULT_VIDEO_MODEL})",
    )
    args = parser.parse_args()

    key = get_tokenhub_api_key()
    base = get_tokenhub_base_url()
    print(f"base_url={base}")
    print(f"api_key={'set' if key else 'MISSING'}")
    print(f"model={args.model}")
    print(f"final={FINAL_MP4}")

    if FINAL_MP4.exists() and not args.force:
        print(f"SKIP: final already exists ({FINAL_MP4.stat().st_size} bytes). Use --force to redo.")
        return 0

    if not key:
        print(
            "ERROR: TOKENHUB_API_KEY not set. Copy from .env.example into .env.",
            file=sys.stderr,
        )
        return 2

    for scene in SCENES:
        if not scene["image"].exists():
            print(f"ERROR: missing reference image: {scene['image']}", file=sys.stderr)
            return 2

    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)

    clips: list[Path] = []
    for scene in SCENES:
        out = SCENE_DIR / f"{scene['name']}.mp4"
        if out.exists() and not args.force:
            print(f"reuse clip {out}")
            clips.append(out)
            continue
        print(f"generate {scene['name']} from {scene['image'].name} …")
        result = generate_video(
            scene["prompt"],
            model=args.model,
            image_path=str(scene["image"]),
            output_path=out,
        )
        print(f"  job_id={result['job_id']} path={result['output_path']}")
        clips.append(Path(result["output_path"]))

    print(f"concat -> {FINAL_MP4}")
    _concat_ffmpeg(clips, FINAL_MP4)
    print(f"DONE {FINAL_MP4} ({FINAL_MP4.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

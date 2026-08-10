#!/usr/bin/env python3
"""TokenHub Pixverse T2V/I2V smoke (P0).

Usage:
  python scripts/_run_tokenhub_pixverse_smoke.py --mode t2v
  python scripts/_run_tokenhub_pixverse_smoke.py --mode i2v --image-url https://...
  python scripts/_run_tokenhub_pixverse_smoke.py --force

Requires TOKENHUB_API_KEY in .env. Skips when output exists unless --force.
I2V needs a public http(s) image URL (local path not supported in P0).
"""

from __future__ import annotations

import argparse
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
from tools._tokenhub.pixverse import PIXVERSE_DEFAULT_MODEL  # noqa: E402
from tools._tokenhub.video import generate_video  # noqa: E402

OUT_ROOT = REPO / "projects" / "tokenhub-pixverse-smoke"
RENDER_DIR = OUT_ROOT / "renders"


def main() -> int:
    parser = argparse.ArgumentParser(description="TokenHub Pixverse T2V/I2V smoke")
    parser.add_argument("--mode", choices=("t2v", "i2v"), default="t2v")
    parser.add_argument(
        "--image-url",
        default="",
        help="public http(s) URL for I2V (required when --mode i2v)",
    )
    parser.add_argument("--prompt", default="")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--quality", default="720p")
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--model", default=PIXVERSE_DEFAULT_MODEL)
    parser.add_argument(
        "--force",
        action="store_true",
        help="regenerate even if output mp4 already exists",
    )
    args = parser.parse_args()

    out = RENDER_DIR / f"pixverse_{args.mode}.mp4"
    key = get_tokenhub_api_key()
    base = get_tokenhub_base_url()
    print(f"base_url={base}")
    print(f"api_key={'set' if key else 'MISSING'}")
    print(f"model={args.model} mode={args.mode}")
    print(f"output={out}")

    if out.exists() and not args.force:
        print(f"SKIP: already exists ({out.stat().st_size} bytes). Use --force to redo.")
        return 0

    if not key:
        print(
            "ERROR: TOKENHUB_API_KEY not set. Copy from .env.example into .env.",
            file=sys.stderr,
        )
        return 2

    if args.mode == "i2v" and not str(args.image_url).startswith(("http://", "https://")):
        print(
            "ERROR: --mode i2v requires --image-url https://... "
            "(local paths not supported in P0).",
            file=sys.stderr,
        )
        return 2

    prompt = args.prompt.strip() or (
        "Elegant product showcase, gentle camera push-in, soft studio lighting"
        if args.mode == "i2v"
        else "一只橙色小猫在窗台上看向镜头，自然转头，柔和光线"
    )

    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    print(f"generate {args.mode} …")
    kwargs = {
        "model": args.model,
        "output_path": out,
        "duration": args.duration,
        "quality": args.quality,
        "aspect_ratio": args.aspect_ratio,
    }
    if args.mode == "i2v":
        kwargs["image_url"] = args.image_url

    result = generate_video(prompt, **kwargs)
    print(f"job_id={result.get('job_id')} path={result.get('output_path')}")
    print(f"DONE {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

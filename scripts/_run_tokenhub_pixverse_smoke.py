#!/usr/bin/env python3
"""TokenHub Pixverse T2V/I2V smoke (P0).

Usage:
  python scripts/_run_tokenhub_pixverse_smoke.py --mode t2v
  python scripts/_run_tokenhub_pixverse_smoke.py --mode i2v --image-url https://...
  python scripts/_run_tokenhub_pixverse_smoke.py --mode i2v --image-path a.png --confirm-cloud-upload
  python scripts/_run_tokenhub_pixverse_smoke.py --force

Requires TOKENHUB_API_KEY in .env. Skips when output exists unless --force.
I2V accepts a public URL, or a project-local image when OSS is configured and
--confirm-cloud-upload is supplied explicitly.
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
from lib.paths import PROJECTS_DIR  # noqa: E402

def main() -> int:
    parser = argparse.ArgumentParser(description="TokenHub Pixverse T2V/I2V smoke")
    parser.add_argument("--mode", choices=("t2v", "i2v"), default="t2v")
    parser.add_argument("--project-id", default="tokenhub-pixverse-smoke")
    parser.add_argument(
        "--image-url",
        default="",
        help="public http(s) URL for I2V",
    )
    parser.add_argument(
        "--image-path",
        default="",
        help="absolute path or filename relative to this project's assets/images",
    )
    parser.add_argument(
        "--confirm-cloud-upload",
        action="store_true",
        help="explicitly authorize this smoke run to upload the local image temporarily",
    )
    parser.add_argument("--prompt", default="")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--quality", default="360p")
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument(
        "--audio",
        action="store_true",
        help="request Pixverse native audio (default is silent)",
    )
    parser.add_argument("--model", default=PIXVERSE_DEFAULT_MODEL)
    parser.add_argument(
        "--force",
        action="store_true",
        help="regenerate even if output mp4 already exists",
    )
    args = parser.parse_args()

    render_dir = PROJECTS_DIR / args.project_id / "renders"
    out = render_dir / f"pixverse_{args.mode}.mp4"
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

    if args.image_url and args.image_path:
        print(
            "ERROR: choose only one of --image-url or --image-path.",
            file=sys.stderr,
        )
        return 2
    if args.mode == "i2v" and not args.image_url and not args.image_path:
        print(
            "ERROR: --mode i2v requires --image-url or --image-path.",
            file=sys.stderr,
        )
        return 2
    if args.image_url and not str(args.image_url).startswith(("http://", "https://")):
        print("ERROR: --image-url must be http(s).", file=sys.stderr)
        return 2
    if args.image_path and not args.confirm_cloud_upload:
        print(
            "ERROR: local image staging requires --confirm-cloud-upload.",
            file=sys.stderr,
        )
        return 2

    prompt = args.prompt.strip() or (
        "Elegant product showcase, gentle camera push-in, soft studio lighting"
        if args.mode == "i2v"
        else "一只橙色小猫在窗台上看向镜头，自然转头，柔和光线"
    )

    render_dir.mkdir(parents=True, exist_ok=True)
    print(f"generate {args.mode} …")
    kwargs = {
        "model": args.model,
        "output_path": out,
        "duration": args.duration,
        "quality": args.quality,
        "aspect_ratio": args.aspect_ratio,
        "generate_audio_switch": args.audio,
    }
    if args.mode == "i2v":
        if args.image_url:
            kwargs["image_url"] = args.image_url
        else:
            image_path = Path(args.image_path)
            if not image_path.is_absolute():
                image_path = (
                    PROJECTS_DIR
                    / args.project_id
                    / "assets"
                    / "images"
                    / image_path
                )
            kwargs["image_path"] = str(image_path.resolve())
            kwargs["project_id"] = args.project_id
            kwargs["user_authorized_upload"] = args.confirm_cloud_upload

    result = generate_video(prompt, **kwargs)
    print(f"job_id={result.get('job_id')} path={result.get('output_path')}")
    print(f"DONE {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

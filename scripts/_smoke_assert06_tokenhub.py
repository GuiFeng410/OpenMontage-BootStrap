#!/usr/bin/env python3
"""Short smoke: TokenHub hy-video-1.5 I2V + pixverse-video-v6.0 T2V using assert06 assets."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
load_dotenv(REPO / ".env", override=True)

from tools._tokenhub.client import get_tokenhub_api_key, get_tokenhub_base_url  # noqa: E402
from tools._tokenhub.video import generate_video  # noqa: E402

ASSETS = REPO / "projects" / "assert06"
OUT = ASSETS / "renders" / "smoke"
REF = ASSETS / "01.png"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    key = get_tokenhub_api_key()
    print(f"base={get_tokenhub_base_url()}")
    print(f"key_configured={bool(key)}")
    print(f"ref={REF} exists={REF.exists()} size={REF.stat().st_size if REF.exists() else 0}")
    if not key:
        print("FAIL: TOKENHUB_API_KEY empty in .env")
        return 2
    if not REF.exists():
        print(f"FAIL: missing {REF}")
        return 2

    results: list[tuple[str, str]] = []

    # 1) Hunyuan I2V — local image OK
    hy_out = OUT / "hy_i2v_5s.mp4"
    print("\n=== TEST 1: hy-video-1.5 I2V (local 01.png) ===")
    try:
        r = generate_video(
            "Elegant jewelry product turn, soft studio light, gentle camera push-in, keep subject sharp",
            model="hy-video-1.5",
            image_path=str(REF),
            output_path=hy_out,
            resolution="720p",
            poll_interval_seconds=5.0,
            timeout_seconds=600.0,
        )
        size = hy_out.stat().st_size if hy_out.exists() else 0
        print(f"OK job_id={r.get('job_id')} path={r.get('output_path')} bytes={size}")
        results.append(("hy-video-1.5 I2V", "PASS" if size > 10000 else "FAIL_small"))
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        results.append(("hy-video-1.5 I2V", "FAIL"))

    # 2) Pixverse T2V — no public URL needed
    pv_out = OUT / "pixverse_t2v_5s.mp4"
    print("\n=== TEST 2: pixverse-video-v6.0 T2V (5s) ===")
    try:
        r = generate_video(
            "Close-up of elegant silver bracelet on soft fabric, gentle sparkle, luxury commercial, slow orbit",
            model="pixverse-video-v6.0",
            output_path=pv_out,
            duration=5,
            quality="720p",
            aspect_ratio="16:9",
            poll_interval_seconds=5.0,
            timeout_seconds=600.0,
        )
        size = pv_out.stat().st_size if pv_out.exists() else 0
        print(f"OK job_id={r.get('job_id')} path={r.get('output_path')} bytes={size}")
        results.append(("pixverse-video-v6.0 T2V", "PASS" if size > 10000 else "FAIL_small"))
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        results.append(("pixverse-video-v6.0 T2V", "FAIL"))

    # 3) Pixverse I2V local path without project authorization — fail closed.
    print("\n=== TEST 3: pixverse I2V local path without authorization (expect reject) ===")
    try:
        generate_video(
            "gentle turn",
            model="pixverse-video-v6.0",
            image_path=str(REF),
            duration=5,
            quality="720p",
        )
        results.append(("pixverse I2V local", "UNEXPECTED_PASS"))
    except Exception as exc:
        print(f"EXPECTED_REJECT: {type(exc).__name__}: {exc}")
        results.append(("pixverse I2V local", "EXPECTED_REJECT"))

    print("\n=== SUMMARY ===")
    for name, status in results:
        print(f"  {status}\t{name}")
    failed = [s for _, s in results if s.startswith("FAIL")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

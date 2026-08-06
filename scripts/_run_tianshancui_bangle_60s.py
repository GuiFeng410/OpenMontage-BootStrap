#!/usr/bin/env python3
"""天山翠玉镯 ~60s Agnes I2V（TokenPlan 并发约 3）+ FFmpeg concat。

Usage:
  python scripts/_run_tianshancui_bangle_60s.py
  python scripts/_run_tianshancui_bangle_60s.py --force
  python scripts/_run_tianshancui_bangle_60s.py --assemble-only

Requires AGNES_API_KEY in .env. Prefer AGNES_ACCOUNT_TIER=tokenplan.
Does not print or commit keys. Does not push remotes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

load_dotenv(REPO / ".env", override=True)

from lib.parallel_generate import (  # noqa: E402
    assemble_ffmpeg,
    estimate_wall_seconds,
    make_agnes_generate_fn,
    normalize_agnes_account_tier,
    progress_report,
    project_dir,
    read_json,
    resolve_agnes_concurrency,
    run_parallel_generate,
    scene_plan_path,
    write_json,
)
from tools._agnes import get_agnes_api_key  # noqa: E402

PROJECT_ID = "tianshancui-bangle-60s"


def main() -> int:
    parser = argparse.ArgumentParser(description="天山翠玉镯 60s Agnes I2V TokenPlan")
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略已有 clip，强制重生成（先删/改名 assets/video 下对应文件）",
    )
    parser.add_argument(
        "--assemble-only",
        action="store_true",
        help="跳过生成，仅拼接已有 clip",
    )
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="拼接时不烧字幕",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="覆盖并发（默认 scene_plan / tokenplan=3）",
    )
    args = parser.parse_args()

    # Ensure TokenPlan unless user already set another tier explicitly via env/plan
    if not os.environ.get("AGNES_ACCOUNT_TIER"):
        os.environ["AGNES_ACCOUNT_TIER"] = "tokenplan"

    project = project_dir(PROJECT_ID)
    plan_path = scene_plan_path(project)
    if not plan_path.exists():
        print(f"ERROR: missing scene_plan: {plan_path}", file=sys.stderr)
        return 2

    plan = read_json(plan_path)
    parallel = plan.setdefault("parallel", {})
    tier = normalize_agnes_account_tier(
        parallel.get("account_tier") or plan.get("account_tier") or "tokenplan"
    )
    parallel["account_tier"] = tier
    plan["account_tier"] = tier

    resolved = resolve_agnes_concurrency(
        args.concurrency if args.concurrency is not None else parallel.get("max_concurrency"),
        force=False,
        tier=tier,
    )
    parallel["max_concurrency"] = resolved["concurrency"]
    write_json(plan_path, plan)

    key = get_agnes_api_key()
    print(f"project={project}")
    print(f"agnes_key={'set' if key else 'MISSING'}")
    print(f"account_tier={resolved['tier']} concurrency={resolved['concurrency']} capped={resolved['capped']}")
    print(f"scenes={len(plan.get('scenes') or [])}")
    est = estimate_wall_seconds(len(plan.get("scenes") or []), max_concurrency=resolved["concurrency"])
    print(
        f"estimate_batches={int(est['batches'])} "
        f"optimistic~{est['optimistic_seconds']/60:.1f}min "
        f"conservative~{est['conservative_seconds']/60:.1f}min"
    )

    # Validate images
    for scene in plan.get("scenes") or []:
        op = scene.get("operation") or plan.get("operation") or "image_to_video"
        if op != "image_to_video":
            continue
        rel = scene.get("image_path") or scene.get("reference_image_path")
        if not rel:
            print(f"ERROR: {scene.get('id')} missing image_path", file=sys.stderr)
            return 2
        img = (project / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        if not img.is_file():
            print(f"ERROR: missing image for {scene.get('id')}: {img}", file=sys.stderr)
            return 2

    if args.force:
        for scene in plan.get("scenes") or []:
            out = project / scene["asset"]
            if out.exists():
                bak = out.with_suffix(out.suffix + f".bak_{int(time.time())}")
                out.rename(bak)
                print(f"force: renamed {out.name} -> {bak.name}")

    if args.assemble_only:
        final = assemble_ffmpeg(project, plan, burn_subtitles=not args.no_subtitles)
        print(f"DONE assemble {final} bytes={final.stat().st_size}")
        return 0

    if not key:
        print("ERROR: AGNES_API_KEY / AGNES_AI_API_KEY not set in .env", file=sys.stderr)
        return 2

    # Ensure each scene is I2V
    for scene in plan.get("scenes") or []:
        scene.setdefault("operation", "image_to_video")

    wave_log: list[dict] = []
    t_run0 = time.perf_counter()

    def on_done(result, manifest):
        wave_log.append(
            {
                "scene_id": result.scene_id,
                "status": result.status,
                "wall_seconds": result.wall_seconds,
                "attempts": result.attempts,
                "error": result.error,
                "t_rel": round(time.perf_counter() - t_run0, 1),
            }
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False))
        print(progress_report(manifest))
        sys.stdout.flush()

    def on_reduced(new_conc: int, reason: str) -> None:
        print(f"NOTE: concurrency reduced to {new_conc} due to rate limit: {reason}", file=sys.stderr)
        sys.stderr.flush()

    generate_fn = make_agnes_generate_fn(
        frame_rate=24,
        aspect_ratio="16:9",
        poll_interval_seconds=int(parallel.get("poll_interval_seconds") or 8),
        timeout_seconds=900,
        project=project,
        default_operation="image_to_video",
        product_id=plan.get("product_id"),
    )

    print(
        f"START generate tool=agnes_video operation=image_to_video "
        f"model=agnes-video-v2.0 concurrency={resolved['concurrency']}"
    )
    sys.stdout.flush()

    manifest = run_parallel_generate(
        project,
        plan,
        generate_fn,
        max_concurrency=resolved["concurrency"],
        on_scene_done=on_done,
        on_concurrency_reduced=on_reduced,
    )

    print(progress_report(manifest))
    print("wave_completion_order=" + json.dumps(wave_log, ensure_ascii=False))
    print(
        f"final_concurrency={manifest.get('max_concurrency')} "
        f"reduced_reason={manifest.get('concurrency_reduced_reason')}"
    )

    incomplete = [
        s
        for s in manifest.get("scenes") or []
        if s.get("status") not in ("completed", "skipped")
    ]
    if incomplete:
        print(f"FAIL: generate incomplete ({len(incomplete)}):", file=sys.stderr)
        for s in incomplete:
            print(f"  - {s.get('id')}: {s.get('status')} {s.get('error')}", file=sys.stderr)
        return 1

    final = assemble_ffmpeg(project, plan, burn_subtitles=not args.no_subtitles)
    print(f"DONE final={final} exists={final.exists()} bytes={final.stat().st_size if final.exists() else 0}")
    print(f"wall_total_sec={time.perf_counter() - t_run0:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

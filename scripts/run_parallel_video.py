#!/usr/bin/env python3
"""CLI for long-video parallel plan / generate / assemble.

Default modes do NOT call cloud video APIs. Use --mode generate only after
the user confirms the theme and scene_plan.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

load_dotenv(REPO / ".env", override=True)

from lib.parallel_generate import (  # noqa: E402
    assemble_ffmpeg,
    brief_path,
    build_scene_plan,
    default_parallel_config,
    estimate_wall_seconds,
    generation_manifest_path,
    init_generation_manifest,
    load_or_init_manifest,
    make_agnes_generate_fn,
    mark_existing_clips,
    normalize_agnes_account_tier,
    plan_segments,
    planning_report,
    progress_report,
    project_dir,
    read_json,
    resolve_agnes_concurrency,
    run_parallel_generate,
    save_manifest,
    scene_plan_path,
    write_json,
)


def _load_plan(project: Path) -> dict:
    path = scene_plan_path(project)
    if not path.exists():
        raise SystemExit(f"missing scene_plan: {path} (run --mode plan first)")
    return read_json(path)


def _resolve_cli_concurrency(args: argparse.Namespace) -> dict:
    requested = None if args.concurrency is None else int(args.concurrency)
    resolved = resolve_agnes_concurrency(
        requested,
        force=bool(args.force_concurrency),
        tier=args.account_tier,
    )
    if resolved["capped"] and requested is not None:
        print(
            f"NOTE: concurrency {requested} exceeds tier={resolved['tier']} "
            f"cap={resolved['cap']}; using {resolved['concurrency']}. "
            f"Pass --force-concurrency to override.",
            file=sys.stderr,
        )
    return resolved


def cmd_plan(args: argparse.Namespace) -> None:
    project = project_dir(args.project)
    project.mkdir(parents=True, exist_ok=True)
    (project / "artifacts").mkdir(parents=True, exist_ok=True)
    (project / "assets" / "video").mkdir(parents=True, exist_ok=True)
    (project / "renders").mkdir(parents=True, exist_ok=True)

    resolved = _resolve_cli_concurrency(args)
    segs = plan_segments(args.target_seconds, segment_seconds=args.segment_seconds)
    scenes = []
    for seg in segs:
        scenes.append(
            {
                "id": seg.scene_id,
                "duration": seg.duration,
                "prompt": args.prompt_placeholder,
                "caption": f"{seg.scene_id} 占位字幕",
            }
        )

    # Optional: merge prompts/captions from an input JSON scene list
    if args.scenes_json:
        override = read_json(Path(args.scenes_json))
        if isinstance(override, dict) and "scenes" in override:
            override = override["scenes"]
        by_id = {s["id"]: s for s in override}
        for s in scenes:
            if s["id"] in by_id:
                s.update({k: v for k, v in by_id[s["id"]].items() if k != "id"})

    parallel = default_parallel_config(
        max_concurrency=resolved["concurrency"],
        force=True,  # already resolved/capped above
        tier=resolved["tier"],
    )
    plan = build_scene_plan(
        scenes,
        provider=args.provider,
        model=args.model,
        parallel=parallel,
        extra={
            "title": args.title,
            "target_duration_sec": args.target_seconds,
            "account_tier": resolved["tier"],
        },
    )
    write_json(scene_plan_path(project), plan)

    brief = {
        "title": args.title,
        "duration_sec": args.target_seconds,
        "provider": args.provider,
        "model": args.model,
        "account_tier": resolved["tier"],
        "audio": {
            "narration": False,
            "subtitles": not args.no_subtitles,
            "bgm": False,
        },
        "compose": "ffmpeg_concat",
        "parallel": plan["parallel"],
    }
    write_json(brief_path(project), brief)

    manifest = init_generation_manifest(
        args.project,
        plan["scenes"],
        max_concurrency=resolved["concurrency"],
        provider=args.provider,
    )
    manifest["account_tier"] = resolved["tier"]
    save_manifest(project, manifest)

    print(
        planning_report(
            project_id=args.project,
            target_seconds=args.target_seconds,
            segments=segs,
            max_concurrency=resolved["concurrency"],
            provider=args.provider,
            model=args.model,
            subtitles=not args.no_subtitles,
            account_tier=resolved["tier"],
        )
    )
    print(f"\nwrote {scene_plan_path(project)}")
    print(f"wrote {generation_manifest_path(project)}")
    print("NOTE: prompts are placeholders until you replace them / pass --scenes-json")


def cmd_status(args: argparse.Namespace) -> None:
    project = project_dir(args.project)
    plan = _load_plan(project)
    manifest = load_or_init_manifest(project, plan)
    mark_existing_clips(project, manifest, plan)
    save_manifest(project, manifest)
    print(progress_report(manifest))
    conc = int((plan.get("parallel") or {}).get("max_concurrency") or resolve_agnes_concurrency()["concurrency"])
    est = estimate_wall_seconds(len(plan.get("scenes") or []), max_concurrency=conc)
    print(
        f"\nestimate_batches={int(est['batches'])} "
        f"optimistic~{est['optimistic_seconds']/60:.1f}min "
        f"conservative~{est['conservative_seconds']/60:.1f}min"
    )


def cmd_assemble(args: argparse.Namespace) -> None:
    project = project_dir(args.project)
    plan = _load_plan(project)
    final = assemble_ffmpeg(project, plan, burn_subtitles=not args.no_subtitles)
    print("DONE", final, "bytes", final.stat().st_size)


def cmd_generate(args: argparse.Namespace) -> None:
    if not args.i_confirm_generate:
        raise SystemExit(
            "Refusing to call cloud video APIs. "
            "Re-run with --i-confirm-generate after the user approved the plan."
        )
    project = project_dir(args.project)
    plan = _load_plan(project)
    resolved = _resolve_cli_concurrency(args)
    plan.setdefault("parallel", {})["max_concurrency"] = resolved["concurrency"]
    plan.setdefault("parallel", {})["account_tier"] = resolved["tier"]
    plan["account_tier"] = resolved["tier"]

    def on_done(result, manifest):
        print(json.dumps(result.to_dict(), ensure_ascii=False))
        print(progress_report(manifest))

    def on_reduced(new_conc: int, reason: str) -> None:
        print(f"NOTE: concurrency reduced to {new_conc} due to rate limit: {reason}", file=sys.stderr)

    if args.provider != "agnes":
        raise SystemExit(f"CLI generate currently supports provider=agnes only, got {args.provider}")

    manifest = run_parallel_generate(
        project,
        plan,
        make_agnes_generate_fn(),
        max_concurrency=resolved["concurrency"],
        force_concurrency=bool(args.force_concurrency),
        on_scene_done=on_done,
        on_concurrency_reduced=on_reduced,
    )
    incomplete = [
        s
        for s in manifest.get("scenes") or []
        if s.get("status") not in ("completed", "skipped")
    ]
    if incomplete:
        raise SystemExit(f"generate incomplete: {len(incomplete)} not done — {incomplete}")
    print(progress_report(manifest))
    if args.assemble_after:
        final = assemble_ffmpeg(project, plan, burn_subtitles=not args.no_subtitles)
        print("DONE", final, "bytes", final.stat().st_size)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Parallel long-video plan/generate/assemble")
    p.add_argument("--project", required=True, help="project id under projects/")
    p.add_argument(
        "--mode",
        choices=("plan", "status", "assemble", "generate"),
        required=True,
    )
    p.add_argument("--title", default="Untitled parallel video")
    p.add_argument("--target-seconds", type=float, default=30.0)
    p.add_argument("--segment-seconds", type=float, default=10.0)
    p.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="override concurrency (capped by AGNES_ACCOUNT_TIER unless --force-concurrency)",
    )
    p.add_argument(
        "--force-concurrency",
        action="store_true",
        help="allow concurrency above tier cap (not recommended)",
    )
    p.add_argument(
        "--account-tier",
        default=None,
        help="default|enterprise|tokenplan (default: env AGNES_ACCOUNT_TIER or default)",
    )
    p.add_argument("--provider", default="agnes")
    p.add_argument("--model", default="agnes-video-v2.0")
    p.add_argument("--scenes-json", default=None, help="optional JSON list/object to fill prompts")
    p.add_argument(
        "--prompt-placeholder",
        default="REPLACE_ME: cinematic shot, realistic motion, no text, no watermark",
    )
    p.add_argument("--no-subtitles", action="store_true")
    p.add_argument(
        "--i-confirm-generate",
        action="store_true",
        help="required for --mode generate (cloud API)",
    )
    p.add_argument(
        "--assemble-after",
        action="store_true",
        help="with --mode generate, also run FFmpeg assemble",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.account_tier is not None:
        args.account_tier = normalize_agnes_account_tier(args.account_tier)
    if args.mode == "plan":
        cmd_plan(args)
    elif args.mode == "status":
        cmd_status(args)
    elif args.mode == "assemble":
        cmd_assemble(args)
    elif args.mode == "generate":
        cmd_generate(args)
    else:
        raise SystemExit(f"unknown mode: {args.mode}")


if __name__ == "__main__":
    main()

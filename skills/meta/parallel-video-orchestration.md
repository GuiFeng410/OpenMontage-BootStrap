# Parallel Video Orchestration — Meta Skill

## When to Use

Use this skill when the user wants a **multi-clip AI video** longer than one provider shot (e.g. Agnes ~18s), or `scene_plan` has **≥ 2** cloud T2V scenes.

**Do NOT use** for: single-clip shorts; pure local footage trim/concat; slideshow-only jobs.

**Full spec:** `docs/长视频并行编排/01-编排规范.md`  
**Code:** `lib/parallel_generate.py`

## Core Rule

> Parallelize **cloud generation**. Assemble **once** with FFmpeg.  
> Do **not** tree-merge with sub-agents (6→3→1). Local concat is cheap.

Default segment length: **10s** (or 5–8s when more cuts help). Cap **≤ 10s** unless the provider docs say otherwise.

Default concurrency: **2–3**. Start at 3; drop to 1 if 503s spike.

## Agent Contract

### Phase A — Plan (no cloud calls)

1. Confirm with the user: target duration, theme, audio (subs / narration / BGM), provider.
2. Split duration:

```python
from lib.parallel_generate import plan_segments, planning_report, estimate_wall_seconds

segs = plan_segments(30)  # -> scene01..scene03 @ 10s
```

3. Write `artifacts/brief.json` + `artifacts/scene_plan.json` via `build_scene_plan(...)`.
4. Init `artifacts/generation_manifest.json` via `init_generation_manifest` / `load_or_init_manifest`.
5. Show `planning_report(...)` and **wait for user confirmation** before generate.

### Phase B — Parallel generate

**Preferred (Cursor):** dispatch one Task subagent per pending scene (pool size ≤ `max_concurrency`). Each subagent follows `docs/长视频并行编排/03-子Agent任务单模板.md`.

**Preferred (local/script):**

```python
from lib.parallel_generate import (
    run_parallel_generate,
    make_agnes_generate_fn,
    progress_report,
    read_json,
    scene_plan_path,
    project_dir,
)

project = project_dir("my-project")
plan = read_json(scene_plan_path(project))
manifest = run_parallel_generate(project, plan, make_agnes_generate_fn())
print(progress_report(manifest))
```

Rules:
- Skip clips that already exist and are large enough (`skip_if_exists_min_bytes`).
- Retry 503/502/429/timeout with backoff; fail fast on 401.
- Update manifest after every scene; report progress to the user.

### Phase C — Assemble (main agent only)

```python
from lib.parallel_generate import assemble_ffmpeg

final = assemble_ffmpeg(project, plan, burn_subtitles=True)
# -> projects/<id>/renders/final.mp4
```

One concat + optional subtitle burn. Windows: SRT is copied under `assets/subs/_work/` (relative path, avoid drive-colon bug).

## CLI (no generation by default)

```bash
# Dry plan + write artifacts (no Agnes)
python scripts/run_parallel_video.py --project my-id --mode plan --target-seconds 30 --title "Demo"

# Status / manifest only
python scripts/run_parallel_video.py --project my-id --mode status

# Assemble only (clips must already exist)
python scripts/run_parallel_video.py --project my-id --mode assemble

# Explicit generate (only when user approved)
python scripts/run_parallel_video.py --project my-id --mode generate --concurrency 3
```

`--mode generate` must only run after the user confirmed the plan.

## Subagent boundaries

| Role | Does | Does not |
|------|------|----------|
| Main agent | Plan, pool dispatch, assemble, user reports | Generate every clip serially when parallel is available |
| Scene subagent | One `sceneXX` clip + manifest update for that id | Concat, edit plan, touch other scenes |

## Success checks

- [ ] `generation_manifest.json` summary: no `pending`/`running`/`failed` (or failed acknowledged)
- [ ] Clips exist in scene_plan order under `assets/video/`
- [ ] `renders/final.mp4` duration ≈ sum of scene durations
- [ ] If captions requested: burned or SRT present under `assets/subs/`

## Anti-patterns

- Serial cloud loops for 6×10s without concurrency
- Subagent pairwise merge trees
- Starting `--mode generate` before user confirms theme/plan
- Writing clips outside `projects/<id>/`

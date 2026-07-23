# Parallel Video Orchestration — Meta Skill

## When to Use

Use this skill when the user wants a **multi-clip AI video** longer than one provider shot (e.g. Agnes ~18s), or `scene_plan` has **≥ 2** cloud T2V scenes.

**Do NOT use** for: single-clip shorts; pure local footage trim/concat; slideshow-only jobs.

**Full spec:** `docs/Phase/A_01-长视频生成-steps/01-编排规范.md`  
**Product flow (frozen):** `docs/Plan/A_01-长视频生成/01-总流程-v1.0.md`  
**Code:** `lib/parallel_generate.py`

## Core Rule

> Parallelize **cloud generation**. Assemble **once** with FFmpeg.  
> Do **not** tree-merge with sub-agents (6→3→1). Local concat is cheap.

Default segment length: **10s** (or 5–8s when more cuts help). Cap **≤ 10s** unless the provider docs say otherwise.

Default concurrency follows **`AGNES_ACCOUNT_TIER`** (see Agnes Token Plan video RPM):

| Tier | Default concurrency | Cap (without `--force-concurrency`) |
|------|---------------------|-------------------------------------|
| `default` | **1** | 1 |
| `enterprise` | **2** | 2 |
| `tokenplan` | **3** | 3 |

On 429/503 failures, remaining work drops to concurrency **1**. Always show **optimistic + conservative** wall-time in `planning_report`.

## Agent Contract

### Phase A — Plan (no cloud calls)

1. Confirm with the user: target duration, theme, audio (subs / narration / BGM), provider.
2. Split duration:

```python
from lib.parallel_generate import (
    plan_segments,
    planning_report,
    resolve_agnes_concurrency,
    build_scene_plan,
)

segs = plan_segments(30)  # -> scene01..scene03 @ 10s
resolved = resolve_agnes_concurrency()  # reads AGNES_ACCOUNT_TIER
```

3. Write `artifacts/brief.json` + `artifacts/scene_plan.json` via `build_scene_plan(...)` (parallel defaults from tier).
4. Init `artifacts/generation_manifest.json` via `init_generation_manifest` / `load_or_init_manifest`.
5. Show `planning_report(..., account_tier=resolved["tier"])` with **双档预估** and **wait for user confirmation** before generate.

### Phase B — Parallel generate

**Preferred (Cursor):** dispatch one Task subagent per pending scene (pool size ≤ `max_concurrency`). Each subagent follows `docs/Phase/A_01-长视频生成-steps/03-子Agent任务单模板.md`.

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
- Retry 503/502/429/timeout with backoff (429 uses longer wait); fail fast on 401.
- On rate-limit failures, reduce concurrency to 1 for not-yet-started scenes.
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
python scripts/run_parallel_video.py --project my-id --mode generate --i-confirm-generate --account-tier tokenplan

# Override concurrency above tier cap (not recommended)
python scripts/run_parallel_video.py --project my-id --mode generate --i-confirm-generate --concurrency 5 --force-concurrency
```

`--mode generate` must only run after the user confirmed the plan. Set `AGNES_ACCOUNT_TIER=tokenplan` in `.env` when using Token Plan.

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

- Serial cloud loops for 6×10s without concurrency (when tier allows >1)
- Defaulting Agnes **default** tier to concurrency 3
- Subagent pairwise merge trees
- Starting `--mode generate` before user confirms theme/plan
- Writing clips outside `projects/<id>/`

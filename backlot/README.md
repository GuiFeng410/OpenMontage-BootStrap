# Backlot — the living storyboard

A read-only local board that shows a production happening: pipeline stages
lighting up, the script as a screenplay page, the scene plan as a filmstrip
that fills in as assets generate, decisions, spend, and activity — all
derived from what the pipeline already writes to `projects/<id>/`.

```bash
python -m backlot open <project-id>   # start server if needed + open browser
python -m backlot open                # library view (all projects)
python -m backlot serve --port 4750   # run the server in the foreground
```

## How it stays live

No agent involvement. A `watchfiles` watcher on `projects/` publishes change
notifications over SSE; the browser refetches board state. State sources:

| Board element | Disk source |
|---|---|
| identity / rail order | `project.json` + `pipeline_defs/<type>.yaml` |
| stage states, gates, versions | `checkpoint_<stage>.json` + `history/` |
| script card / modal | `artifacts/script.json` |
| filmstrip cards | `scene_plan × script × asset_manifest` join |
| generating shimmer, activity | `events.jsonl` (written by `BaseTool` instrumentation) |
| cost meter | checkpoint `cost_snapshot` |
| renders | `renders/*.mp4` (+ root-level mp4 heuristic) |

For `bootstrap-commercial`, the board is also the read-only decision evidence
surface. The Agent writes one current choice into checkpoint `metadata`
(`needs_user_decision`, `decision_prompt_zh`, `decision_options`, recommendation,
examples, and partial progress); the user still approves in chat. Backlot never
writes project state or submits approval.

## B1 interaction boundary

- Backlot does not write checkpoint/artifact/decision truth.
- B1 may store `sessionStorage`-only decision drafts and copy chat summaries.
- `POST /intents` is the sole server-side write exception: edit intents keep
  the editing gate; B2 interaction intents skip that gate but still only
  write `projects/<id>/intents/`.
- Formal approval remains in chat. The panel never writes checkpoint,
  decision log, or canonical artifacts, and never triggers paid generate.

B1 copy-summary stays as the fallback when the B2 submit request fails.

The draft key is
`backlot.intent-draft.v1:<project_id>:<stage>`. Its revision covers project,
stage, checkpoint timestamp and the normalized decision payload. A matching
revision restores the draft. A changed revision is stale, while malformed JSON
is corrupt; both fail closed, disable the old choices and require
“清空并重选”.

Copying uses `navigator.clipboard.writeText` when available. If Clipboard API
access fails, the summary stays visible, receives focus and is selected for
manual copy.

## B1.1 Library boundary

- Library is localized to Chinese.
- It displays the local service, project count and collapsed projects root.
- Review-mode picker (极简 / 普通 / 专业) previews only the confirmation
  steps for that mode.
- “开始创建项目”在填好主题后即可点；本机创建项目，不调付费接口。成功后跳到 `/p/<id>` 看板。
- Copy-to-chat remains a fallback and includes the selected review mode.
- If create fails (environment missing), the page explains and chat remains the fallback. The Agent still reads `.openmontage/install-state.json` so a finished install is not repeated.
- Backlot `serve` writes/refreshes `.openmontage/install-state.json` (no secrets) so a new chat can see this machine already used the repo.
- Clipboard failure keeps a selectable textarea.

## UI module ownership

- `board.js`: thin page entry and board assembly.
- `board-core.js`: state normalization, refresh and live-feed lifecycle.
- `board-rail.js`: stage rail/drawer rendering and stage labels.
- `board-commercial.js`: commercial evidence views and media guards.
- `board-replay.js`: replay state, controls and projected views.
- `board-intent-state.js`: pure decision-draft, revision and storage helpers.
- `board-intent-panel.js`: commercial option buttons, copy fallback, and
  「提交待确认」.
- `board-intent-submit.js`: POST `/intents` helper for pending `decision`
  intents; never posts `approval_bundle`.
- `library.js`: Library cards, localized status labels and onboarding wiring.
- `library-onboarding.js`: create-product-video prompt, review-mode route map, service info and Clipboard helper.
- `library.css`: Library onboarding and empty-state styles.

Existing selectors and behavior remain compatibility contracts, including
`.commercial-decision-option`, `.commercial-intent-summary`,
`.commercial-chat-only`, the replay controls and generic/commercial/edit view
boundaries.

## B2 interaction / fast-track v2 boundary

- Panel button is 「提交待确认」. Success copy is
  `已提交。请留在本页等待本机处理。`
- The page never shows 「批准」「立即创建」「开始生成」「已生效」.
- Chat confirmation for panel intents is exactly `确认面板选择` (fallback).
  「直接出片」 is not approval evidence.
- Local runner starts with `python -m backlot open` and consumes pending
  intents via `produce_runner_tick`. Browser still only POSTs intents.
- End-and-export button writes `project_export`; chat phrase is `结束导出`.
- Agent tools: `produce_list_interaction_intents`,
  `produce_plan_approval_bundle` (promotes a pending panel `decision` into a
  complete §6.3 `approval_bundle` using project evidence; missing evidence
  fails closed), `produce_apply_approval_bundle`
  (`confirm_phrase` required; writes `selected="fast_track_v2"`),
  `produce_fast_track_evaluate` (read-only),
  `produce_apply_project_export`, `produce_runner_tick`.
- Fast-track v2 may use the visible Backlot-side runner; Agent must not
  silently start a daemon, silently pay, or silently switch providers.
- Evaluate missing fields fail-closed. Generated images still pause for
  batch review. Delivery waits for signoff. Project completion is
  「结束并导出项目」 only.
- On evaluate `pause`, the Agent must `produce_write_checkpoint` with
  `metadata.fast_track_pause` so the board can echo the Chinese reason.
- Board echoes interaction intent status, checkpoint `metadata.fast_track_pause`,
  and a playable/downloadable `renders/final.mp4`. The browser does not apply.

Projects without checkpoints degrade gracefully to a "what the watcher
found" view — media, snapshots, renders.

**Replay**: a completed run can be scrubbed end-to-end (▶ REPLAY RUN on the
board) — reconstructed from checkpoint history and event timestamps.

Try it without a real production:

```bash
python scripts/backlot_simulate_run.py          # live demo run (~1 min)
python -m backlot open backlot-demo-run
```

Design doc: `internal/design/LIVING_STORYBOARD.md`.

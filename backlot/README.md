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
- `POST /intents` remains the sole server-side write exception and is edit-only.
- B2 interaction intents and fast-track v2 are not implemented.

Formal approval remains in chat. The commercial decision panel only prepares a
local draft and a copyable summary; it never posts the commercial selection or
mutates project truth.

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
- “创建新商品片” copies a chat request; it does not create a project.
- Clipboard failure keeps a selectable textarea.
- Formal creation remains Agent/BootStrap in chat.
- No create/upload POST exists.
- B2 remains deferred.

## UI module ownership

- `board.js`: thin page entry and board assembly.
- `board-core.js`: state normalization, refresh and live-feed lifecycle.
- `board-rail.js`: stage rail/drawer rendering and stage labels.
- `board-commercial.js`: commercial evidence views and media guards.
- `board-replay.js`: replay state, controls and projected views.
- `board-intent-state.js`: pure decision-draft, revision and storage helpers.
- `board-intent-panel.js`: commercial option buttons, summary and copy feedback.
- `library.js`: Library cards, localized status labels and onboarding wiring.
- `library-onboarding.js`: create-product-video prompt, service info and Clipboard helper.
- `library.css`: Library onboarding and empty-state styles.

Existing selectors and behavior remain compatibility contracts, including
`.commercial-decision-option`, `.commercial-intent-summary`,
`.commercial-chat-only`, the replay controls and generic/commercial/edit view
boundaries. B2 server-backed interaction intents, approval bundles and
fast-track v2 remain deferred.

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

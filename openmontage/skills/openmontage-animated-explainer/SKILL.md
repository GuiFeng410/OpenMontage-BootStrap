---
name: openmontage-animated-explainer
description: Drive zero-key animated-explainer pipeline via OpenMontage doctor+media MCP with human gates.
metadata:
  openclaw:
    requires:
      bins:
        - python
        - ffmpeg
        - node
      env:
        - OPENMONTAGE_PROJECTS_DIR
      anyBins:
        - piper
        - piper-tts
    primaryEnv: OPENMONTAGE_PROJECTS_DIR
    envVars:
      - name: OPENMONTAGE_PROJECTS_DIR
        required: true
        description: Sandboxed projects root for all artifacts and renders
      - name: OPENMONTAGE_P1_ALLOW_WRITES
        required: true
        description: Must be true on the production Agent for checkpoint/artifact writes
      - name: PIPER_MODEL_DIR
        required: false
        description: Piper voice model directory
      - name: OPENMONTAGE_PIPER_MODEL
        required: false
        description: Default voice slug (e.g. zh_CN-huayan-medium)
    os:
      - win32
      - darwin
      - linux
    emoji: "🎥"
---

# OpenMontage Animated Explainer (P1)

## Scope

Zero-key **animated-explainer** only. Cloud video/image APIs are out of scope unless the user explicitly upgrades later.

## Required MCP servers

- `openmontage-doctor` (state, checkpoints, artifacts)
- `openmontage-media` (Piper, diagrams, subtitles, compose jobs)

Tool names may appear as `openmontage-doctor__*` / `openmontage-media__*`.

## Pipeline contract

Manifest: `pipeline_defs/animated-explainer.yaml`

Stage directors live in the monorepo (read before each stage):

1. `skills/pipelines/explainer/research-director.md`
2. `skills/pipelines/explainer/proposal-director.md` — **human gate**
3. `skills/pipelines/explainer/script-director.md` — **human gate**
4. `skills/pipelines/explainer/scene-director.md` — **human gate**
5. `skills/pipelines/explainer/asset-director.md` — **human gate** (+ TTS sample)
6. `skills/pipelines/explainer/edit-director.md`
7. `skills/pipelines/explainer/compose-director.md`
8. `skills/pipelines/explainer/publish-director.md` — optional

Also follow `openmontage-production-contract`.

## Execution loop

1. `doctor` → confirm Piper + Remotion + FFmpeg; `can_produce_video_now` should be true.
2. `init_project` with `pipeline_type=animated-explainer` (production Agent only).
3. For each stage: read director skill → produce artifact via `write_artifact` → `write_checkpoint`.
4. Gated stages: write `awaiting_human`, summarize, **END TURN**. After user approval, call `approve_checkpoint` with their exact approval text.
5. Assets: `tts_sample` → user listen OK → `tts_generate` with `confirm_sample_ok=true`.
6. Compose: `compose_preflight` → `compose_start` → poll `job_status` → `probe_media` on `renders/final.mp4`.

## Hard rules

- No `make_video` single call.
- Do not silently switch Remotion ↔ HyperFrames.
- Do not invent user approval.
- All paths under `OPENMONTAGE_PROJECTS_DIR`.
- Budget default `$0` for zero-key path.
- Present both composition runtimes if both available; wait for user choice before locking.

## Deliverable

`$OPENMONTAGE_PROJECTS_DIR/<id>/renders/final.mp4`

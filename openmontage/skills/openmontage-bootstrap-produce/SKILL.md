---
name: openmontage-bootstrap-produce
description: Minimal zero-key explainer produce flow via openmontage-bootstrap produce_* tools.
metadata:
  openclaw:
    requires:
      bins:
        - python
      env:
        - OPENMONTAGE_PROJECTS_DIR
    primaryEnv: OPENMONTAGE_PROJECTS_DIR
    envVars:
      - name: OPENMONTAGE_PROJECTS_DIR
        required: true
        description: Sandboxed projects root
      - name: OPENMONTAGE_P1_ALLOW_WRITES
        required: true
        description: Must be true for produce writes
      - name: PIPER_MODEL_DIR
        required: false
      - name: OPENMONTAGE_PIPER_MODEL
        required: false
    os:
      - win32
      - darwin
      - linux
    emoji: "🎬"
---

# OpenMontage BootStrap Produce (Skill02)

## Scope (v1 minimal)

Zero-key **animated explainer** path only via facade `produce_*` tools.

**In scope:** init project, checkpoints/approvals, Piper TTS sample→batch, subtitles, compose, probe.

**Out of scope:** diagram, stitch, mix_audio, paid TTS/image/video execution.

## Required MCP

`openmontage-bootstrap` (`produce_*` tools).  
Prerequisite: Skill01 `verify_ready` passed (or equivalent doctor ready).

## Hard protocol

1. Confirm `verify_ready` / Piper preflight before asset generation.
2. Human gates: stop for user approval; `produce_approve_checkpoint` needs the user's **approval_text** — never invent it.
3. TTS: `produce_tts_sample` → user listen OK → `produce_tts_generate(..., confirm_sample_ok=true)`.
4. Compose: `produce_compose_preflight` then `produce_compose_start`; poll `produce_job_status`.
5. Deliverable: `renders/final.mp4` under the project sandbox.
6. Read stage directors under `skills/pipelines/explainer/` when available in the workspace.

## Optional teaching (do not execute unless configured)

If the user wants paid/cloud TTS, image, or video: hand off to Skill03 `openmontage-bootstrap-providers` (setup) and the matching `openmontage-providers-*` Skill (execution with dry_run → sample → generate). Do **not** call paid APIs from this Skill.

## Related

Also see `openmontage-animated-explainer` / `openmontage-production-contract` for fuller pipeline guidance when those Skills are loaded.

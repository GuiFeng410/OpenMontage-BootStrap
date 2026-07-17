---
name: openmontage-production-contract
description: OpenMontage production contract — Rule Zero, gates, decision log, runtime selection.
metadata:
  openclaw:
    os:
      - win32
      - darwin
      - linux
    emoji: "📜"
---

# OpenMontage Production Contract (P1)

## Rule Zero

All production goes through a pipeline. Identify pipeline → read manifest → preflight → execute stage by stage with director skills → checkpoint → human gates.

## Decision communication

Before paid or consequential generation:

- announce tool, provider, model, sample vs batch
- ask before switching provider/runtime/narration/music
- append `decision_log` with same `(category, subject)` when revising a choice

## Human gates

Typical explainer gates: `proposal`, `script`, `scene_plan`, `assets` (+ TTS sample), optional `publish`.

Protocol:

1. Write checkpoint `awaiting_human`
2. Present summary + cost snapshot
3. **END YOUR TURN**
4. After user reply, `approve_checkpoint` with `approval_text` = user words
5. Never mark gated stage `completed` without `human_approved`

## Runtime selection (HARD)

If both Remotion and HyperFrames are available, present both with tradeoffs and wait for explicit user approval. Log `render_runtime_selection` with both options considered.

If only one runtime exists, say so explicitly.

## Composition mode

Present templated vs atelier as its own decision (`composition_mode`). Default atelier for hero explainers when the user wants a distinctive look.

## Reviewer

After each stage, self-review against manifest `review_focus` (advisory, max 2 rounds). Do not skip schema validation.

## Writes & sandbox

- Default Agent: read-only doctor tools
- Production Agent: `OPENMONTAGE_P1_ALLOW_WRITES=true`
- All file I/O under `OPENMONTAGE_PROJECTS_DIR`
- Media generation only via `openmontage-media`

## Forbidden

- Python orchestrator that skips Skills
- Silent provider/runtime fallback
- MCP inventing approvals
- Embedding API keys in Skills

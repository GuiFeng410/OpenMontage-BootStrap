---
name: openmontage-router
description: Diagnose OpenMontage setup via doctor MCP and give 3 machine-ready starter prompts.
metadata:
  openclaw:
    requires:
      bins:
        - python
    primaryEnv: OPENMONTAGE_PROJECTS_DIR
    envVars:
      - name: OPENMONTAGE_PROJECTS_DIR
        required: false
        description: Sandboxed projects root; required for project state tools
      - name: PYTHONUTF8
        required: false
        description: Set to 1 on Windows for UTF-8
    os:
      - win32
      - darwin
      - linux
    emoji: "🎬"
---

# OpenMontage Router (P0)

## When to use

User is vague or exploring: "我想做视频", "现在能做什么", "help me create something".

Skip when they already give a concrete production brief **and** P1 media packs are installed. In P0, still diagnose first, then explain what to install for production.

## Hard rules

1. Call OpenMontage doctor MCP tools (names may appear as `openmontage-doctor__doctor` — use whatever the host lists).
2. **Do not** generate video, call paid APIs, or invent a `make_video` tool.
3. **Do not** dump raw JSON. Paraphrase in plain language.
4. Give **exactly 3** starter prompts that match the current machine.
5. `can_produce_video_now` from doctor is **false** in P0 even if Remotion/Piper exist — media MCP is P1.
6. Do **not** pick Remotion vs HyperFrames during onboarding; only report availability.
7. Default Agent has **no host write access**. Never call `init_project` on the default Agent.

## Protocol

### 1) Diagnose

Call:

- `doctor` (optional `deep=false`)
- `provider_menu_summary`

### 2) Summarize

Cover:

- Ready binaries (Python / Node / FFmpeg / Piper / Remotion)
- Setup tier hint (`tier` field)
- What is missing + platform-specific fix commands from `fix_hint` / `quick_unlocks`
- That P0 is diagnosis-only; full explainer needs P1 packs

### 3) Exactly 3 prompts

Rules:

- If cannot produce video now (always in P0): at least one prompt must be an install/next-step prompt (Piper / Remotion / FFmpeg / P1 packs), not a fake "render now" request.
- Prefer zero-key explainer wording when Piper+Remotion+FFmpeg look present.
- Never recommend a paid-only path as the only option when free tools exist.

Example shape (adapt to doctor output):

1. Install/fix the top missing dependency, then re-ask "现在能做什么".
2. "制作一个 45 秒动画解说，讲天空为什么是蓝色的；零 Key，关卡等我确认。" (only if local stack looks ready; still note P1 MCP required to actually render)
3. "先只做能力诊断：列出我机器上可用的 TTS / 合成引擎，不要生成视频。"

### 4) Gates pointer

If the user asks how approvals work, load / follow `openmontage-gates-intro`.

### 5) Production handoff

If they want a finished video:

- Tell them P1 requires `openmontage-media` MCP + animated-explainer Skill Pack + Piper/Remotion/FFmpeg.
- Do not start pipeline stages yourself in P0.

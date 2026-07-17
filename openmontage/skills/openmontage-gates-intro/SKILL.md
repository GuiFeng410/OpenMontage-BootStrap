---
name: openmontage-gates-intro
description: Explain OpenMontage human approval gates and how users should reply at each stage.
metadata:
  openclaw:
    os:
      - win32
      - darwin
      - linux
    emoji: "🚦"
---

# OpenMontage Gates Intro (P0)

## Purpose

Teach newcomers how creative checkpoints work. This Skill does **not** write checkpoints and does **not** generate media.

## Gate map (animated explainer)

| Stage | What you review | Suggested reply |
|-------|-----------------|-----------------|
| proposal | 2–3 concepts, cost, runtime options | `选 B` / `选 c1` / `方案 2` |
| script | Narration copy | `脚本通过` or request line edits |
| scene_plan | Shot list / visual types | `分镜通过` |
| assets | Files + **TTS sample listen** | `试听通过，资产通过` |

Later stages (`edit`, `compose`) usually auto-proceed. `publish` is optional and gated when present.

## Rules for the Agent

1. At a human gate: present a short summary, then **end the turn**. Wait for the user.
2. Do not treat silence as approval.
3. Do not spend paid API budget before proposal approval.
4. Default P0 Agent cannot write project files on the host; production writes belong to elevated/sandbox agents in later phases.

## Where the final video will live (P1+)

```text
$OPENMONTAGE_PROJECTS_DIR/<project-id>/renders/final.mp4
```

Artifacts and checkpoints live under the same project directory inside that sandbox root.

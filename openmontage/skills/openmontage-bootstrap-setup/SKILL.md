---
name: openmontage-bootstrap-setup
description: Detect and install OpenMontage BootStrap environment via openmontage-bootstrap MCP with dry_run gates.
metadata:
  openclaw:
    requires:
      bins:
        - python
    os:
      - win32
      - darwin
      - linux
    emoji: "🧰"
---

# OpenMontage BootStrap Setup (Skill01)

## Required MCP

`openmontage-bootstrap` — `python -m openmontage.mcp.bootstrap`  
`cwd` must be the manually cloned repo root.

## Hard protocol

1. Assume the user **already cloned** the repo (GitHub primary, Gitee fallback). Do not invent a seed pip flow.
2. `detect_environment` — summarize gaps.
3. `plan_install` — show the **full change plan** to the user (venv, npm, ffmpeg, piper, sandbox).
4. Wait for explicit user approval of the plan.
5. For each needed step, call with `dry_run=false` **and** `confirm_execute=true` only after approval:
   - `install_python_deps`
   - `install_node_deps`
   - `ensure_ffmpeg`
   - `ensure_piper_model`
   - `configure_sandbox`
6. Never call high-risk tools with `confirm_execute=true` while `dry_run` is still true-only preview without user OK.
7. If a tool returns `skipped_no_admin_or_failed` / `manual_commands`: show those commands; do not pretend success.
8. `verify_ready` — only when `ready_for_skill02` / `can_produce_video_now` is true, hand off to Skill02.

## Optional

`clone_repo` — only if the user asks to clone again into a new path; still dry_run first.

## Success

Environment ready for zero-key produce; OpenClaw MCP `command` preferably points at `.venv` python after install.

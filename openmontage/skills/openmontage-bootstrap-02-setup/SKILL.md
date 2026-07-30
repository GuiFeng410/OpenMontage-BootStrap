---
name: openmontage-bootstrap-02-setup
description: >-
  Detect and install OpenMontage BootStrap runtime via openmontage-bootstrap MCP
  with dry_run gates; verify_ready then hand off to 03-usercheck / produce.
  Host-agnostic (any agent with Skills + MCP).
metadata:
  requires:
    bins:
      - python
  os:
    - win32
    - darwin
    - linux
  emoji: "🧰"
---

# OpenMontage BootStrap Setup（02 · 环境）

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
8. `verify_ready` — only when ready flags indicate produce is possible（如 `can_produce_video_now` / 等价 ready），交接下游：模糊需求 → **`openmontage-bootstrap-03-usercheck`**；简报已锁定 → **`openmontage-bootstrap-04-produce`**。

## 旁白依赖提醒

- `install_python_deps` 会装上 `requirements.txt` 中的 **`edge-tts`**。  
- **默认推荐**中文旁白：Edge-TTS 男声 `zh-CN-YunyangNeural`（需联网）；按字幕 SRT **cue 对齐**（见 04）。  
- 旁白相对「先出画面」**可以后置**：不挡 `verify_ready`，也不要求用户在 setup 阶段就选定配音。  
- Piper 模型仍由 `ensure_piper_model` 安装，作**离线回退**。  
- 付费云端 TTS 仅在用户显式要求且已配 Key 时走 `06-providers` / providers-tts。

## Optional

`clone_repo` — only if the user asks to clone again into a new path; still dry_run first.

## Success

Environment ready for zero-key light produce path; MCP `command` preferably points at `.venv` python after install.  
Hand-off: **03-usercheck**（表 1→2→3）→ **04-produce**.

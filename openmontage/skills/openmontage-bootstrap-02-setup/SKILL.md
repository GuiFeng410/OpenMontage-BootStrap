---
name: openmontage-bootstrap-02-setup
description: >-
  Detect and install OpenMontage BootStrap runtime via openmontage-bootstrap MCP
  with dry_run gates; Edge-TTS primary, HyperFrames recommended/skippable,
  Piper optional offline; verify_ready then hand off to 03-usercheck / produce.
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
2. `detect_environment` — summarize gaps（含 Edge / HyperFrames 建议项）。  
3. `plan_install` — show the **full change plan** to the user. Default plan order:

   | 优先级 | 步骤 | 说明 |
   |--------|------|------|
   | 必做 | `install_python_deps` | venv + `requirements.txt`（含 **edge-tts**） |
   | 必做 | `install_node_deps` | `remotion-composer` 的 `npm install` |
   | 必做 | `ensure_ffmpeg` | FFmpeg / ffprobe |
   | 必做验收 | `probe_edge_tts` | 确认 Edge 可 import（合成时需联网） |
   | **建议** | `probe_hyperframes` | Node ≥ 22 + npx + ffmpeg；可跳过，**不挡** `verify_ready` |
   | 必做 | `configure_sandbox` | `OPENMONTAGE_PROJECTS_DIR` 等 |
   | 可选 | `ensure_piper_model` | **仅**用户要离线旁白时；`plan_install(include_piper=true)` |

4. Wait for explicit user approval of the plan.  
5. For each **required** step, call with `dry_run=false` **and** `confirm_execute=true` only after approval.  
6. Never call high-risk tools with `confirm_execute=true` while `dry_run` is still true-only preview without user OK.  
7. If a tool returns `skipped_no_admin_or_failed` / `manual_commands`: show those commands; do not pretend success.  
8. HyperFrames：**建议安装**。向用户说明 Node.js **≥ 22**、PATH 上有 `npx`/`ffmpeg`，然后可跑 `npx hyperframes doctor` 或 `probe_hyperframes(run_doctor=true)`。用户说跳过 → 继续；勿因缺 HF 判定 setup 失败。  
9. `verify_ready` — when `can_produce_video_now`（或等价 ready）为真即可交接下游。该工具会写入仓根 `.openmontage/install-state.json`（不写密钥）。读返回的 `recommendations`：若缺 HF，仍可交接，但用一句话提醒「建议补装 HyperFrames，轻度讲解/品牌片可多一条路径」。  
10. 交接：模糊需求 → **`openmontage-bootstrap-03-usercheck`**（先 `scan_video_keys`，默认电商）；简报已锁定 → **`openmontage-bootstrap-04-produce`**。

## TTS 策略（强制口径）

| 角色 | 引擎 | 安装 |
|------|------|------|
| **主推** | **Edge-TTS**（默认男声 `zh-CN-YunyangNeural`） | 随 `install_python_deps`；用 `probe_edge_tts` 验收 |
| **可选回退** | Piper | **默认不下载**；仅离线或用户点名时 `ensure_piper_model` |

- 旁白相对「先出画面」**可以后置**：不挡 `verify_ready`。  
- 向用户展示计划时：**先讲 Edge，再提 Piper 可选**，勿把 Piper 写成必装。  
- 付费云端 TTS：仅用户显式要求且已配 Key → `06-providers` / providers-tts。

## HyperFrames（建议 · 可跳过）

- 用途：轻度品牌渐显 / 动能文字等（见 `03-usercheck/references/first-run-demo.md`）。  
- 门槛：Node.js ≥ 22、`npx`、FFmpeg；验收：`npx hyperframes doctor`。  
- **第一期不做复杂自动安装**：检测 + 口述命令 + doctor；用户确认后再代跑系统级 Node 安装（若需要）。  
- 跳过不影响 Remotion 轻度出片。

## Optional

`clone_repo` — only if the user asks to clone again into a new path; still dry_run first.  
`plan_install(..., include_piper=true)` — only when offline Piper is requested.

## Success

- Required steps done；`probe_edge_tts` ready（或已说明缺包将重跑 python deps）。  
- `verify_ready` / `can_produce_video_now` 为真。  
- HyperFrames：已建议；若未装，已告知可跳过且不挡出片。  
- MCP `command` preferably points at `.venv` python after install.  
- Hand-off: **03-usercheck**（默认电商 · `scan_video_keys` · 给网址；轻度仅明确要求）→ **04-produce**。  
- 已写入 `.openmontage/install-state.json`（或已说明写入失败但不挡出片）。  
- 向用户可加一句：「环境已就绪；旁白默认 Edge-TTS；建议有 Node 22+ 时再装 HyperFrames。默认按电商宣传片出片，明确要讲解时再走轻度。」

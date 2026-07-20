# 第二步：配置 MCP 与 Skill

前提：已完成 [01-第一步](./01-第一步-下载必要文件与运行时.md)。  
目标：在 OpenClaw（或 eClaw 等价配置）里挂上 OpenMontage 的「手」（MCP）与「脑」（Skill）。

路径占位符以实机为准；企业壳若 UI 不同，技术基线仍是：`mcp.servers` + Skill 目录加载。

---

## 2.1 要注册的 MCP（最少 2 个；可选第 3 个）

配置模板源：

| 阶段 | 模板 |
|------|------|
| P0/P1 | [../Mcp_Entity/Mcp_P1/templates/p1-openclaw.mcp.json](../Mcp_Entity/Mcp_P1/templates/p1-openclaw.mcp.json) |
| P2 TTS（可选） | [../Mcp_Entity/Mcp_P2/templates/p2-providers-tts.mcp.json](../Mcp_Entity/Mcp_P2/templates/p2-providers-tts.mcp.json) |

安装说明：

- [../Mcp_Entity/Mcp_P1/02-OpenClaw安装.md](../Mcp_Entity/Mcp_P1/02-OpenClaw安装.md)
- [../Mcp_Entity/Mcp_P2/02-OpenClaw安装.md](../Mcp_Entity/Mcp_P2/02-OpenClaw安装.md)

### A. `openmontage-doctor`（必须）

- [ ] `command`：目标机 venv 的 `python`（不要用错系统 Python）  
- [ ] `args`：`["-m", "openmontage.mcp.doctor"]`  
- [ ] `cwd`：`<OPENMONTAGE_REPO_ROOT>`  
- [ ] `env`：
  - `OPENMONTAGE_PROJECTS_DIR=<PROJECTS_DIR>`
  - `PYTHONUTF8=1`
  - Production：`OPENMONTAGE_P1_ALLOW_WRITES=true`

### B. `openmontage-media`（必须，出片）

- [ ] `args`：`["-m", "openmontage.mcp.media"]`  
- [ ] 同样 `cwd` + `OPENMONTAGE_PROJECTS_DIR` + `PYTHONUTF8`  
- [ ] `env`：`PIPER_MODEL_DIR`、`OPENMONTAGE_PIPER_MODEL`

### C. `openmontage-providers-tts`（可选，付费 TTS）

- [ ] `args`：`["-m", "openmontage.mcp.providers_tts"]`  
- [ ] `env`：所选 `*_API_KEY`、`OPENMONTAGE_MAX_COST_USD`、`OPENMONTAGE_ALLOWED_PROVIDERS`  
- [ ] 最小零 Key 出片可跳过本项

### 探针

- [ ] `openclaw mcp doctor openmontage-doctor --probe`（或实机等价）  
- [ ] Production Agent 能看到 `openmontage-media__*`（至少 `tts_sample` / `compose_start`）  
- [ ] 若启用 P2：能看到 `openmontage-providers-tts__list_tts_providers`

---

## 2.2 导入 Skill

### 加载方式（二选一）

**A. extraDirs（推荐）**

- [ ] `skills.load.extraDirs` 增加：`<OPENMONTAGE_REPO_ROOT>/openmontage/skills`  
- [ ] 开发期建议 `watch: true`

**B. 复制**

- [ ] 将 `openmontage/skills/*` 复制到 OpenClaw skills 目录（路径以实机为准）

### 必须启用（最小出片）

| Skill | 用途 |
|-------|------|
| `openmontage-animated-explainer` | 解说出片主流程 |
| `openmontage-production-contract` | 关卡 / Rule Zero / runtime |

### 建议启用

| Skill | 用途 |
|-------|------|
| `openmontage-router` | 入门路由（P0） |
| `openmontage-gates-intro` | 人审关说明 |
| `openmontage-l3-remotion` | Remotion Layer3 指针 |
| `openmontage-l3-tts` | TTS Layer3 指针 |
| `openmontage-l3-ffmpeg` | FFmpeg Layer3 指针 |
| `openmontage-providers-tts` | 仅在要用付费 TTS 时启用 |

### 重要提醒

- [ ] OpenClaw Skill **不会**自动带上仓内 `skills/pipelines/explainer/`；Agent 仍需能读仓库文件，或经 MCP 完成出片  
- [ ] 若 Agent `workspaceAccess: none`，请按实机策略放行对仓库的只读访问（以便读 director）

策略模板：

- [../Mcp_Entity/Mcp_P1/templates/p1-openclaw.policy.json5](../Mcp_Entity/Mcp_P1/templates/p1-openclaw.policy.json5)
- [../Mcp_Entity/Mcp_P2/templates/p2-providers-tts.policy.json5](../Mcp_Entity/Mcp_P2/templates/p2-providers-tts.policy.json5)

---

## 2.3 建议：双 Agent

| Agent | 写盘 | MCP | Skills |
|-------|------|-----|--------|
| Default（诊断） | 关 | 仅 doctor 只读 | router + gates-intro |
| Production（出片） | `OPENMONTAGE_P1_ALLOW_WRITES=true` | doctor + media（+ 可选 providers-tts） | explainer + production-contract（+ L3；+ 可选 providers-tts） |

- [ ] 至少 Production 已按上表配齐  
- [ ] Default **不要**误开写盘 flag

---

## 2.4 本步勾选总表

| # | 项 | ☐ |
|---|----|---|
| 1 | doctor MCP 已注册且 probe 成功 | |
| 2 | media MCP 已注册，工具可见 | |
| 3 | Skill 目录已加载，explainer + production-contract 已启用 | |
| 4 | Production 写盘 flag 与工具策略已放行 | |
| 5 | （可选）providers-tts MCP + Skill + Key | |

**下一步 →** [03-第三步-最小视频出片验证.md](./03-第三步-最小视频出片验证.md)

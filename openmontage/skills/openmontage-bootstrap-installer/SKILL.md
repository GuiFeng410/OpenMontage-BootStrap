---
name: openmontage-bootstrap-installer
description: >-
  BootStrap installer Skill for OpenClaw: when the user wants to make a video,
  guide cloning OpenMontage-BootStrap and narrate MCP/Skill setup steps (no auto
  config edits). Registers facade + three providers MCPs; paid Keys stay optional.
metadata:
  openclaw:
    os:
      - win32
      - darwin
      - linux
    emoji: "📦"
---

# OpenMontage BootStrap Installer（安装 Skill）

## 分发方式（重要）

本 Skill **先单独复制**到 OpenClaw 用户本地 Skill 目录（不依赖仓库已存在）。  
用户说「我想生成视频 / 做个解说片」等时启用本 Skill。

仓内路径（供你拷贝）：`openmontage/skills/openmontage-bootstrap-installer/`

## 硬规则

1. **不自动修改** OpenClaw 配置文件；只**口述**逐步操作，等用户确认完成后再进入下一步。  
2. 拉仓优先 GitHub，失败再用 Gitee。  
3. 安装阶段目标：项目可跑 + **4 个 MCP 已注册可启动** + **3 个 Skill 已启用**。  
4. **付费 API Key 安装时不必填**；MCP 可先用占位/空 Key 启动。项目与零 Key 路径跑通后，再可选填 Key。  
5. 不要跳过「用户确认已 clone / 已改配置」的检查点。

## 触发话术（示例）

用户类似说法即可进入本流程：

- 我想生成视频  
- 帮我做个动画解说  
- 安装 OpenMontage / BootStrap  

## 流程

### A. 询问安装目录

问用户要把仓库克隆到哪个本地路径，记为 `<TARGET>`（例如 `D:\OpenMontage-BootStrap`）。

### B. 口述 clone（可代跑终端则代跑；否则只给命令）

```powershell
git clone https://github.com/GuiFeng410/OpenMontage-BootStrap.git "<TARGET>"
# 若失败：
git clone https://gitee.com/rory_-3232/open-montage-boot-strap.git "<TARGET>"
```

用户确认 clone 成功后继续。

### C. 口述最小 Python（启动 MCP 需要）

```powershell
cd "<TARGET>"
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### D. 口述注册 MCP（门面 + 三个 providers，共 4 个；只口述，不改文件）

请用户在 OpenClaw 中**一并注册**下列 MCP（模板在 `<TARGET>/README/templates/`）：

| Server | 模板 | 模块 |
|--------|------|------|
| 门面 | `bootstrap.mcp.json` | `openmontage.mcp.bootstrap` |
| 付费 TTS | `providers-tts.mcp.json` | `openmontage.mcp.providers_tts` |
| 付费生图 | `providers-image.mcp.json` | `openmontage.mcp.providers_image` |
| 付费生视频 | `providers-video.mcp.json` | `openmontage.mcp.providers_video` |

共同点：

- `command`：`<TARGET>\.venv\Scripts\python.exe`（或等价）  
- `cwd`：`<TARGET>`  
- `env`：至少 `OPENMONTAGE_PROJECTS_DIR`、`PYTHONUTF8=1`  
- 门面另需：`OPENMONTAGE_P1_ALLOW_WRITES=true`  
- **付费 Key（`OPENAI_API_KEY` / `FAL_KEY` / `KLING_API_KEY` 等）此时可留空或删掉**，先保证四个 server 能启动  

等用户回复「四个 MCP 都已配好并能启动」再继续。

### E. 口述启用仓内 3 个 Skill

请用户将 `skills.load.extraDirs` 增加：

`<TARGET>/openmontage/skills`

并**启用**（安装必开）：

- `openmontage-bootstrap-setup`（Skill01 环境）  
- `openmontage-bootstrap-produce`（Skill02 零 Key 出片）  
- `openmontage-bootstrap-providers`（Skill03 收费引导；无 Key 时只做说明，不烧钱）  

同目录下还有 `openmontage-providers-tts` / `image` / `video`（执行层）：无 Key 时可不急用；填 Key 后由 Skill03 交接启用即可。

（本安装 Skill 可保留在外置目录，供以后新机引导。）

等用户回复「三个 Skill 已启用」再继续。

### F. 交接（零 Key 先跑通；Key 后选）

告知用户下一步对 Agent 说：

> 先检测环境，给我看完整安装计划，不要直接改系统。

交由 **setup** → `verify_ready` → **produce** 零 Key 出片。  

**付费 Key（可选，安装后）：** 项目与 MCP 已稳定后，若要用云端 TTS/生图/生视频，再对 Agent 说「按 Skill03 帮我填 Key」，或自读 `<TARGET>/README/04-收费Providers接入.md`。  
此时只需在已注册的 providers MCP 的 `env` 里填入对应 Key 并重启 MCP，**不必重装项目**。

操作说明索引：`<TARGET>/README/00-INDEX.md`

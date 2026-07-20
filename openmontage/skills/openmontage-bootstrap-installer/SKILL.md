---
name: openmontage-bootstrap-installer
description: >-
  BootStrap installer Skill for OpenClaw: when the user wants to make a video,
  guide cloning OpenMontage-BootStrap and narrate MCP/Skill setup steps (no auto
  config edits).
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
3. 拉仓完成后，仓内应已包含：门面 MCP `openmontage-bootstrap` + Skill `setup` / `produce` /（可选）`providers`（Skill03）。  
4. 不要跳过「用户确认已 clone / 已改配置」的检查点。

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

### D. 口述注册门面 MCP（只口述，不改文件）

请用户在 OpenClaw 中新增 MCP（模板在仓内）：

- 文件：`<TARGET>/README/templates/bootstrap.mcp.json`
- `command`：`<TARGET>\.venv\Scripts\python.exe`（或等价）
- `args`：`["-m", "openmontage.mcp.bootstrap"]`
- `cwd`：`<TARGET>`
- `env`：`OPENMONTAGE_PROJECTS_DIR`、`PYTHONUTF8=1`、`OPENMONTAGE_P1_ALLOW_WRITES=true`

等用户回复「MCP 已配好」再继续。

### E. 口述启用仓内 Skill

请用户将 `skills.load.extraDirs` 增加：

`<TARGET>/openmontage/skills`

并启用：

- `openmontage-bootstrap-setup`（环境安装）  
- `openmontage-bootstrap-produce`（零 Key 出片）  
- （可选）`openmontage-bootstrap-providers`（收费 Key/MCP 引导，见 README/04）  

（本安装 Skill 可保留，用于新机再次引导。）

等用户回复「Skill 已启用」再继续。

### F. 交接

告知用户下一步对 Agent 说：

> 先检测环境，给我看完整安装计划，不要直接改系统。

交由 **setup** Skill 执行；通过 `verify_ready` 后再说出片需求，交由 **produce** Skill。  
若要云端 TTS/生图/生视频：读 `<TARGET>/README/04-收费Providers接入.md`，启用 Skill03。

操作说明索引：`<TARGET>/README/00-INDEX.md`

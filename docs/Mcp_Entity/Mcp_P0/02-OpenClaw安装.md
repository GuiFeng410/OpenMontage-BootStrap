# OpenClaw P0 安装指南

> 门禁宿主：**OpenClaw**（eClaw 差异见 Guide/05，未证实前勿写死 eClaw 路径）

## 1. 环境变量

```powershell
# Windows PowerShell
$env:PYTHONUTF8 = "1"
$env:OPENMONTAGE_PROJECTS_DIR = "C:\Users\<you>\OpenMontageProjects"
# 可选：勿对默认 Agent 设置
# $env:OPENMONTAGE_P0_ALLOW_WRITES = "true"
```

创建沙箱根目录（仅目录本身；默认 Agent 仍不能通过 MCP 写项目）：

```powershell
New-Item -ItemType Directory -Force -Path $env:OPENMONTAGE_PROJECTS_DIR
```

## 2. Python 依赖

在仓库根、已激活 venv：

```powershell
python -m pip install -r requirements.txt
# 确保含 mcp>=1.0
```

验证：

```powershell
python -m openmontage.mcp.doctor --help
# FastMCP 无 --help 时会挂起等 stdio；改用：
python -c "from openmontage.mcp.doctor.server import mcp; print(mcp.name)"
```

## 3. 注册 MCP（stdio）

将 [templates/p0-openclaw.mcp.json](./templates/p0-openclaw.mcp.json) 合并进 `~/.openclaw/openclaw.json` 的 `mcp.servers`，或：

```bash
openclaw mcp add openmontage-doctor \
  --command python \
  --arg -m \
  --arg openmontage.mcp.doctor \
  --cwd "<OPENMONTAGE_REPO_ROOT>" \
  --env OPENMONTAGE_PROJECTS_DIR=<PROJECTS_DIR> \
  --env PYTHONUTF8=1 \
  --include "doctor,provider_menu_summary,list_pipelines,list_projects,get_project_state,get_next_stage,validate_artifact,validate_checkpoint,estimate_cost"

openclaw mcp doctor openmontage-doctor --probe
```

**注意：** 默认 `toolFilter.include` **不含** `init_project`。即使误暴露，服务端也会拒绝写盘。

## 4. 加载 Skill

方式 A — `extraDirs`（推荐开发）：

```json5
{
  skills: {
    load: {
      extraDirs: ["<OPENMONTAGE_REPO_ROOT>/openmontage/skills"],
      watch: true
    },
    entries: {
      "openmontage-router": { enabled: true },
      "openmontage-gates-intro": { enabled: true }
    }
  },
  agents: {
    defaults: {
      skills: ["openmontage-router", "openmontage-gates-intro"]
    }
  }
}
```

方式 B — 复制到 `~/.openclaw/skills/`：

```text
openmontage-router/
openmontage-gates-intro/
```

## 5. 权限基线（必须）

合并 [templates/p0-openclaw.policy.json5](./templates/p0-openclaw.policy.json5)：

- allow: `bundle-mcp`, `openmontage-doctor__*`
- deny: `group:runtime`, `browser`, `gateway`
- 默认 Agent sandbox：`workspaceAccess: "none"`（无宿主机工作区写）

若沙箱开启后看不到 MCP 工具：放行 `bundle-mcp` 与 `openmontage-doctor__*`。

## 6. 对话验收句

对 Agent 说：

> 我想做一个视频，现在能做什么？

期望：白话诊断 + 恰好 3 条提示词 + 说明 P0 不能直接出片。

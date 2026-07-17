# OpenClaw P1 安装指南

> 前置：完成 [../Mcp_P0/02-OpenClaw安装.md](../Mcp_P0/02-OpenClaw安装.md)  
> 门禁宿主：**OpenClaw**

## 1. 本机依赖（零 Key）

| 依赖 | 说明 |
|------|------|
| Piper | `pip install piper-tts` + 中文模型（如 `zh_CN-huayan-medium`） |
| Node 18+ | Remotion composer |
| Remotion | 仓库内 `remotion-composer` 执行 `npm install` |
| FFmpeg / FFprobe | PATH 可用 |
| 中文字体 | 本机至少一套 |

```powershell
$env:PIPER_MODEL_DIR = "$env:USERPROFILE\.piper\models"
$env:OPENMONTAGE_PIPER_MODEL = "zh_CN-huayan-medium"
# 生产 Agent 必须：
$env:OPENMONTAGE_P1_ALLOW_WRITES = "true"
$env:OPENMONTAGE_PROJECTS_DIR = "C:\Users\<you>\OpenMontageProjects"
```

用 doctor 确认：`can_produce_video_now == true`（Piper + Remotion + FFmpeg + media 模块 + explainer Skill）。

## 2. 注册 MCP

合并 [templates/p1-openclaw.mcp.json](./templates/p1-openclaw.mcp.json)：

- **Default Agent**：沿用 P0 — 仅 doctor 只读 `toolFilter`，**不要**设 `OPENMONTAGE_P1_ALLOW_WRITES`
- **Production Agent**：doctor 全量工具 + `openmontage-media`，env 含 `OPENMONTAGE_P1_ALLOW_WRITES=true`

示例（production）：

```bash
openclaw mcp add openmontage-media \
  --command python \
  --arg -m \
  --arg openmontage.mcp.media \
  --cwd "<OPENMONTAGE_REPO_ROOT>" \
  --env OPENMONTAGE_PROJECTS_DIR=<PROJECTS_DIR> \
  --env PYTHONUTF8=1 \
  --env PIPER_MODEL_DIR=<PIPER_MODEL_DIR>
```

doctor production 侧需取消对 `init_project` / write 工具的 `exclude`，并设置 write flag。

## 3. 加载 Skill

```json5
{
  skills: {
    load: {
      extraDirs: ["<OPENMONTAGE_REPO_ROOT>/openmontage/skills"],
      watch: true
    },
    entries: {
      "openmontage-router": { enabled: true },
      "openmontage-gates-intro": { enabled: true },
      "openmontage-animated-explainer": { enabled: true },
      "openmontage-production-contract": { enabled: true },
      "openmontage-l3-remotion": { enabled: true },
      "openmontage-l3-tts": { enabled: true },
      "openmontage-l3-ffmpeg": { enabled: true }
    }
  }
}
```

Production Agent `skills` 至少包含：`openmontage-animated-explainer`、`openmontage-production-contract`。

## 4. 权限基线

合并 [templates/p1-openclaw.policy.json5](./templates/p1-openclaw.policy.json5)：

- allow：`bundle-mcp`、`openmontage-doctor__*`、`openmontage-media__*`
- deny：`group:runtime`、`browser`、`gateway`（除非调试需要）
- Production：`workspaceAccess` 仍建议限制；文件只经 MCP 沙箱路径写入

## 5. 对话验收句

对 **Production** Agent：

> 制作一个约 45 秒动画解说，解释天空为什么是蓝色的；零 Key，每个关卡等我确认。

期望：调用 `init_project` → 按 director 推进 → 在 proposal/script/scene_plan/assets 停轮 → TTS 先 sample 再 batch → `compose_start` + `job_status` → `renders/final.mp4`。
